"""Name the distinct frozen prompt setups, and point executions at them.

Revision ID: 0007_prompt_configurations
Revises: 0006_emg_context_block

An execution already recorded which version of each frozen block it used, and
already carried ``frozen_context_sha256``. What was missing was an identity for
the *combination*, so "how many prompt setups have I tried, and what did each
produce?" meant grouping on three foreign keys by hand.

Rows are deduplicated on the digest. Three runs under two distinct setups leave
two rows; returning to an earlier setup reuses the row it created.

The digest is the key rather than the three version ids, on purpose: it is
computed from the text that was actually assembled, so it catches a block edited
in place without a version bump, and an override supplied per request that
points at no artefact at all. Two runs whose ids agree but whose text differs
are not the same configuration.

Existing executions are backfilled from their own recorded digest. That is
sound because the digest was already stored per execution — this migration
groups history that was always there, it does not invent it. Rows predating
`frozen_context_sha256` are left NULL rather than guessed at.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision: str = "0007_prompt_configurations"
down_revision: str | None = "0006_emg_context_block"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_configurations",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("frozen_context_sha256", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("system_prompt_version_id", PgUUID(as_uuid=True),
                  sa.ForeignKey("system_prompt_versions.id", ondelete="SET NULL")),
        sa.Column("technical_context_version_id", PgUUID(as_uuid=True),
                  sa.ForeignKey("technical_context_versions.id", ondelete="SET NULL")),
        sa.Column("emg_context_version_id", PgUUID(as_uuid=True),
                  sa.ForeignKey("emg_context_versions.id", ondelete="SET NULL")),
        sa.Column("system_prompt_version", sa.String(length=32)),
        sa.Column("technical_context_version", sa.String(length=32)),
        sa.Column("emg_context_version", sa.String(length=32)),
        sa.Column("frozen_context_text", sa.Text()),
        sa.Column("first_used_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("frozen_context_sha256",
                            name="uq_prompt_configurations_frozen_context_sha256"),
    )
    op.create_index("ix_prompt_configurations_frozen_context_sha256",
                    "prompt_configurations", ["frozen_context_sha256"])
    op.create_index("ix_prompt_configurations_last_used",
                    "prompt_configurations", ["last_used_at"])

    op.add_column(
        "executions",
        sa.Column("prompt_configuration_id", PgUUID(as_uuid=True),
                  sa.ForeignKey("prompt_configurations.id", ondelete="SET NULL"),
                  nullable=True),
    )
    op.create_index("ix_executions_prompt_configuration_id",
                    "executions", ["prompt_configuration_id"])

    # ── Backfill from history ───────────────────────────────────────────────
    #
    # One configuration per distinct digest already present in `executions`.
    # The label and version strings come from whichever execution used that
    # digest most recently: every execution sharing a digest saw byte-identical
    # blocks, so any of them describes the group correctly, and the newest is
    # the one whose artefact rows are most likely to still exist.
    op.execute("""
        INSERT INTO prompt_configurations (
            id, frozen_context_sha256, label,
            system_prompt_version_id, technical_context_version_id,
            emg_context_version_id,
            system_prompt_version, technical_context_version, emg_context_version,
            first_used_at, last_used_at
        )
        SELECT
            gen_random_uuid(),
            latest.frozen_context_sha256,
            concat(
                'S', coalesce(sp.version, '?'),
                ' · T', coalesce(tc.version, '?'),
                ' · E', coalesce(ec.version, '?')
            ),
            latest.system_prompt_version_id,
            latest.technical_context_version_id,
            latest.emg_context_version_id,
            sp.version, tc.version, ec.version,
            latest.first_used_at,
            latest.last_used_at
        FROM (
            SELECT DISTINCT ON (frozen_context_sha256)
                frozen_context_sha256,
                system_prompt_version_id,
                technical_context_version_id,
                emg_context_version_id,
                min(created_at) OVER (PARTITION BY frozen_context_sha256) AS first_used_at,
                max(created_at) OVER (PARTITION BY frozen_context_sha256) AS last_used_at
            FROM executions
            WHERE frozen_context_sha256 IS NOT NULL
            ORDER BY frozen_context_sha256, created_at DESC
        ) AS latest
        LEFT JOIN system_prompt_versions     sp ON sp.id = latest.system_prompt_version_id
        LEFT JOIN technical_context_versions tc ON tc.id = latest.technical_context_version_id
        LEFT JOIN emg_context_versions       ec ON ec.id = latest.emg_context_version_id
    """)

    op.execute("""
        UPDATE executions e
        SET prompt_configuration_id = pc.id
        FROM prompt_configurations pc
        WHERE pc.frozen_context_sha256 = e.frozen_context_sha256
    """)


def downgrade() -> None:
    op.drop_index("ix_executions_prompt_configuration_id", table_name="executions")
    op.drop_column("executions", "prompt_configuration_id")
    op.drop_index("ix_prompt_configurations_last_used",
                  table_name="prompt_configurations")
    op.drop_index("ix_prompt_configurations_frozen_context_sha256",
                  table_name="prompt_configurations")
    op.drop_table("prompt_configurations")
