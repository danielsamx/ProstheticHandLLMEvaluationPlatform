"""Suppress the thinking channel, and log every command that moves the hand.

Revision ID: 0008_reasoning_and_movement_log
Revises: 0007_prompt_configurations

``sampling_configurations.disable_reasoning``
    Defaults to true, including for rows that already exist. That is a change in
    behaviour applied retroactively to configurations, and it is the right one:
    a reasoning model on this task can spend its whole token budget deliberating
    and return an empty answer. The same model, same prompt, with thinking off
    answered with a pose; with thinking on it answered `no_action` and an empty
    command list. Leaving existing rows at false would preserve a setting nobody
    chose — it was never a setting, it was the absence of one.

``movement_log``
    Every command that reached the simulator or the prosthesis, whatever
    produced it: a model execution, a manual test from the interface, or a replay
    of a stored movement. Separate from `simulator_movements`, which records the
    pose an execution resolved to; this records the *transmission* — where it
    went, whether it arrived, and what it was.

    The distinction matters for the hardware. A pose that resolved is not a pose
    that was delivered: the link can be closed, or drop mid-session. Without a
    transmission log there is no way to answer "did the hand actually receive
    this?", which is the first question after any unexpected movement.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision: str = "0008_reasoning_and_movement_log"
down_revision: str | None = "0007_prompt_configurations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sampling_configurations",
        sa.Column("disable_reasoning", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
    )

    op.create_table(
        "movement_log",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now(), index=True),

        # What was sent.
        sa.Column("serial_command", sa.String(length=128), nullable=False),
        sa.Column("handedness", sa.String(length=8), nullable=False,
                  server_default="right"),
        sa.Column("actuator_positions", JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("duration_ms", sa.Integer()),

        # Where it came from: "execution", "manual", "replay".
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("execution_id", PgUUID(as_uuid=True),
                  sa.ForeignKey("executions.id", ondelete="SET NULL"), index=True),
        sa.Column("triggered_by_email", sa.String(length=320)),

        # Where it went. Two independent destinations, so two independent
        # outcomes: the simulator always renders, the prosthesis only when a
        # link is open, and either can fail on its own.
        sa.Column("sent_to_simulator", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("sent_to_prosthesis", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("transport", sa.String(length=16)),
        sa.Column("delivery_error", sa.Text()),

        sa.Column("notes", sa.Text()),
    )
    op.create_index("ix_movement_log_source", "movement_log", ["source"])
    op.create_index("ix_movement_log_serial_command", "movement_log",
                    ["serial_command"])

    op.alter_column("sampling_configurations", "disable_reasoning",
                    server_default=None)


def downgrade() -> None:
    op.drop_index("ix_movement_log_serial_command", table_name="movement_log")
    op.drop_index("ix_movement_log_source", table_name="movement_log")
    op.drop_table("movement_log")
    op.drop_column("sampling_configurations", "disable_reasoning")
