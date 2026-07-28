"""A fourth prompt block: the EMG knowledge context.

Revision ID: 0006_emg_context_block
Revises: 0005_expected_command

The prompt was three blocks: behaviour, hardware, stimulus. It is now four,
with EMG interpretation guidance separated out of the hardware description.

The separation is the point of the migration. "What can this hand do?" is a
fact about hardware that changes only when the hardware does. "How should EMG
be interpreted — is co-contraction a stop, or physiological coactivation?" is a
methodological position a researcher will revise repeatedly, and each revision
is an experiment. Sharing one artefact meant every experiment on the second
question also reversioned the first, and the two effects could never be
attributed apart.

`frozen_context_sha256` now covers all three frozen blocks rather than two.
Existing rows keep their old hash, which was computed over a different set of
blocks and therefore cannot collide with any new one. That is the correct
outcome: runs from before the split saw different constants, so they are not
comparable with runs from after it, and the hash saying so is the mechanism
working rather than data being lost.

Nothing is backfilled into `emg_context_text`. Those executions genuinely had
no such block, and inventing one would put text in the record that no model
ever read.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision: str = "0006_emg_context_block"
down_revision: str | None = "0005_expected_command"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emg_context_versions",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False, index=True),
        sa.Column("description", sa.Text()),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_system_default", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("generated_from_domain", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("extra", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_id", PgUUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("name", "version", name="uq_emg_context_versions_name"),
    )

    op.add_column(
        "executions",
        sa.Column("emg_context_version_id", PgUUID(as_uuid=True),
                  sa.ForeignKey("emg_context_versions.id", ondelete="SET NULL"),
                  nullable=True),
    )
    op.add_column("executions", sa.Column("emg_context_text", sa.Text(), nullable=True))
    op.add_column(
        "executions",
        sa.Column("emg_context_sha256", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("executions", "emg_context_sha256")
    op.drop_column("executions", "emg_context_text")
    op.drop_column("executions", "emg_context_version_id")
    op.drop_table("emg_context_versions")
