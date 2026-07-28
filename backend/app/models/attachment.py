"""Files attached to a project or an execution.

Small payloads (an EMG recording, a calibration note, a plot) are stored inline;
anything larger is referenced by path so the database stays queryable. Every
attachment is content-addressed, so the same file uploaded twice is provably the
same file.
"""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, ForeignKey, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

#: Above this, the bytes live on disk and only the path is stored.
INLINE_LIMIT_BYTES: int = 1_048_576


class Attachment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "attachments"

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), index=True
    )
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )

    filename: Mapped[str] = mapped_column(String(320), nullable=False)
    content_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: SHA-256 of the payload. Deduplicates and proves integrity.
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="file", nullable=False, index=True)

    inline_data: Mapped[bytes | None] = mapped_column(LargeBinary)
    storage_path: Mapped[str | None] = mapped_column(String(1024))

    description: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    uploaded_by_email: Mapped[str | None] = mapped_column(String(320))

    project = relationship("Project", back_populates="attachments")
