"""Prosthetic Hand LLM Evaluation Platform - FastAPI application.

An experiment runner, not a chat service: there are no conversation endpoints,
no session memory and no streaming chat. Every request is a self-contained
evaluation of one model against one EMG window under a frozen prompt.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
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
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@app.get("/", tags=["system"])
async def root() -> dict:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "api": settings.api_v1_prefix,
        "websockets": ["/ws/simulator", "/ws/emg/{session_key}"],
    }
