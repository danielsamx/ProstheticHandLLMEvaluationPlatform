# Database

**Languages:** [English](database.md) · [Español](../es/base-de-datos.md)

PostgreSQL 17. Twenty-one tables, third normal form, with two deliberate
denormalisations documented below.

---

## Design principles

**Nothing is overwritten.** Prompt versions, executions and audit entries are
append-only. A result published a year ago must still resolve to the exact bytes
that produced it, which rules out in-place edits.

**Identity is snapshotted.** Rows that record an action also store the actor's
email as text, not only a foreign key. Accounts get deleted; the record of who
ran an experiment must survive that.

**Deletion is logical.** `projects.is_deleted` flags a row; nothing is removed.
A hard delete would break the traceability the platform exists to provide.

**Conditions are queryable.** Decoding parameters live both in
`executions.model_snapshot` (JSONB, for fidelity) and as typed columns (for
`GROUP BY temperature` across millions of rows). The duplication is intentional
and one-directional: the snapshot is authoritative.

---

## Schema map

```
users
  │
  ├──< projects ──< experiments ──< executions ─┬─ validation_results ──< validation_issues
  │                                             ├─ execution_metrics
  │                                             ├─ execution_errors
  │                                             ├─ execution_logs
  │                                             ├─ simulator_movements
  │                                             └─ attachments
  │
  ├──< audit_logs
  └──< sampling_configurations >── llm_models >── llm_providers

emg_windows ──< executions          system_prompt_versions ──< executions
emg_stream_sessions                 technical_context_versions ──< executions
                                    dynamic_prompt_templates ──< executions
                                    lab_presets
```

---

## Tables

### Identity and organisation

#### `users`
Researcher accounts. `role` is one of `admin`, `researcher`, `viewer`.

#### `projects`
A line of investigation.

| Column | Notes |
|---|---|
| `slug` | Unique, URL-safe, generated from the name and de-duplicated |
| `research_question` | What makes the project legible a year later |
| `status` | `active` / `paused` / `archived` |
| `owner_email` | Identity snapshot, survives account deletion |
| `is_deleted`, `deleted_at` | Soft delete; the row is retained |
| `settings` | JSONB defaults inherited by new experiments |

### Catalogue

#### `llm_providers`
A LiteLLM-routable provider. `litellm_prefix` is prepended to the model key
(`lm_studio` + `qwen2.5-7b` → `lm_studio/qwen2.5-7b`). `is_local` drives cost
reporting: local runs record zero, and tokens per second becomes the efficiency
metric.

#### `llm_models`
A concrete model. The `supports_*` flags are capability declarations — the UI
disables a parameter the runtime cannot honour rather than letting it be dropped
silently.

#### `sampling_configurations`
A named, reusable decoding configuration. Saved once and replayed across models,
which is what keeps a comparison controlled.

### Versioned prompt artefacts

`system_prompt_versions`, `technical_context_versions`, `dynamic_prompt_templates`

Shared shape: `name`, `version`, `content`, `content_sha256`, `is_active`,
`is_system_default`. Unique on `(name, version)`.

**Immutable.** Editing in the UI inserts a new row. Where the generated text
drifts without a version bump, the seed files it under `2.0.0+<sha8>` rather than
overwriting.

`technical_context_versions.limit_profile` records which mechanical envelope the
text describes, so a context can never be paired with a validator that
contradicts it.

#### `lab_presets`
One-click bundle: configuration + three prompt versions + hand + limit profile.

### Stimulus

#### `emg_windows`
The experimental stimulus.

| Column | Notes |
|---|---|
| `samples` | JSONB. N×8 matrix, amplitudes in [-1, 1] |
| `features` | **Denormalisation (1 of 2).** Cached descriptors, derived from `samples`. Recomputing RMS over millions of rows for every query is not viable. |
| `checksum` | SHA-256 of matrix + sample rate. Proves two runs saw the same signal |
| `ground_truth_gesture` | Enables automatic accuracy scoring |

#### `emg_stream_sessions`
Live acquisition sessions.

### Experimentation

#### `experiments`
Pins one set of frozen conditions: the three prompt versions, the limit profile,
the handedness. `frozen_context_sha256` is the comparability key.

#### `executions`
One independent inference. The central table.

**Organisation** — `project_id`, `experiment_id`, `repetition_index`,
`triggered_by_id`, `triggered_by_email`

**The exact prompt sent** — `system_prompt_text`, `technical_context_text`,
`dynamic_prompt_text`, `messages_json`, plus five SHA-256 digests. Stored
verbatim, not reconstructed: a result survives later editing or deletion of the
rows it referenced.

**Model and endpoint** — `litellm_model`, `provider_slug`, `model_key`,
`api_base`, `api_flavour`, `model_snapshot`

**Decoding parameters** — **Denormalisation (2 of 2).** `temperature`, `top_p`,
`top_k`, `max_tokens`, `seed`, `frequency_penalty`, `presence_penalty`,
`stop_sequences`, `response_format`, `reasoning_mode`, `custom_parameters`.
Duplicated from `model_snapshot` so a parameter sweep is a plain SQL aggregate.

**`dropped_parameters`** — knobs the runtime silently ignored. Without this a run
looks reproducible when it is not.

**Result** — `raw_response`, `parsed_response`, `finish_reason`, token counts,
`cost_usd` (14,8 — local runs are 0, hosted can be sub-cent), `latency_ms`,
`tokens_per_second`

**Origin** — `client_ip`, `user_agent`, `browser`, `operating_system`,
`device_type`, `session_id`, `request_id`, `app_version`

### Outcome

#### `validation_results` / `validation_issues`
Verdict of the seven-stage pipeline, and one row per issue. Aggregating `code`
across executions is what turns "fails 30% of the time" into "fails because it
prefixes JSON with prose".

#### `execution_errors`
Hard failures, categorised: `provider`, `parse`, `schema`, `protocol`, `range`,
`kinematic`, `safety`, `internal`.

#### `execution_logs`
The log lines that belong to the scientific record — a retry, a dropped
parameter, a response that needed repair. Ordered by `sequence`, because
wall-clock timestamps collide at this resolution.

#### `execution_metrics`
Derived measures, wide by design so cross-model aggregation is a plain
`GROUP BY`. Compliance flags, accuracy against ground truth, calibration error,
efficiency, and `response_fingerprint` — the canonical digest that makes
determinism measurable.

#### `simulator_movements`
The pose actually rendered. **A row exists only when validation passed.** Its
absence for a failed execution is the audit trail proving the safety gate held.

### Governance

#### `audit_logs`
Append-only. Actor (id + email snapshot + role), `action` from a closed
catalogue, `outcome`, `summary`, affected entity (type + id + label snapshot),
field-level `changes` diff, and full request origin.

`action` is a closed enumeration on purpose: free text drifts into a dozen
spellings of the same event and stops being aggregatable.

Secrets are redacted and long values summarised before they reach `changes`.

#### `attachments`
Files bound to a project, experiment or execution. Content-addressed; small
payloads inline, larger ones by path.

---

## Recurring queries

**Cross-model leaderboard, comparability enforced**

```sql
SELECT litellm_model,
       count(*)                                            AS runs,
       avg((validation_passed)::int)::numeric(5,4)         AS pass_rate,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency,
       sum(total_tokens)                                   AS tokens,
       sum(cost_usd)                                       AS cost
FROM executions
WHERE experiment_id = $1
  AND frozen_context_sha256 = (
      SELECT frozen_context_sha256 FROM experiments WHERE id = $1
  )
GROUP BY litellm_model
ORDER BY pass_rate DESC;
```

The `frozen_context_sha256` predicate is what makes the ranking mean anything.

**How each model fails**

```sql
SELECT e.litellm_model, i.stage, i.code, count(*) AS n
FROM executions e
JOIN validation_results r ON r.execution_id = e.id
JOIN validation_issues  i ON i.validation_result_id = r.id
WHERE i.severity = 'error' AND e.experiment_id = $1
GROUP BY 1, 2, 3
ORDER BY n DESC;
```

**Determinism at temperature 0**

```sql
SELECT m.repetition_group,
       count(DISTINCT m.response_fingerprint) AS distinct_responses,
       count(*)                               AS repetitions
FROM execution_metrics m
JOIN executions e ON e.id = m.execution_id
WHERE e.temperature = 0 AND m.repetition_group IS NOT NULL
GROUP BY 1
HAVING count(DISTINCT m.response_fingerprint) > 1;
```

Rows returned are runs that should have been identical and were not.

**Effect of one parameter**

```sql
SELECT temperature,
       avg((validation_passed)::int) AS pass_rate,
       avg(latency_ms)               AS mean_latency
FROM executions
WHERE litellm_model = $1 AND frozen_context_sha256 = $2
GROUP BY temperature
ORDER BY temperature;
```

This is the query the denormalised parameter columns exist for.

**Audit trail for one entity**

```sql
SELECT created_at, actor_email, action, outcome, summary, changes
FROM audit_logs
WHERE entity_type = 'project' AND entity_id = $1
ORDER BY created_at DESC;
```

---

## Migrations

| Revision | Content |
|---|---|
| `0001_initial` | Seventeen tables: the core experimental record |
| `0002_emg_matrix` | Stimulus becomes a raw N×8 matrix; features derived, not supplied |
| `0003_governance` | Projects, audit, attachments, execution logs, request metadata |

`0002` deletes existing windows and executions. A feature vector does not
determine the waveform it came from, so back-filling a synthetic matrix would
have produced fabricated data indistinguishable from recorded data.

```bash
alembic upgrade head
alembic downgrade -1
alembic history --verbose
```

---

## Retention

Nothing is deleted automatically. On a workstation running thousands of
executions, `executions.raw_response` and `emg_windows.samples` dominate storage.
If pruning becomes necessary, drop the payload columns and keep the row: metrics,
digests and audit entries are small and are what the analysis actually reads.
