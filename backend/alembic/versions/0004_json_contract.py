"""Restore the structured JSON response contract.

Revision ID: 0004_json_contract
Revises: 0003_governance

The model returns a JSON object again rather than a bare command line, so the
validation pipeline gains back the two stages that compare the response against
itself: `schema` and `consistency`. This migration adds the column that records
whether the second one passed.

Existing rows are backfilled to NULL rather than to false. Those executions ran
under a contract where the question "did the serial_command agree with the
structure beside it?" had no meaning — there was no structure. Writing false
would assert they failed a check that never ran; NULL says the check does not
apply, which is the only honest value and keeps the accuracy statistics from
silently absorbing a cohort of fabricated failures.

`prompt_variant_metrics` is left alone: it aggregates over executions, and a
stage that only some of them were subject to should be counted from the source
rows rather than duplicated into a summary.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004_json_contract"
down_revision: str | None = "0003_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "execution_metrics",
        sa.Column(
            "consistency_compliant",
            sa.Boolean(),
            nullable=True,
            comment=(
                "The serial_command agreed with the intent, gesture and commands "
                "stated beside it. NULL for executions that predate the JSON "
                "contract, where the response carried only one representation."
            ),
        ),
    )
    op.create_index(
        "ix_execution_metrics_consistency_compliant",
        "execution_metrics",
        ["consistency_compliant"],
    )

    # Sampling configurations saved under the bare-command contract carry
    # max_tokens=64, which was generous for a two-character reply and is far too
    # small for a JSON object. A truncated response is indistinguishable from a
    # malformed one in the metrics, so leaving these rows alone would record a
    # budget mistake as the model's failure — on every run, silently.
    #
    # Only the old default is touched. A researcher who deliberately set 96 or
    # 150 chose it, and overwriting a deliberate value would be worse than the
    # problem being fixed.
    op.execute(
        "UPDATE sampling_configurations SET max_tokens = 320 WHERE max_tokens = 64"
    )


def downgrade() -> None:
    op.drop_index("ix_execution_metrics_consistency_compliant",
                  table_name="execution_metrics")
    op.drop_column("execution_metrics", "consistency_compliant")
