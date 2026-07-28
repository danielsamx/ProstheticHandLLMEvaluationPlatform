"""Projects, audit trail, attachments, per-execution logs and request metadata

Adds the governance layer the platform was missing:

* ``projects``        - the container above experiments
* ``audit_logs``      - append-only record of who did what, with what outcome
* ``attachments``     - files bound to a project, experiment or execution
* ``execution_logs``  - the log lines that belong to the scientific record

and widens ``executions`` so the conditions of a run are queryable as columns
rather than only as JSON: decoding parameters, endpoint, dropped parameters and
the origin of the request (address, agent, session, request id).

Every column added to ``executions`` is nullable or carries a server default, so
the migration is safe against existing rows.

Revision ID: 0003_governance
Revises: 0002_emg_matrix
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_governance"
down_revision: str | None = "0002_emg_matrix"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Columns added to `executions`, as (name, type, extra kwargs).
_EXECUTION_COLUMNS: list[tuple[str, sa.types.TypeEngine, dict]] = [
    ("project_id", postgresql.UUID(as_uuid=True), {}),
    ("triggered_by_email", sa.String(320), {}),
    ("model_key", sa.String(256), {}),
    ("api_base", sa.String(512), {}),
    ("api_flavour", sa.String(32), {}),
    ("temperature", sa.Float(), {}),
    ("top_p", sa.Float(), {}),
    ("top_k", sa.Integer(), {}),
    ("max_tokens", sa.Integer(), {}),
    ("seed", sa.Integer(), {}),
    ("frequency_penalty", sa.Float(), {}),
    ("presence_penalty", sa.Float(), {}),
    ("response_format", sa.String(32), {}),
    ("reasoning_mode", sa.String(32), {}),
    ("client_ip", sa.String(45), {}),
    ("user_agent", sa.String(512), {}),
    ("browser", sa.String(64), {}),
    ("operating_system", sa.String(64), {}),
    ("device_type", sa.String(24), {}),
    ("session_id", sa.String(64), {}),
    ("request_id", sa.String(64), {}),
    ("app_version", sa.String(32), {}),
]

_EXECUTION_JSON_COLUMNS = [
    ("stop_sequences", "'[]'::jsonb"),
    ("custom_parameters", "'{}'::jsonb"),
    ("dropped_parameters", "'[]'::jsonb"),
]

_EXECUTION_INDEXES = [
    ("ix_executions_project_id", "project_id"),
    ("ix_executions_triggered_by_email", "triggered_by_email"),
    ("ix_executions_model_key", "model_key"),
    ("ix_executions_temperature", "temperature"),
    ("ix_executions_session_id", "session_id"),
    ("ix_executions_request_id", "request_id"),
]


def upgrade() -> None:
    # ── New tables ──────────────────────────────────────────────────────────
    op.create_table('projects',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('research_question', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('owner_email', sa.String(length=320), nullable=True),
    sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_projects_owner_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_projects'))
    )
    op.create_index(op.f('ix_projects_created_at'), 'projects', ['created_at'], unique=False)
    op.create_index(op.f('ix_projects_is_deleted'), 'projects', ['is_deleted'], unique=False)
    op.create_index(op.f('ix_projects_name'), 'projects', ['name'], unique=False)
    op.create_index(op.f('ix_projects_owner_id'), 'projects', ['owner_id'], unique=False)
    op.create_index(op.f('ix_projects_slug'), 'projects', ['slug'], unique=True)
    op.create_index(op.f('ix_projects_status'), 'projects', ['status'], unique=False)
    op.create_table('attachments',
    sa.Column('project_id', sa.UUID(), nullable=True),
    sa.Column('execution_id', sa.UUID(), nullable=True),
    sa.Column('experiment_id', sa.UUID(), nullable=True),
    sa.Column('filename', sa.String(length=320), nullable=False),
    sa.Column('content_type', sa.String(length=160), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('checksum', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('inline_data', sa.LargeBinary(), nullable=True),
    sa.Column('storage_path', sa.String(length=1024), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('uploaded_by_id', sa.UUID(), nullable=True),
    sa.Column('uploaded_by_email', sa.String(length=320), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], name=op.f('fk_attachments_execution_id_executions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['experiment_id'], ['experiments.id'], name=op.f('fk_attachments_experiment_id_experiments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_attachments_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], name=op.f('fk_attachments_uploaded_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attachments'))
    )
    op.create_index(op.f('ix_attachments_checksum'), 'attachments', ['checksum'], unique=False)
    op.create_index(op.f('ix_attachments_created_at'), 'attachments', ['created_at'], unique=False)
    op.create_index(op.f('ix_attachments_execution_id'), 'attachments', ['execution_id'], unique=False)
    op.create_index(op.f('ix_attachments_experiment_id'), 'attachments', ['experiment_id'], unique=False)
    op.create_index(op.f('ix_attachments_kind'), 'attachments', ['kind'], unique=False)
    op.create_index(op.f('ix_attachments_project_id'), 'attachments', ['project_id'], unique=False)
    op.create_table('audit_logs',
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('actor_email', sa.String(length=320), nullable=True),
    sa.Column('actor_role', sa.String(length=32), nullable=True),
    sa.Column('action', sa.String(length=48), nullable=False),
    sa.Column('outcome', sa.String(length=16), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('entity_type', sa.String(length=48), nullable=True),
    sa.Column('entity_id', sa.UUID(), nullable=True),
    sa.Column('entity_label', sa.String(length=320), nullable=True),
    sa.Column('project_id', sa.UUID(), nullable=True),
    sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('client_ip', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.String(length=512), nullable=True),
    sa.Column('browser', sa.String(length=64), nullable=True),
    sa.Column('operating_system', sa.String(length=64), nullable=True),
    sa.Column('device_type', sa.String(length=24), nullable=True),
    sa.Column('session_id', sa.String(length=64), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('http_method', sa.String(length=8), nullable=True),
    sa.Column('http_path', sa.String(length=512), nullable=True),
    sa.Column('http_status', sa.Integer(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_audit_logs_actor_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_audit_logs_project_id_projects'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index('ix_audit_logs_action_created', 'audit_logs', ['action', 'created_at'], unique=False)
    op.create_index('ix_audit_logs_actor_created', 'audit_logs', ['actor_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_actor_email'), 'audit_logs', ['actor_email'], unique=False)
    op.create_index(op.f('ix_audit_logs_actor_id'), 'audit_logs', ['actor_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_client_ip'), 'audit_logs', ['client_ip'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index('ix_audit_logs_entity', 'audit_logs', ['entity_type', 'entity_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_id'), 'audit_logs', ['entity_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_type'), 'audit_logs', ['entity_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_outcome'), 'audit_logs', ['outcome'], unique=False)
    op.create_index(op.f('ix_audit_logs_project_id'), 'audit_logs', ['project_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_request_id'), 'audit_logs', ['request_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_session_id'), 'audit_logs', ['session_id'], unique=False)
    op.create_table('execution_logs',
    sa.Column('execution_id', sa.UUID(), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('stage', sa.String(length=32), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], name=op.f('fk_execution_logs_execution_id_executions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_execution_logs'))
    )
    op.create_index(op.f('ix_execution_logs_created_at'), 'execution_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_execution_logs_execution_id'), 'execution_logs', ['execution_id'], unique=False)
    op.create_index('ix_execution_logs_execution_sequence', 'execution_logs', ['execution_id', 'sequence'], unique=False)
    op.create_index(op.f('ix_execution_logs_level'), 'execution_logs', ['level'], unique=False)
    op.create_index(op.f('ix_execution_logs_stage'), 'execution_logs', ['stage'], unique=False)
    

    # ── executions: conditions and origin as first-class columns ────────────
    for name, column_type, kwargs in _EXECUTION_COLUMNS:
        op.add_column("executions", sa.Column(name, column_type, nullable=True, **kwargs))

    for name, default in _EXECUTION_JSON_COLUMNS:
        op.add_column(
            "executions",
            sa.Column(
                name,
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text(default),
            ),
        )

    op.add_column(
        "executions",
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
    )

    for index_name, column in _EXECUTION_INDEXES:
        op.create_index(index_name, "executions", [column], unique=False)

    op.create_foreign_key(
        "fk_executions_project_id_projects", "executions", "projects",
        ["project_id"], ["id"], ondelete="SET NULL",
    )

    # ── experiments belong to a project ─────────────────────────────────────
    op.add_column(
        "experiments",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_experiments_project_id", "experiments", ["project_id"], unique=False)
    op.create_foreign_key(
        "fk_experiments_project_id_projects", "experiments", "projects",
        ["project_id"], ["id"], ondelete="SET NULL",
    )

    # Server defaults were only needed to backfill existing rows; drop them so
    # the application layer stays the single source of default values.
    for name, _ in _EXECUTION_JSON_COLUMNS:
        op.alter_column("executions", name, server_default=None)
    op.alter_column("executions", "warning_count", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_experiments_project_id_projects", "experiments", type_="foreignkey")
    op.drop_index("ix_experiments_project_id", table_name="experiments")
    op.drop_column("experiments", "project_id")

    op.drop_constraint("fk_executions_project_id_projects", "executions", type_="foreignkey")
    for index_name, _ in _EXECUTION_INDEXES:
        op.drop_index(index_name, table_name="executions")

    op.drop_column("executions", "warning_count")
    for name, _ in _EXECUTION_JSON_COLUMNS:
        op.drop_column("executions", name)
    for name, _, _ in _EXECUTION_COLUMNS:
        op.drop_column("executions", name)

    op.drop_table("execution_logs")
    op.drop_table("audit_logs")
    op.drop_table("attachments")
    op.drop_table("projects")
