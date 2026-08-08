"""Declarative base and shared column mixins."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    """Timezone-aware current time, evaluated in the application."""
    return datetime.now(timezone.utc)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    """Creation and modification timestamps.

    ``created_at`` keeps a server default: PostgreSQL computes it and SQLAlchemy
    fetches it back through RETURNING on INSERT, so the value is available
    immediately and comes from the database clock.

    ``updated_at`` deliberately uses a *Python-side* ``onupdate`` rather than
    ``func.now()``. A SQL-side onupdate is computed by the server during UPDATE,
    which SQLAlchemy cannot see, so it expires the attribute and defers a
    refresh. That refresh then fires during response serialisation — outside the
    async greenlet — and raises ``MissingGreenlet``:

        Error extracting attribute: greenlet_spawn has not been called

    Evaluating it in the application makes the new value known at flush time, so
    nothing is expired and no lazy IO is attempted. The cost is that the
    timestamp comes from the application clock instead of the database one,
    which is acceptable: every write goes through this process anyway.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_utcnow,
        nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
