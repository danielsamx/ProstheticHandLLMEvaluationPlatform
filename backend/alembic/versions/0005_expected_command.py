"""Expected command, and the dynamic block's content as a recorded variable.

Revision ID: 0005_expected_command
Revises: 0004_json_contract

Three additions, all of them things that were previously either implicit or
absent from the record:

``executions.expected_serial_command``
    What a domain expert says the window should have produced. Stored on the
    execution and not joined from the EMG window: a window's label can be
    corrected later, and reading the comparison through a foreign key would let
    one correction silently rewrite the recorded accuracy of every run that had
    ever used it. An execution must remain a fixed account of what was expected
    at the time it ran.

``executions.dynamic_content`` / ``executions.matrix_rows_sent``
    Which rendering of the EMG reached the model, and how much of it. Runs that
    saw the raw matrix and runs that saw only the derived descriptors are not
    comparable, and neither are a 404-row run and a 32-row one. Without these
    columns the difference is invisible in the record and the two get averaged
    together.

``execution_metrics.command_matches_expected``
    Nullable on purpose. NULL means "no expected command was given", which is a
    different fact from `false` meaning "compared and wrong". Collapsing them
    would let unlabelled runs drag an accuracy figure down while never
    appearing in its denominator.

Existing rows are backfilled to 'matrix' for `dynamic_content`, which is what
they in fact used, and left NULL everywhere a value would have to be invented.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005_expected_command"
down_revision: str | None = "0004_json_contract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "executions",
        sa.Column("expected_serial_command", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "executions",
        sa.Column(
            "dynamic_content",
            sa.String(length=16),
            nullable=False,
            server_default="matrix",
        ),
    )
    op.add_column(
        "executions",
        sa.Column("matrix_rows_sent", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_executions_expected_serial_command",
        "executions",
        ["expected_serial_command"],
    )

    op.add_column(
        "execution_metrics",
        sa.Column("command_matches_expected", sa.Boolean(), nullable=True),
    )
    op.create_index(
        "ix_execution_metrics_command_matches_expected",
        "execution_metrics",
        ["command_matches_expected"],
    )

    # The server default did its job on the existing rows; drop it so the
    # application stays the single authority on what a new row means. Leaving it
    # in place would let an insert that forgot the column succeed silently and
    # claim a mode it never ran.
    op.alter_column("executions", "dynamic_content", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_execution_metrics_command_matches_expected",
                  table_name="execution_metrics")
    op.drop_column("execution_metrics", "command_matches_expected")
    op.drop_index("ix_executions_expected_serial_command", table_name="executions")
    op.drop_column("executions", "matrix_rows_sent")
    op.drop_column("executions", "dynamic_content")
    op.drop_column("executions", "expected_serial_command")
