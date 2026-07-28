"""Projects: the top-level container for a line of investigation.

An *experiment* pins one set of frozen conditions; a *project* groups the
experiments, prompt work and datasets belonging to a single research question.
Separating them matters for auditing — "who changed this project" is a
different question from "what did this run produce".
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class ProjectStatus(str):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class Project(UUIDMixin, TimestampMixin, Base):
    """A research project."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    research_question: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(24), default=ProjectStatus.ACTIVE, nullable=False, index=True
    )

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    #: Snapshot of the owner's identity at creation time. Survives account
    #: deletion, which an audit trail has to.
    owner_email: Mapped[str | None] = mapped_column(String(320))

    tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    #: Project-level defaults applied to new experiments (limit profile,
    #: handedness, preferred provider…). Free-form so the shape can evolve
    #: without a migration.
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    #: Soft delete. Records are never physically removed: an experiment that
    #: produced published results must remain reconstructible even after the
    #: project it belonged to is retired.
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner = relationship("User", lazy="joined")
    experiments = relationship("Experiment", back_populates="project")
    attachments = relationship(
        "Attachment", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Project {self.slug}>"
