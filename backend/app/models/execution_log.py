"""Per-execution log lines.

Application logs go to stdout and rotate away; these are the lines that belong
to the scientific record — the provider retried, a sampling parameter was
dropped by the runtime, the response needed repair before it would parse.
Losing them means losing the explanation for a result.
"""

from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ExecutionLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "execution_logs"
    __table_args__ = (
        Index("ix_execution_logs_execution_sequence", "execution_id", "sequence"),
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    #: Ordering within the execution; wall-clock timestamps collide at this
    #: resolution and cannot be relied on to reconstruct the sequence.
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    #: Which part of the pipeline emitted it: prompt, provider, validation…
    stage: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    execution = relationship("Execution", back_populates="logs")
