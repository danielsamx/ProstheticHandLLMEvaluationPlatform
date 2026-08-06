"""Authentication roles and gesture feedback.

Revision ID: 0009_auth_myo_feedback
Revises: 0008_reasoning_and_movement_log
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_auth_myo_feedback"
down_revision = "0008_reasoning_and_movement_log"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gesture_feedback",
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluator_email", sa.String(320)),
        sa.Column("source", sa.String(24), nullable=False, server_default="human"),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Integer()),
        sa.Column("expected_gesture", sa.String(64)),
        sa.Column("observed_gesture", sa.String(64)),
        sa.Column("notes", sa.Text()),
        sa.Column("sensor_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("correction_attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correction_execution_id", postgresql.UUID(as_uuid=True)),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluator_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["correction_execution_id"], ["executions.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_gesture_feedback_execution_id", "gesture_feedback", ["execution_id"])
    op.create_index("ix_gesture_feedback_evaluator_id", "gesture_feedback", ["evaluator_id"])
    op.create_index("ix_gesture_feedback_is_correct", "gesture_feedback", ["is_correct"])
    op.execute("UPDATE users SET role='intern' WHERE role='viewer'")


def downgrade():
    op.execute("UPDATE users SET role='viewer' WHERE role='intern'")
    op.drop_table("gesture_feedback")
