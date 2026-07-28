"""Per-request context: who is calling, from where, and under which request id.

Held in a :class:`~contextvars.ContextVar` so any layer can reach it without
threading a parameter through every signature. Async-safe: each request gets its
own copy, and concurrent requests cannot see each other's context.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

#: Ordered longest-first: "Edg" must be tested before "Chrome", and "Chrome"
#: before "Safari", because each of those agents also names the previous one.
_BROWSERS: tuple[tuple[str, str], ...] = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Chrome/", "Chrome"),
    ("Firefox/", "Firefox"),
    ("Safari/", "Safari"),
    ("curl/", "curl"),
    ("python-requests", "python-requests"),
    ("httpx", "httpx"),
    ("PostmanRuntime", "Postman"),
)

#: Ordered most-specific first, and the order is load-bearing:
#:   - iPad and iPhone agents both contain "Mac OS X", so they must be tested
#:     before macOS or every tablet is logged as a desktop Mac.
#:   - Android agents contain "Linux", so Android must precede Linux.
#:   - ChromeOS agents contain "Linux" and "CrOS".
_OPERATING_SYSTEMS: tuple[tuple[str, str], ...] = (
    ("iPad", "iPadOS"),
    ("iPhone", "iOS"),
    ("iPod", "iOS"),
    ("Android", "Android"),
    ("CrOS", "ChromeOS"),
    ("Windows NT 10.0", "Windows 10/11"),
    ("Windows NT", "Windows"),
    ("Mac OS X", "macOS"),
    ("Macintosh", "macOS"),
    ("Linux", "Linux"),
)

_MOBILE_RE = re.compile(r"Mobi|Android|iPhone", re.IGNORECASE)
_TABLET_RE = re.compile(r"iPad|Tablet", re.IGNORECASE)


def parse_browser(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    for token, name in _BROWSERS:
        if token in user_agent:
            return name
    return "unknown"


def parse_operating_system(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    for token, name in _OPERATING_SYSTEMS:
        if token in user_agent:
            return name
    return "unknown"


def parse_device_type(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    if _TABLET_RE.search(user_agent):
        return "tablet"
    if _MOBILE_RE.search(user_agent):
        return "mobile"
    return "desktop"


@dataclass(slots=True)
class RequestContext:
    """Everything about the origin of the current request."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    actor_id: uuid.UUID | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    browser: str | None = None
    operating_system: str | None = None
    device_type: str | None = None
    http_method: str | None = None
    http_path: str | None = None

    def as_origin(self) -> dict[str, Any]:
        """The subset persisted on executions and audit entries."""
        return {
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
            "browser": self.browser,
            "operating_system": self.operating_system,
            "device_type": self.device_type,
            "session_id": self.session_id,
            "request_id": self.request_id,
        }


_EMPTY = RequestContext(request_id="unbound")

_context: ContextVar[RequestContext] = ContextVar("request_context", default=_EMPTY)


def current_context() -> RequestContext:
    """The active context, or a neutral one outside a request (tests, workers)."""
    return _context.get()


def set_context(context: RequestContext):
    return _context.set(context)


def reset_context(token) -> None:
    _context.reset(token)


def build_context(
    *,
    client_ip: str | None,
    user_agent: str | None,
    session_id: str | None,
    request_id: str | None,
    http_method: str | None = None,
    http_path: str | None = None,
) -> RequestContext:
    return RequestContext(
        request_id=request_id or str(uuid.uuid4()),
        session_id=session_id,
        client_ip=client_ip,
        user_agent=user_agent,
        browser=parse_browser(user_agent),
        operating_system=parse_operating_system(user_agent),
        device_type=parse_device_type(user_agent),
        http_method=http_method,
        http_path=http_path,
    )
