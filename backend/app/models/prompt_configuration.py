"""A distinct combination of the three frozen prompt blocks.

An execution already records *which version* of each frozen block it used, and
already carries ``frozen_context_sha256`` — the digest of the three blocks
joined. What it did not have was a name for the combination, so answering "how
many different prompt setups have I tried, and what did each produce?" meant
grouping on three foreign keys by hand and hoping nobody had edited a block's
text without moving its version.

This table gives that combination an identity. Rows are created on demand and
deduplicated on the digest, so running the same setup a hundred times produces
one row, and going back to an earlier setup reuses the row it created rather
than adding a second.

Keyed on the digest and not on the three version ids, deliberately. The digest
is computed from the text that was actually assembled, so it catches a case the
ids cannot: a block edited in place, or an override supplied per request. Two
runs whose ids match but whose text differs are not the same configuration, and
grouping them together would be the quiet kind of wrong.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PromptConfiguration(Base):
    """One distinct frozen context, however many executions used it."""

    __tablename__ = "prompt_configurations"
    __table_args__ = (
        Index("ix_prompt_configurations_last_used", "last_used_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    #: The deduplication key: SHA-256 of system + technical + EMG, joined.
    frozen_context_sha256: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )

    #: A short readable name, derived from the three versions: "S1.0 · T1.0 · E1.0".
    #:
    #: Derived rather than typed. A configuration is not something anyone sets
    #: out to create — it comes into being the first time a particular set of
    #: blocks is run — so asking for a name would mean prompting the researcher
    #: mid-experiment for a label they have no reason to have thought about.
    label: Mapped[str] = mapped_column(String(120), nullable=False)

    system_prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("system_prompt_versions.id", ondelete="SET NULL"),
    )
    technical_context_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("technical_context_versions.id", ondelete="SET NULL"),
    )
    emg_context_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("emg_context_versions.id", ondelete="SET NULL"),
    )

    #: The three version strings as they stood, copied rather than joined.
    #:
    #: The foreign keys can be nulled by a deletion, and an override has no row
    #: to point at in the first place. A configuration that cannot say which
    #: versions it was would be useless in exactly the situation it exists for.
    system_prompt_version: Mapped[str | None] = mapped_column(String(32))
    technical_context_version: Mapped[str | None] = mapped_column(String(32))
    emg_context_version: Mapped[str | None] = mapped_column(String(32))

    #: The assembled text. Stored so a configuration can be read and compared
    #: without joining out to three artefact tables and re-joining them in the
    #: same order the builder used.
    frozen_context_text: Mapped[str | None] = mapped_column(Text)

    first_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    executions = relationship("Execution", back_populates="prompt_configuration")
