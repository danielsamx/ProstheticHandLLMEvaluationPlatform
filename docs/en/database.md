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
                                    emg_context_versions ──< executions
                                    dynamic_prompt_templates ──< executions
                                    prompt_configurations ──< executions
                                    lab_presets

movement_log >── executions (nullable: manual commands have no execution)
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

Carries `disable_reasoning` (boolean, default **true**) alongside the decoding
knobs, even though suppressing the thinking channel is not decoding. It belongs
here because it is a property of *how the model is asked*, and because leaving it
out of the reusable bundle would let two runs of "the same configuration" differ on
the one setting most likely to empty a response.

### Versioned prompt artefacts

`system_prompt_versions`, `technical_context_versions`, `emg_context_versions`,
`dynamic_prompt_templates`

Shared shape: `name`, `version`, `content`, `content_sha256`, `is_active`,
`is_system_default`. Unique on `(name, version)`.

**Immutable.** Editing in the UI inserts a new row. Where the generated text
drifts without a version bump, the seed files it under a suffixed version rather
than overwriting.

All four artefacts ship at version **1.0**. The numbers previously carried the
platform's own development history — a system prompt at 6.0.0 before a single
experiment had been run — which made this table read as though five earlier studies
had happened.

`technical_context_versions.limit_profile` records which mechanical envelope the
text describes, so a context can never be paired with a validator that
contradicts it.

`is_system_default` is load-bearing beyond bookkeeping: it is how the assembler
knows whether a stored template should override the dynamic-content mode. A flag
survives every rewording of the text; comparing the text itself only works until
the next edit.

#### `prompt_configurations`
One row per **distinct combination** of the three frozen blocks, unique on
`frozen_context_sha256`.

Deduplicated at write time: three hundred runs under one setup leave one row,
changing a block files a second, and returning to the first reuses it and touches
`last_used_at`. Carries `label` (`S1.0 · T1.0 · E1.0`), the three version foreign
keys **and** the version strings copied in, plus `frozen_context_text`.

The strings are copied rather than only referenced on purpose. The foreign keys are
`ON DELETE SET NULL`; if an artefact row is ever removed, the configuration still
knows which wording it stood for.

#### `movement_log`
Every command that reached the simulator, the prosthesis, or both.

Deliberately not derivable from `simulator_movements`: that table records poses the
platform *resolved*, this one records what was *transmitted*, and the two diverge
in both directions.

`source` is `execution`, `manual` or `replay`. `execution_id` is nullable, because
a typed command has no execution behind it.

`sent_to_simulator` and `sent_to_prosthesis` are **two independent booleans**, not
one `delivered` flag. The simulator renders from the backend and the hardware is
driven from the browser, so either can arrive while the other does not — and that
asymmetry is the whole diagnostic value of the table. `transport` (`serial` | `ble`)
and `delivery_error` record how, or why not.

Rows are written **after** the attempt, so the flags record what happened rather
than what was intended.

#### `lab_presets`
One-click bundle: configuration + the prompt versions + hand + limit profile.

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
`emg_context_text`, `dynamic_prompt_text`, `messages_json`, plus six SHA-256
digests (`…_sha256` per block, `frozen_context_sha256`, `full_prompt_sha256`).
Stored verbatim, not reconstructed: a result survives later editing or deletion of
the rows it referenced.

`frozen_context_sha256 = SHA256(system ‖ technical ‖ emg_context)` is the
comparability key. Two executions with the same digest were asked the same way;
two with different digests are different experiments, whatever else they share.

**The stimulus condition** — `dynamic_content` (`matrix` | `features` | `both`) and
`matrix_rows_sent`. The second records what was *rendered*, not what was
*requested*: a row cap decimates with a whole-number stride, so 64 on 404 rows
yields 58, and storing the request would misdescribe the stimulus.

**The answer key** — `expected_serial_command`, nullable. Supplied by the
researcher, compared against the normalised command, never placed in a prompt. Null
means "not compared", which is a different fact from "compared and wrong" and is
excluded from the accuracy denominator rather than counted as a miss.

**The prompt configuration** — `prompt_configuration_id`, pointing at the
deduplicated frozen setup this run belongs to.

**Model and endpoint** — `litellm_model`, `provider_slug`, `model_key`,
`api_base`, `api_flavour`, `model_snapshot`

**Decoding parameters** — **Denormalisation (2 of 2).** `temperature`, `top_p`,
`top_k`, `max_tokens`, `seed`, `frequency_penalty`, `presence_penalty`,
`stop_sequences`, `response_format`, `reasoning_mode`, `custom_parameters`.
Duplicated from `model_snapshot` so a parameter sweep is a plain SQL aggregate.

`reasoning_mode` lives **here**, on the execution, not on
`sampling_configurations` — which carries the boolean `disable_reasoning`. The
distinction matters: the configuration holds the *intent*, the execution holds what
was actually sent. Editing a configuration afterwards must not be able to
retroactively change the condition a past result is attributed to.

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
| `0004_json_contract` | The response becomes one JSON object; per-block digests |
| `0005_expected_command` | `expected_serial_command`, `dynamic_content`, `matrix_rows_sent` |
| `0006_emg_context_block` | `emg_context_versions` and the fourth block on executions |
| `0007_prompt_configurations` | `prompt_configurations`, deduplicated on the frozen digest |
| `0008_reasoning_and_movement_log` | `sampling_configurations.disable_reasoning`, `movement_log` |
| `0009_auth_myo_feedback` | Authentication roles, Myo acquisition settings and gesture feedback |
| `0010_feedback_timestamp_defaults` | Server-side defaults for the feedback timestamps |
| `0009_auth_myo_feedback` | Four-role accounts, authentication support and auditable gesture feedback |

`0002` deletes existing windows and executions. A feature vector does not
determine the waveform it came from, so back-filling a synthetic matrix would
have produced fabricated data indistinguishable from recorded data.

`0007` back-fills a configuration row for each distinct `frozen_context_sha256`
already present and points existing executions at it, so the history is not split
into "runs with a configuration" and "runs from before".

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
