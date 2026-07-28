"""Structured JSON logging."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.core.config import settings

#: Attributes `LogRecord` owns. Two separate concerns share this set:
#:
#:  * the formatter must not emit them as structured fields, and
#:  * `logging` raises `KeyError: Attempt to overwrite 'x' in LogRecord` if a
#:    caller passes one through `extra` — which crashed the seed on
#:    `extra={"name": ...}`, a completely reasonable-looking key.
_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message", "asctime",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    for noisy in ("httpx", "LiteLLM", "litellm", "sqlalchemy.engine.Engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class SafeLogger(logging.LoggerAdapter):
    """A logger that cannot be crashed by a structured field name.

    `logging` rejects any `extra` key that collides with a `LogRecord`
    attribute, and it does so by raising — so a log line intended to *report* a
    problem takes the process down instead. Several natural field names collide:
    `name`, `module`, `filename`, `args`, `message`.

    Colliding keys are suffixed rather than dropped: the value is usually the
    most interesting part of the line, and silently discarding it would trade a
    crash for a subtler loss.
    """

    def process(self, msg, kwargs):
        extra = kwargs.get("extra")
        if extra:
            kwargs["extra"] = {
                (f"{key}_" if key in _RESERVED else key): value
                for key, value in extra.items()
            }
        return msg, kwargs


def get_logger(name: str) -> SafeLogger:
    return SafeLogger(logging.getLogger(name), {})
