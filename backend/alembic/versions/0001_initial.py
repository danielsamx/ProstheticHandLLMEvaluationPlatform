"""Initial schema - Prosthetic Hand LLM Evaluation Platform

Creates the full relational model: users, LLM providers/models/configurations,
versioned prompt artefacts, EMG windows, experiments, executions, validation
results and issues, execution errors, metrics and simulator movements.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### auto-generated from app.models metadata ###
    op.create_table('emg_windows',
    sa.Column('source_mode', sa.String(length=16), nullable=False),
    sa.Column('window_ms', sa.Integer(), nullable=False),
    sa.Column('sample_rate_hz', sa.Integer(), nullable=False),
    sa.Column('channels', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('mean_rms', sa.Float(), nullable=False),
    sa.Column('ground_truth_gesture', sa.String(length=32), nullable=True),
    sa.Column('subject_ref', sa.String(length=64), nullable=True),
    sa.Column('session_id', sa.String(length=64), nullable=True),
    sa.Column('sequence', sa.Integer(), nullable=True),
    sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('checksum', sa.String(length=64), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_emg_windows'))
    )
    op.create_index(op.f('ix_emg_windows_checksum'), 'emg_windows', ['checksum'], unique=False)
    op.create_index(op.f('ix_emg_windows_created_at'), 'emg_windows', ['created_at'], unique=False)
    op.create_index(op.f('ix_emg_windows_ground_truth_gesture'), 'emg_windows', ['ground_truth_gesture'], unique=False)
    op.create_index(op.f('ix_emg_windows_mean_rms'), 'emg_windows', ['mean_rms'], unique=False)
    op.create_index(op.f('ix_emg_windows_session_id'), 'emg_windows', ['session_id'], unique=False)
    op.create_index(op.f('ix_emg_windows_source_mode'), 'emg_windows', ['source_mode'], unique=False)
    op.create_index(op.f('ix_emg_windows_subject_ref'), 'emg_windows', ['subject_ref'], unique=False)
    op.create_table('llm_providers',
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('display_name', sa.String(length=128), nullable=False),
    sa.Column('litellm_prefix', sa.String(length=64), nullable=False),
    sa.Column('api_base', sa.String(length=512), nullable=True),
    sa.Column('api_key_env_var', sa.String(length=128), nullable=True),
    sa.Column('requires_api_key', sa.Boolean(), nullable=False),
    sa.Column('is_local', sa.Boolean(), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_llm_providers'))
    )
    op.create_index(op.f('ix_llm_providers_created_at'), 'llm_providers', ['created_at'], unique=False)
    op.create_index(op.f('ix_llm_providers_slug'), 'llm_providers', ['slug'], unique=True)
    op.create_table('users',
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=True),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('institution', sa.String(length=200), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index(op.f('ix_users_created_at'), 'users', ['created_at'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('dynamic_prompt_templates',
    sa.Column('include_channel_sites', sa.Boolean(), nullable=False),
    sa.Column('include_extended_features', sa.Boolean(), nullable=False),
    sa.Column('required_placeholders', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('version', sa.String(length=32), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_sha256', sa.String(length=64), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_system_default', sa.Boolean(), nullable=False),
    sa.Column('char_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_dynamic_prompt_templates_created_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dynamic_prompt_templates')),
    sa.UniqueConstraint('name', 'version', name='uq_dynamic_prompt_templates_name')
    )
    op.create_index(op.f('ix_dynamic_prompt_templates_content_sha256'), 'dynamic_prompt_templates', ['content_sha256'], unique=False)
    op.create_index(op.f('ix_dynamic_prompt_templates_created_at'), 'dynamic_prompt_templates', ['created_at'], unique=False)
    op.create_index(op.f('ix_dynamic_prompt_templates_name'), 'dynamic_prompt_templates', ['name'], unique=False)
    op.create_table('llm_models',
    sa.Column('provider_id', sa.UUID(), nullable=False),
    sa.Column('model_key', sa.String(length=256), nullable=False),
    sa.Column('display_name', sa.String(length=256), nullable=False),
    sa.Column('family', sa.String(length=64), nullable=True),
    sa.Column('parameter_count_b', sa.Float(), nullable=True),
    sa.Column('quantisation', sa.String(length=32), nullable=True),
    sa.Column('context_window', sa.Integer(), nullable=True),
    sa.Column('max_output_tokens', sa.Integer(), nullable=True),
    sa.Column('supports_json_mode', sa.Boolean(), nullable=False),
    sa.Column('supports_json_schema', sa.Boolean(), nullable=False),
    sa.Column('supports_seed', sa.Boolean(), nullable=False),
    sa.Column('supports_top_k', sa.Boolean(), nullable=False),
    sa.Column('supports_penalties', sa.Boolean(), nullable=False),
    sa.Column('input_cost_per_1k', sa.Numeric(precision=12, scale=8), nullable=False),
    sa.Column('output_cost_per_1k', sa.Numeric(precision=12, scale=8), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['provider_id'], ['llm_providers.id'], name=op.f('fk_llm_models_provider_id_llm_providers'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_llm_models')),
    sa.UniqueConstraint('provider_id', 'model_key', name='uq_llm_models_provider_model_key')
    )
    op.create_index(op.f('ix_llm_models_created_at'), 'llm_models', ['created_at'], unique=False)
    op.create_index(op.f('ix_llm_models_provider_id'), 'llm_models', ['provider_id'], unique=False)
    op.create_table('system_prompt_versions',
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('version', sa.String(length=32), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_sha256', sa.String(length=64), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_system_default', sa.Boolean(), nullable=False),
    sa.Column('char_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_system_prompt_versions_created_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_system_prompt_versions')),
    sa.UniqueConstraint('name', 'version', name='uq_system_prompt_versions_name')
    )
    op.create_index(op.f('ix_system_prompt_versions_content_sha256'), 'system_prompt_versions', ['content_sha256'], unique=False)
    op.create_index(op.f('ix_system_prompt_versions_created_at'), 'system_prompt_versions', ['created_at'], unique=False)
    op.create_index(op.f('ix_system_prompt_versions_name'), 'system_prompt_versions', ['name'], unique=False)
    op.create_table('technical_context_versions',
    sa.Column('limit_profile', sa.String(length=32), nullable=False),
    sa.Column('generated_from_domain', sa.Boolean(), nullable=False),
    sa.Column('includes_json_schema', sa.Boolean(), nullable=False),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('version', sa.String(length=32), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_sha256', sa.String(length=64), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_system_default', sa.Boolean(), nullable=False),
    sa.Column('char_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_technical_context_versions_created_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_technical_context_versions')),
    sa.UniqueConstraint('name', 'version', name='uq_technical_context_versions_name')
    )
    op.create_index(op.f('ix_technical_context_versions_content_sha256'), 'technical_context_versions', ['content_sha256'], unique=False)
    op.create_index(op.f('ix_technical_context_versions_created_at'), 'technical_context_versions', ['created_at'], unique=False)
    op.create_index(op.f('ix_technical_context_versions_limit_profile'), 'technical_context_versions', ['limit_profile'], unique=False)
    op.create_index(op.f('ix_technical_context_versions_name'), 'technical_context_versions', ['name'], unique=False)
    op.create_table('experiments',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('hypothesis', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('system_prompt_version_id', sa.UUID(), nullable=True),
    sa.Column('technical_context_version_id', sa.UUID(), nullable=True),
    sa.Column('dynamic_prompt_template_id', sa.UUID(), nullable=True),
    sa.Column('limit_profile', sa.String(length=32), nullable=False),
    sa.Column('handedness', sa.String(length=8), nullable=False),
    sa.Column('frozen_context_sha256', sa.String(length=64), nullable=True),
    sa.Column('repetitions_per_condition', sa.Integer(), nullable=False),
    sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['dynamic_prompt_template_id'], ['dynamic_prompt_templates.id'], name=op.f('fk_experiments_dynamic_prompt_template_id_dynamic_prompt_templates'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_experiments_owner_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['system_prompt_version_id'], ['system_prompt_versions.id'], name=op.f('fk_experiments_system_prompt_version_id_system_prompt_versions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['technical_context_version_id'], ['technical_context_versions.id'], name=op.f('fk_experiments_technical_context_version_id_technical_context_versions'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_experiments'))
    )
    op.create_index(op.f('ix_experiments_created_at'), 'experiments', ['created_at'], unique=False)
    op.create_index(op.f('ix_experiments_frozen_context_sha256'), 'experiments', ['frozen_context_sha256'], unique=False)
    op.create_index(op.f('ix_experiments_name'), 'experiments', ['name'], unique=False)
    op.create_index(op.f('ix_experiments_owner_id'), 'experiments', ['owner_id'], unique=False)
    op.create_index(op.f('ix_experiments_status'), 'experiments', ['status'], unique=False)
    op.create_table('sampling_configurations',
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('model_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('temperature', sa.Float(), nullable=False),
    sa.Column('top_p', sa.Float(), nullable=False),
    sa.Column('top_k', sa.Integer(), nullable=True),
    sa.Column('max_tokens', sa.Integer(), nullable=False),
    sa.Column('seed', sa.Integer(), nullable=True),
    sa.Column('frequency_penalty', sa.Float(), nullable=False),
    sa.Column('presence_penalty', sa.Float(), nullable=False),
    sa.Column('stop_sequences', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('response_format', sa.String(length=32), nullable=False),
    sa.Column('extra_params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_favorite', sa.Boolean(), nullable=False),
    sa.Column('use_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('max_tokens > 0', name=op.f('ck_sampling_configurations_max_tokens_positive')),
    sa.CheckConstraint('temperature >= 0 AND temperature <= 2', name=op.f('ck_sampling_configurations_temperature_range')),
    sa.CheckConstraint('top_p > 0 AND top_p <= 1', name=op.f('ck_sampling_configurations_top_p_range')),
    sa.ForeignKeyConstraint(['model_id'], ['llm_models.id'], name=op.f('fk_sampling_configurations_model_id_llm_models'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_sampling_configurations_owner_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sampling_configurations'))
    )
    op.create_index(op.f('ix_sampling_configurations_created_at'), 'sampling_configurations', ['created_at'], unique=False)
    op.create_index(op.f('ix_sampling_configurations_model_id'), 'sampling_configurations', ['model_id'], unique=False)
    op.create_index(op.f('ix_sampling_configurations_name'), 'sampling_configurations', ['name'], unique=False)
    op.create_index(op.f('ix_sampling_configurations_owner_id'), 'sampling_configurations', ['owner_id'], unique=False)
    op.create_table('emg_stream_sessions',
    sa.Column('session_key', sa.String(length=64), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('experiment_id', sa.UUID(), nullable=True),
    sa.Column('device_label', sa.String(length=160), nullable=True),
    sa.Column('subject_ref', sa.String(length=64), nullable=True),
    sa.Column('frames_received', sa.Integer(), nullable=False),
    sa.Column('executions_triggered', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['experiment_id'], ['experiments.id'], name=op.f('fk_emg_stream_sessions_experiment_id_experiments'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_emg_stream_sessions_owner_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_emg_stream_sessions'))
    )
    op.create_index(op.f('ix_emg_stream_sessions_created_at'), 'emg_stream_sessions', ['created_at'], unique=False)
    op.create_index(op.f('ix_emg_stream_sessions_experiment_id'), 'emg_stream_sessions', ['experiment_id'], unique=False)
    op.create_index(op.f('ix_emg_stream_sessions_session_key'), 'emg_stream_sessions', ['session_key'], unique=True)
    op.create_table('executions',
    sa.Column('experiment_id', sa.UUID(), nullable=True),
    sa.Column('triggered_by_id', sa.UUID(), nullable=True),
    sa.Column('repetition_index', sa.Integer(), nullable=False),
    sa.Column('llm_model_id', sa.UUID(), nullable=True),
    sa.Column('sampling_configuration_id', sa.UUID(), nullable=True),
    sa.Column('system_prompt_version_id', sa.UUID(), nullable=True),
    sa.Column('technical_context_version_id', sa.UUID(), nullable=True),
    sa.Column('dynamic_prompt_template_id', sa.UUID(), nullable=True),
    sa.Column('emg_window_id', sa.UUID(), nullable=True),
    sa.Column('model_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('litellm_model', sa.String(length=320), nullable=True),
    sa.Column('provider_slug', sa.String(length=64), nullable=True),
    sa.Column('handedness', sa.String(length=8), nullable=False),
    sa.Column('limit_profile', sa.String(length=32), nullable=False),
    sa.Column('experiment_type', sa.String(length=48), nullable=False),
    sa.Column('system_prompt_text', sa.Text(), nullable=True),
    sa.Column('technical_context_text', sa.Text(), nullable=True),
    sa.Column('dynamic_prompt_text', sa.Text(), nullable=True),
    sa.Column('messages_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('system_prompt_sha256', sa.String(length=64), nullable=True),
    sa.Column('technical_context_sha256', sa.String(length=64), nullable=True),
    sa.Column('dynamic_prompt_sha256', sa.String(length=64), nullable=True),
    sa.Column('frozen_context_sha256', sa.String(length=64), nullable=True),
    sa.Column('full_prompt_sha256', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('raw_response', sa.Text(), nullable=True),
    sa.Column('parsed_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('finish_reason', sa.String(length=48), nullable=True),
    sa.Column('provider_response_id', sa.String(length=160), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('time_to_first_token_ms', sa.Integer(), nullable=True),
    sa.Column('prompt_tokens', sa.Integer(), nullable=True),
    sa.Column('completion_tokens', sa.Integer(), nullable=True),
    sa.Column('total_tokens', sa.Integer(), nullable=True),
    sa.Column('cost_usd', sa.Numeric(precision=14, scale=8), nullable=False),
    sa.Column('tokens_per_second', sa.Float(), nullable=True),
    sa.Column('validation_passed', sa.Boolean(), nullable=True),
    sa.Column('simulator_executed', sa.Boolean(), nullable=False),
    sa.Column('retry_of_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['dynamic_prompt_template_id'], ['dynamic_prompt_templates.id'], name=op.f('fk_executions_dynamic_prompt_template_id_dynamic_prompt_templates'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['emg_window_id'], ['emg_windows.id'], name=op.f('fk_executions_emg_window_id_emg_windows'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['experiment_id'], ['experiments.id'], name=op.f('fk_executions_experiment_id_experiments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['llm_model_id'], ['llm_models.id'], name=op.f('fk_executions_llm_model_id_llm_models'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['retry_of_id'], ['executions.id'], name=op.f('fk_executions_retry_of_id_executions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sampling_configuration_id'], ['sampling_configurations.id'], name=op.f('fk_executions_sampling_configuration_id_sampling_configurations'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['system_prompt_version_id'], ['system_prompt_versions.id'], name=op.f('fk_executions_system_prompt_version_id_system_prompt_versions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['technical_context_version_id'], ['technical_context_versions.id'], name=op.f('fk_executions_technical_context_version_id_technical_context_versions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['triggered_by_id'], ['users.id'], name=op.f('fk_executions_triggered_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_executions'))
    )
    op.create_index(op.f('ix_executions_created_at'), 'executions', ['created_at'], unique=False)
    op.create_index(op.f('ix_executions_emg_window_id'), 'executions', ['emg_window_id'], unique=False)
    op.create_index(op.f('ix_executions_experiment_id'), 'executions', ['experiment_id'], unique=False)
    op.create_index('ix_executions_experiment_status', 'executions', ['experiment_id', 'status'], unique=False)
    op.create_index('ix_executions_frozen_context', 'executions', ['frozen_context_sha256'], unique=False)
    op.create_index(op.f('ix_executions_full_prompt_sha256'), 'executions', ['full_prompt_sha256'], unique=False)
    op.create_index(op.f('ix_executions_latency_ms'), 'executions', ['latency_ms'], unique=False)
    op.create_index(op.f('ix_executions_litellm_model'), 'executions', ['litellm_model'], unique=False)
    op.create_index(op.f('ix_executions_llm_model_id'), 'executions', ['llm_model_id'], unique=False)
    op.create_index('ix_executions_model_created', 'executions', ['llm_model_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_executions_provider_slug'), 'executions', ['provider_slug'], unique=False)
    op.create_index(op.f('ix_executions_status'), 'executions', ['status'], unique=False)
    op.create_index(op.f('ix_executions_validation_passed'), 'executions', ['validation_passed'], unique=False)
    op.create_table('lab_presets',
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('sampling_configuration_id', sa.UUID(), nullable=False),
    sa.Column('system_prompt_version_id', sa.UUID(), nullable=False),
    sa.Column('technical_context_version_id', sa.UUID(), nullable=False),
    sa.Column('dynamic_prompt_template_id', sa.UUID(), nullable=False),
    sa.Column('handedness', sa.String(length=8), nullable=False),
    sa.Column('limit_profile', sa.String(length=32), nullable=False),
    sa.Column('merge_context_into_system', sa.Boolean(), nullable=False),
    sa.Column('is_favorite', sa.Boolean(), nullable=False),
    sa.Column('use_count', sa.Integer(), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['dynamic_prompt_template_id'], ['dynamic_prompt_templates.id'], name=op.f('fk_lab_presets_dynamic_prompt_template_id_dynamic_prompt_templates'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_lab_presets_owner_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sampling_configuration_id'], ['sampling_configurations.id'], name=op.f('fk_lab_presets_sampling_configuration_id_sampling_configurations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['system_prompt_version_id'], ['system_prompt_versions.id'], name=op.f('fk_lab_presets_system_prompt_version_id_system_prompt_versions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['technical_context_version_id'], ['technical_context_versions.id'], name=op.f('fk_lab_presets_technical_context_version_id_technical_context_versions'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lab_presets'))
    )
    op.create_index(op.f('ix_lab_presets_created_at'), 'lab_presets', ['created_at'], unique=False)
    op.create_index(op.f('ix_lab_presets_name'), 'lab_presets', ['name'], unique=False)
    op.create_index(op.f('ix_lab_presets_owner_id'), 'lab_presets', ['owner_id'], unique=False)
    op.create_table('execution_errors',
    sa.Column('execution_id', sa.UUID(), nullable=False),
    sa.Column('category', sa.String(length=24), nullable=False),
    sa.Column('error_type', sa.String(length=160), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('provider_status_code', sa.Integer(), nullable=True),
    sa.Column('provider_error_code', sa.String(length=96), nullable=True),
    sa.Column('is_retryable', sa.Boolean(), nullable=False),
    sa.Column('traceback', sa.Text(), nullable=True),
    sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], name=op.f('fk_execution_errors_execution_id_executions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_execution_errors'))
    )
    op.create_index(op.f('ix_execution_errors_category'), 'execution_errors', ['category'], unique=False)
    op.create_index(op.f('ix_execution_errors_created_at'), 'execution_errors', ['created_at'], unique=False)
    op.create_index(op.f('ix_execution_errors_execution_id'), 'execution_errors', ['execution_id'], unique=False)
    op.create_table('execution_metrics',
    sa.Column('execution_id', sa.UUID(), nullable=False),
    sa.Column('is_valid_json', sa.Boolean(), nullable=False),
    sa.Column('is_bare_json', sa.Boolean(), nullable=False),
    sa.Column('schema_compliant', sa.Boolean(), nullable=False),
    sa.Column('protocol_compliant', sa.Boolean(), nullable=False),
    sa.Column('within_mechanical_limits', sa.Boolean(), nullable=False),
    sa.Column('safety_compliant', sa.Boolean(), nullable=False),
    sa.Column('ground_truth_gesture', sa.String(length=32), nullable=True),
    sa.Column('predicted_gesture', sa.String(length=32), nullable=True),
    sa.Column('gesture_correct', sa.Boolean(), nullable=True),
    sa.Column('detected_pattern', sa.String(length=64), nullable=True),
    sa.Column('pose_mae', sa.Float(), nullable=True),
    sa.Column('pose_similarity', sa.Float(), nullable=True),
    sa.Column('model_confidence', sa.Float(), nullable=True),
    sa.Column('calibration_error', sa.Float(), nullable=True),
    sa.Column('actuators_commanded', sa.Integer(), nullable=False),
    sa.Column('intent', sa.String(length=24), nullable=True),
    sa.Column('used_preset_gesture', sa.Boolean(), nullable=False),
    sa.Column('refused_to_act', sa.Boolean(), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('tokens_per_second', sa.Float(), nullable=True),
    sa.Column('cost_usd', sa.Numeric(precision=14, scale=8), nullable=False),
    sa.Column('output_token_efficiency', sa.Float(), nullable=True),
    sa.Column('response_fingerprint', sa.String(length=64), nullable=True),
    sa.Column('repetition_group', sa.String(length=64), nullable=True),
    sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], name=op.f('fk_execution_metrics_execution_id_executions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_execution_metrics'))
    )
    op.create_index(op.f('ix_execution_metrics_created_at'), 'execution_metrics', ['created_at'], unique=False)
    op.create_index(op.f('ix_execution_metrics_detected_pattern'), 'execution_metrics', ['detected_pattern'], unique=False)
    op.create_index(op.f('ix_execution_metrics_execution_id'), 'execution_metrics', ['execution_id'], unique=True)
    op.create_index(op.f('ix_execution_metrics_gesture_correct'), 'execution_metrics', ['gesture_correct'], unique=False)
    op.create_index(op.f('ix_execution_metrics_ground_truth_gesture'), 'execution_metrics', ['ground_truth_gesture'], unique=False)
    op.create_index(op.f('ix_execution_metrics_intent'), 'execution_metrics', ['intent'], unique=False)
    op.create_index(op.f('ix_execution_metrics_predicted_gesture'), 'execution_metrics', ['predicted_gesture'], unique=False)
    op.create_index(op.f('ix_execution_metrics_repetition_group'), 'execution_metrics', ['repetition_group'], unique=False)
    op.create_index(op.f('ix_execution_metrics_response_fingerprint'), 'execution_metrics', ['response_fingerprint'], unique=False)
    op.create_table('simulator_movements',
    sa.Column('execution_id', sa.UUID(), nullable=False),
    sa.Column('handedness', sa.String(length=8), nullable=False),
    sa.Column('limit_profile', sa.String(length=32), nullable=False),
    sa.Column('source', sa.String(length=48), nullable=False),
    sa.Column('serial_command', sa.String(length=160), nullable=True),
    sa.Column('actuator_positions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('actuator_normalised', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('joint_angles', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('was_rendered', sa.Boolean(), nullable=False),
    sa.Column('dispatched_to_hardware', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], name=op.f('fk_simulator_movements_execution_id_executions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_simulator_movements'))
    )
    op.create_index(op.f('ix_simulator_movements_created_at'), 'simulator_movements', ['created_at'], unique=False)
    op.create_index(op.f('ix_simulator_movements_execution_id'), 'simulator_movements', ['execution_id'], unique=True)
    op.create_table('validation_results',
    sa.Column('execution_id', sa.UUID(), nullable=False),
    sa.Column('passed', sa.Boolean(), nullable=False),
    sa.Column('limit_profile', sa.String(length=32), nullable=False),
    sa.Column('failed_stage', sa.String(length=24), nullable=True),
    sa.Column('stages_completed', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error_count', sa.Integer(), nullable=False),
    sa.Column('warning_count', sa.Integer(), nullable=False),
    sa.Column('normalised_serial', sa.String(length=160), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], name=op.f('fk_validation_results_execution_id_executions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_validation_results'))
    )
    op.create_index(op.f('ix_validation_results_created_at'), 'validation_results', ['created_at'], unique=False)
    op.create_index(op.f('ix_validation_results_execution_id'), 'validation_results', ['execution_id'], unique=True)
    op.create_index(op.f('ix_validation_results_failed_stage'), 'validation_results', ['failed_stage'], unique=False)
    op.create_index(op.f('ix_validation_results_passed'), 'validation_results', ['passed'], unique=False)
    op.create_table('validation_issues',
    sa.Column('validation_result_id', sa.UUID(), nullable=False),
    sa.Column('stage', sa.String(length=24), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('field_path', sa.String(length=160), nullable=True),
    sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['validation_result_id'], ['validation_results.id'], name=op.f('fk_validation_issues_validation_result_id_validation_results'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_validation_issues'))
    )
    op.create_index(op.f('ix_validation_issues_code'), 'validation_issues', ['code'], unique=False)
    op.create_index(op.f('ix_validation_issues_created_at'), 'validation_issues', ['created_at'], unique=False)
    op.create_index(op.f('ix_validation_issues_severity'), 'validation_issues', ['severity'], unique=False)
    op.create_index(op.f('ix_validation_issues_stage'), 'validation_issues', ['stage'], unique=False)
    op.create_index(op.f('ix_validation_issues_validation_result_id'), 'validation_issues', ['validation_result_id'], unique=False)
    # ### end Alembic commands ###



def downgrade() -> None:
    # ### auto-generated from app.models metadata ###
    op.drop_index(op.f('ix_validation_issues_code'), table_name='validation_issues')
    op.drop_index(op.f('ix_validation_issues_created_at'), table_name='validation_issues')
    op.drop_index(op.f('ix_validation_issues_severity'), table_name='validation_issues')
    op.drop_index(op.f('ix_validation_issues_stage'), table_name='validation_issues')
    op.drop_index(op.f('ix_validation_issues_validation_result_id'), table_name='validation_issues')
    op.drop_table('validation_issues')
    op.drop_index(op.f('ix_validation_results_created_at'), table_name='validation_results')
    op.drop_index(op.f('ix_validation_results_execution_id'), table_name='validation_results')
    op.drop_index(op.f('ix_validation_results_failed_stage'), table_name='validation_results')
    op.drop_index(op.f('ix_validation_results_passed'), table_name='validation_results')
    op.drop_table('validation_results')
    op.drop_index(op.f('ix_simulator_movements_created_at'), table_name='simulator_movements')
    op.drop_index(op.f('ix_simulator_movements_execution_id'), table_name='simulator_movements')
    op.drop_table('simulator_movements')
    op.drop_index(op.f('ix_execution_metrics_created_at'), table_name='execution_metrics')
    op.drop_index(op.f('ix_execution_metrics_detected_pattern'), table_name='execution_metrics')
    op.drop_index(op.f('ix_execution_metrics_execution_id'), table_name='execution_metrics')
    op.drop_index(op.f('ix_execution_metrics_gesture_correct'), table_name='execution_metrics')
    op.drop_index(op.f('ix_execution_metrics_ground_truth_gesture'), table_name='execution_metrics')
    op.drop_index(op.f('ix_execution_metrics_intent'), table_name='execution_metrics')
    op.drop_index(op.f('ix_execution_metrics_predicted_gesture'), table_name='execution_metrics')
    op.drop_index(op.f('ix_execution_metrics_repetition_group'), table_name='execution_metrics')
    op.drop_index(op.f('ix_execution_metrics_response_fingerprint'), table_name='execution_metrics')
    op.drop_table('execution_metrics')
    op.drop_index(op.f('ix_execution_errors_category'), table_name='execution_errors')
    op.drop_index(op.f('ix_execution_errors_created_at'), table_name='execution_errors')
    op.drop_index(op.f('ix_execution_errors_execution_id'), table_name='execution_errors')
    op.drop_table('execution_errors')
    op.drop_index(op.f('ix_lab_presets_created_at'), table_name='lab_presets')
    op.drop_index(op.f('ix_lab_presets_name'), table_name='lab_presets')
    op.drop_index(op.f('ix_lab_presets_owner_id'), table_name='lab_presets')
    op.drop_table('lab_presets')
    op.drop_index(op.f('ix_executions_created_at'), table_name='executions')
    op.drop_index(op.f('ix_executions_emg_window_id'), table_name='executions')
    op.drop_index(op.f('ix_executions_experiment_id'), table_name='executions')
    op.drop_index('ix_executions_experiment_status', table_name='executions')
    op.drop_index('ix_executions_frozen_context', table_name='executions')
    op.drop_index(op.f('ix_executions_full_prompt_sha256'), table_name='executions')
    op.drop_index(op.f('ix_executions_latency_ms'), table_name='executions')
    op.drop_index(op.f('ix_executions_litellm_model'), table_name='executions')
    op.drop_index(op.f('ix_executions_llm_model_id'), table_name='executions')
    op.drop_index('ix_executions_model_created', table_name='executions')
    op.drop_index(op.f('ix_executions_provider_slug'), table_name='executions')
    op.drop_index(op.f('ix_executions_status'), table_name='executions')
    op.drop_index(op.f('ix_executions_validation_passed'), table_name='executions')
    op.drop_table('executions')
    op.drop_index(op.f('ix_emg_stream_sessions_created_at'), table_name='emg_stream_sessions')
    op.drop_index(op.f('ix_emg_stream_sessions_experiment_id'), table_name='emg_stream_sessions')
    op.drop_index(op.f('ix_emg_stream_sessions_session_key'), table_name='emg_stream_sessions')
    op.drop_table('emg_stream_sessions')
    op.drop_index(op.f('ix_sampling_configurations_created_at'), table_name='sampling_configurations')
    op.drop_index(op.f('ix_sampling_configurations_model_id'), table_name='sampling_configurations')
    op.drop_index(op.f('ix_sampling_configurations_name'), table_name='sampling_configurations')
    op.drop_index(op.f('ix_sampling_configurations_owner_id'), table_name='sampling_configurations')
    op.drop_table('sampling_configurations')
    op.drop_index(op.f('ix_experiments_created_at'), table_name='experiments')
    op.drop_index(op.f('ix_experiments_frozen_context_sha256'), table_name='experiments')
    op.drop_index(op.f('ix_experiments_name'), table_name='experiments')
    op.drop_index(op.f('ix_experiments_owner_id'), table_name='experiments')
    op.drop_index(op.f('ix_experiments_status'), table_name='experiments')
    op.drop_table('experiments')
    op.drop_index(op.f('ix_technical_context_versions_content_sha256'), table_name='technical_context_versions')
    op.drop_index(op.f('ix_technical_context_versions_created_at'), table_name='technical_context_versions')
    op.drop_index(op.f('ix_technical_context_versions_limit_profile'), table_name='technical_context_versions')
    op.drop_index(op.f('ix_technical_context_versions_name'), table_name='technical_context_versions')
    op.drop_table('technical_context_versions')
    op.drop_index(op.f('ix_system_prompt_versions_content_sha256'), table_name='system_prompt_versions')
    op.drop_index(op.f('ix_system_prompt_versions_created_at'), table_name='system_prompt_versions')
    op.drop_index(op.f('ix_system_prompt_versions_name'), table_name='system_prompt_versions')
    op.drop_table('system_prompt_versions')
    op.drop_index(op.f('ix_llm_models_created_at'), table_name='llm_models')
    op.drop_index(op.f('ix_llm_models_provider_id'), table_name='llm_models')
    op.drop_table('llm_models')
    op.drop_index(op.f('ix_dynamic_prompt_templates_content_sha256'), table_name='dynamic_prompt_templates')
    op.drop_index(op.f('ix_dynamic_prompt_templates_created_at'), table_name='dynamic_prompt_templates')
    op.drop_index(op.f('ix_dynamic_prompt_templates_name'), table_name='dynamic_prompt_templates')
    op.drop_table('dynamic_prompt_templates')
    op.drop_index(op.f('ix_users_created_at'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_llm_providers_created_at'), table_name='llm_providers')
    op.drop_index(op.f('ix_llm_providers_slug'), table_name='llm_providers')
    op.drop_table('llm_providers')
    op.drop_index(op.f('ix_emg_windows_checksum'), table_name='emg_windows')
    op.drop_index(op.f('ix_emg_windows_created_at'), table_name='emg_windows')
    op.drop_index(op.f('ix_emg_windows_ground_truth_gesture'), table_name='emg_windows')
    op.drop_index(op.f('ix_emg_windows_mean_rms'), table_name='emg_windows')
    op.drop_index(op.f('ix_emg_windows_session_id'), table_name='emg_windows')
    op.drop_index(op.f('ix_emg_windows_source_mode'), table_name='emg_windows')
    op.drop_index(op.f('ix_emg_windows_subject_ref'), table_name='emg_windows')
    op.drop_table('emg_windows')
    # ### end Alembic commands ###
