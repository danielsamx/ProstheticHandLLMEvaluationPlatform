"""Add missing feedback timestamp defaults.

Revision ID: 0010_feedback_timestamp_defaults
Revises: 0009_auth_myo_feedback
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_feedback_timestamp_defaults"
down_revision = "0009_auth_myo_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "gesture_feedback", "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.alter_column(
        "gesture_feedback", "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "gesture_feedback", "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "gesture_feedback", "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
