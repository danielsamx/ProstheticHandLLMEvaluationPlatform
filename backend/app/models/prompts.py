"""Versioned prompt artefacts.

The scientific design hinges on these being immutable once used: an execution
references a specific version row, so any published result can be reproduced
byte for byte.  Editing a prompt in the UI creates a NEW version rather than
mutating the existing one.
"""

from __future__ import annotations

import uuid

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class _PromptArtefact(UUIDMixin, TimestampMixin):
    """Shared columns for every versioned prompt block."""

    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    #: SHA-256 of ``content``. Two executions with the same digest provably saw
    #: identical text, regardless of which row they pointed at.
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_system_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SystemPromptVersion(_PromptArtefact, Base):
    """Block 1 - behaviour contract."""

    __tablename__ = "system_prompt_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_system_prompt_versions_name"),)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    executions = relationship("Execution", back_populates="system_prompt_version")


class TechnicalContextVersion(_PromptArtefact, Base):
    """Block 2 - hardware description.

    ``limit_profile`` records which mechanical envelope the text describes, so a
    context can never be paired with a validator that contradicts it.
    ``generated_from_domain`` marks the auto-generated baseline; hand-edited
    versions set it to False.
    """

    __tablename__ = "technical_context_versions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_technical_context_versions_name"),
    )

    limit_profile: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    generated_from_domain: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    includes_json_schema: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    executions = relationship("Execution", back_populates="technical_context_version")


class DynamicPromptTemplate(_PromptArtefact, Base):
    """Block 3 - the per-execution EMG rendering template."""

    __tablename__ = "dynamic_prompt_templates"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_dynamic_prompt_templates_name"),
    )

    include_channel_sites: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_extended_features: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Placeholder names the template consumes, for UI validation.
    required_placeholders: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    executions = relationship("Execution", back_populates="dynamic_prompt_template")


class LabPreset(UUIDMixin, TimestampMixin, Base):
    """A one-click bundle of everything the left panel needs.

    This is what the "reusable configuration history" list is built from:
    model + sampling configuration + the three prompt versions + hand + limit
    profile, saved under a name and replayable verbatim.
    """

    __tablename__ = "lab_presets"

    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    sampling_configuration_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sampling_configurations.id", ondelete="CASCADE"),
        nullable=False,
    )
    system_prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("system_prompt_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    technical_context_version_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("technical_context_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dynamic_prompt_template_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("dynamic_prompt_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )

    handedness: Mapped[str] = mapped_column(String(8), default="right", nullable=False)
    limit_profile: Mapped[str] = mapped_column(String(32), nullable=False)
    merge_context_into_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sampling_configuration = relationship("SamplingConfiguration", lazy="joined")
