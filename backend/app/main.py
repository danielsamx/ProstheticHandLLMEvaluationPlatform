"""Prosthetic Hand LLM Evaluation Platform - FastAPI application.

An experiment runner, not a chat service: there are no conversation endpoints,
no session memory and no streaming chat. Every request is a self-contained
evaluation of one model against one EMG window under a frozen prompt.
"""

from __future__ import annotations

import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.request_context import current_context
from app.core.schema_check import check_and_log
from app.db.session import engine
from app.domain.hand_spec import DRIVEN_DOF, KINEMATIC_DOF
from app.ws import emg_stream

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info(
        "startup",
        extra={
            "app": settings.app_name,
            "env": settings.app_env,
            "driven_dof": DRIVEN_DOF,
            "kinematic_dof": KINEMATIC_DOF,
            "default_limit_profile": settings.default_limit_profile.value,
            "lm_studio_api_base": settings.lm_studio_api_base,
            "cors_origins": settings.cors_origins,
            "cors_origin_regex": settings.cors_origin_regex,
        },
    )

    # A pending migration does not announce itself: the app starts, serves
    # reference data, then dies on the first INSERT touching a missing column.
    # Checking once here turns that into one actionable log line instead of an
    # unexplained dropped connection on the first Run Evaluation.
    app.state.schema_report = await check_and_log(engine)

    yield
    await engine.dispose()
    logger.info("shutdown")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Research platform for benchmarking LLMs on the task of translating "
        "surface EMG into validated control commands for the HANDi EPN V3 "
        "prosthetic hand. Not a chatbot: no conversations, no memory."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Order matters: the context must be bound before any handler runs, and CORS
# must be outermost so preflight responses still carry the right headers.
app.add_middleware(RequestContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)
app.include_router(emg_stream.router)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    logger.warning("value_error", extra={"path": request.url.path, "detail": str(exc)})
    return _error_response(400, str(exc))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Field-level validation failures, with the request id attached."""
    logger.info(
        "request_validation_error",
        extra={"path": request.url.path, "errors": exc.errors()[:10]},
    )
    return _error_response(422, "Request payload failed validation.", errors=exc.errors())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all so an unexpected error is never a dropped connection.

    Without this, an exception propagates through ``BaseHTTPMiddleware`` and can
    reach the browser as a reset socket rather than a response. The client then
    sees status 0, which is indistinguishable from "the server is down" — and
    the actual cause, usually a pending migration, stays invisible.
    """
    logger.error(
        "unhandled_exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=25),
        },
    )

    hint = None
    report = getattr(app.state, "schema_report", None)
    if report is not None and not report.ok:
        # By far the most common cause of a 500 on a write path right after an
        # upgrade, and the one the user cannot guess from the message alone.
        hint = (
            f"{report.summary()} Run `alembic upgrade head`, or with Docker "
            "`docker compose down && docker compose up --build`."
        )

    return _error_response(
        500,
        f"{type(exc).__name__}: {exc}",
        hint=hint,
    )


def _error_response(status_code: int, detail: str, **extra) -> JSONResponse:
    """Uniform error body carrying the request id for log correlation."""
    context = current_context()
    payload: dict = {"detail": detail, "request_id": context.request_id}
    payload.update({k: v for k, v in extra.items() if v is not None})
    return JSONResponse(
        status_code=status_code,
        content=payload,
        # The exception handler runs outside CORSMiddleware, so an error
        # response would otherwise arrive without CORS headers and the browser
        # would report it as a network failure instead of showing the message.
        headers={"Access-Control-Allow-Origin": "*"},
    )


@app.get("/health", tags=["system"])
async def health() -> dict:
    """Liveness, plus whether the schema matches the models.

    The schema state belongs here: a backend that is up but migrating-behind is
    not actually usable, and the interface should be able to say so.
    """
    report = getattr(app.state, "schema_report", None)
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "env": settings.app_env,
        "schema": {
            "ok": report.ok if report else None,
            "revision": report.alembic_revision if report else None,
            "detail": report.summary() if report and not report.ok else None,
        },
    }


@app.get("/", tags=["system"])
async def root() -> dict:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "api": settings.api_v1_prefix,
        "websockets": ["/ws/simulator", "/ws/emg/{session_key}"],
    }
