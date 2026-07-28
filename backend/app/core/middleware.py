"""Request-scoped middleware: identity, origin and correlation id."""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger
from app.core.request_context import build_context, reset_context, set_context

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
SESSION_ID_HEADER = "X-Session-ID"


def client_ip_from(request: Request) -> str | None:
    """Best-effort client address.

    ``X-Forwarded-For`` is honoured because the API is normally behind a proxy,
    and its first entry is the original client. It is spoofable, so it is used
    for provenance only — never for authorisation.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a :class:`RequestContext` for the lifetime of each request.

    Everything downstream — execution records, audit entries, log lines — reads
    the origin from here, so provenance is captured once and consistently rather
    than re-derived at each call site.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        context = build_context(
            client_ip=client_ip_from(request),
            user_agent=request.headers.get("user-agent"),
            session_id=request.headers.get(SESSION_ID_HEADER),
            request_id=request_id,
            http_method=request.method,
            http_path=request.url.path,
        )

        token = set_context(context)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            reset_context(token)

        duration_ms = int((time.perf_counter() - started) * 1000)
        response.headers[REQUEST_ID_HEADER] = request_id

        # Health checks are polled every few seconds; logging them drowns
        # everything that matters.
        if request.url.path not in ("/health", "/"):
            logger.info(
                "http_request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": context.client_ip,
                },
            )
        return response
