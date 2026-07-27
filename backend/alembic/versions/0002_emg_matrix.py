"""EMG stimulus becomes a raw sample matrix

The window used to be eight scalar feature vectors supplied by the caller. It is
now an N x 8 matrix of raw normalised samples, with the features derived from it
by the backend - so the descriptors a model is shown can never disagree with the
signal printed beside them.

Existing rows cannot be migrated: a feature vector does not determine the
waveform it came from. They are dropped rather than back-filled with a fake
matrix, because a synthesised signal masquerading as recorded data would
silently corrupt any analysis that touched it.

Revision ID: 0002_emg_matrix
Revises: 0001_initial
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_emg_matrix"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Executions reference windows; clear both so no execution is left pointing
    # at a stimulus that no longer exists in a usable form.
    op.execute("DELETE FROM executions")
    op.execute("DELETE FROM emg_windows")

    op.alter_column("emg_windows", "channels", new_column_name="features")
    op.add_column(
        "emg_windows",
        sa.Column("samples", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "emg_windows",
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column(
        "emg_windows", "window_ms",
        existing_type=sa.Integer(), type_=sa.Float(),
        existing_nullable=False, postgresql_using="window_ms::double precision",
    )
    op.create_index(
        op.f("ix_emg_windows_sample_count"), "emg_windows", ["sample_count"], unique=False
    )

    op.alter_column("emg_windows", "samples", server_default=None)
    op.alter_column("emg_windows", "sample_count", server_default=None)


def downgrade() -> None:
    op.execute("DELETE FROM executions")
    op.execute("DELETE FROM emg_windows")

    op.drop_index(op.f("ix_emg_windows_sample_count"), table_name="emg_windows")
    op.alter_column(
        "emg_windows", "window_ms",
        existing_type=sa.Float(), type_=sa.Integer(),
        existing_nullable=False, postgresql_using="window_ms::integer",
    )
    op.drop_column("emg_windows", "sample_count")
    op.drop_column("emg_windows", "samples")
    op.alter_column("emg_windows", "features", new_column_name="channels")
