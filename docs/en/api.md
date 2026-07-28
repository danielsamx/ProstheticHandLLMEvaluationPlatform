# API reference

**Languages:** [English](api.md) · [Español](../es/api.md)

Base path `/api/v1`. Interactive documentation at `/docs` (Swagger) and `/redoc`.

All bodies are JSON. Errors follow FastAPI's shape: `{"detail": "..."}` for a
single message, or a list of field errors for validation failures.

Every request may carry `X-Request-ID` and `X-Session-ID`; both are echoed onto
the execution record and the audit trail, and `X-Request-ID` comes back on the
response so a client can correlate its own logs with the server's.

---

## System

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness. Answers "is anything there", not "does a query work" |
| `GET` | `/` | Service metadata and WebSocket paths |

---

## Hardware specification

The prosthesis, as the backend understands it. The Angular simulator builds its
rig from this, so there is one definition of the hardware in the whole system.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/hand/spec` | DOF counts, actuators, joints, gestures, limit profiles, protocol, safety envelope, EMG format |
| `GET` | `/hand/actuator-joint-map` | Actuator letter → driven joint ids |
| `GET` | `/hand/output-schema` | The JSON Schema the LLM must satisfy |

---

## Providers and models

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/providers` | Registered providers, local ones first |
| `GET` | `/providers/models` | Model catalogue, optionally filtered by provider |
| `POST` | `/providers/models` | Register a model manually |
| `GET` | `/providers/lm-studio/probe` | What LM Studio currently has loaded |
| `POST` | `/providers/lm-studio/sync` | Import loaded models into the catalogue |

`sync` registers new models conservatively — JSON mode on, JSON Schema off —
because GGUF runtimes vary. Raise the flags per model once verified.

---

## Projects

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/projects` | List. `include_archived`, `include_deleted` |
| `POST` | `/projects` | Create; slug generated and de-duplicated |
| `GET` | `/projects/{id}` | Retrieve |
| `PATCH` | `/projects/{id}` | Partial update; audited with a field-level diff |
| `DELETE` | `/projects/{id}` | **Soft** delete; nothing is destroyed |
| `POST` | `/projects/{id}/restore` | Undo a soft delete |
| `GET` | `/projects/{id}/stats` | Counts, tokens, cost, latency — aggregated in SQL |
| `GET` | `/projects/{id}/audit` | Everything that happened inside the project |

```http
POST /api/v1/projects
{
  "name": "Grasp classification across 7B models",
  "research_question": "Does quantisation degrade EMG interpretation?",
  "tags": ["emg", "quantisation"]
}
```

---

## Experiments

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/experiments` | List |
| `POST` | `/experiments` | Create with pinned frozen conditions |
| `GET` | `/experiments/{id}` | Retrieve |
| `GET` | `/experiments/{id}/comparison` | Cross-model leaderboard |
| `GET` | `/experiments/{id}/failure-modes` | How each model fails, by stage and code |

`comparison` returns `comparable: false` when the executions did not all share
one `frozen_context_sha256`. The platform would rather report "not comparable"
than present an authoritative-looking ranking built on unequal conditions.

---

## Prompts

Three versioned artefacts. Editing creates a new version; existing rows are never
modified.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/prompts/system` | System prompt versions |
| `POST` | `/prompts/system` | New version |
| `POST` | `/prompts/system/{id}/activate` | Make active |
| `GET` | `/prompts/technical-context` | Technical context versions |
| `GET` | `/prompts/technical-context/generated` | Regenerate canonically from the domain model |
| `POST` | `/prompts/technical-context` | New version |
| `POST` | `/prompts/technical-context/{id}/activate` | Make active |
| `GET` | `/prompts/dynamic-templates` | Dynamic templates |
| `POST` | `/prompts/dynamic-templates` | New template |
| `POST` | `/prompts/preview` | Assemble the final prompt **without spending a token** |

`preview` returns the three blocks, the assembled messages, character counts and
all five digests — including `frozen_context_sha256`, the comparability key.

---

## EMG

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/emg/format` | The matrix contract: shape, layout, amplitude range, limits |
| `GET` | `/emg/blank` | A zeroed N×8 matrix |
| `POST` | `/emg/parse` | Parse pasted CSV / TSV / JSON and normalise |
| `GET` | `/emg/synthetic/gestures` | Available synthetic gestures |
| `GET` | `/emg/synthetic` | Generate a labelled window |
| `GET` | `/emg/windows` | Stored windows |
| `GET` | `/emg/windows/{id}` | One window |
| `GET` | `/emg/windows/{id}/csv` | Export as CSV |

### Parsing

```http
POST /api/v1/emg/parse
{
  "text": "CH0,CH1,...\n-2,-2,-3,-3,0,2,0,0\n...",
  "sample_rate_hz": 1000,
  "normalisation": "full_scale",
  "full_scale": 512
}
```

The response reports `divisor`, `observed_peak` and `inferred_full_scale`,
because how amplitudes were normalised determines whether two windows can be
compared at all.

| `normalisation` | Behaviour |
|---|---|
| `full_scale` | Divide by the declared converter range. **Default.** |
| `none` | Reject anything outside [-1, 1] |
| `peak` | Divide by this window's own maximum — **breaks cross-window comparability**, and says so in `warnings` |

A transposed matrix (8 rows × N columns) is detected and named explicitly rather
than accepted.

---

## Executions

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/executions/run` | Run one experiment, optionally repeated |
| `GET` | `/executions` | List, filterable |
| `GET` | `/executions/{id}` | One execution with validation, metrics and movement |
| `GET` | `/executions/{id}/prompt` | The literal prompt that was sent |
| `POST` | `/executions/{id}/replay-movement` | Re-emit a stored validated pose |

```http
POST /api/v1/executions/run
{
  "sampling_configuration_id": "…",
  "window": { "samples": [[…]], "source_mode": "manual", "sample_rate_hz": 1000 },
  "handedness": "right",
  "limit_profile": "TABLE_5_V3",
  "repetitions": 5
}
```

With `repetitions > 1` the response includes `determinism`: distinct responses
and the modal agreement rate. At temperature 0 with a fixed seed, anything below
1.0 means the runtime is not honouring the seed.

`replay-movement` only works for executions that passed validation, so it cannot
resurrect an unsafe pose.

---

## Traceability

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/traceability/{execution_id}` | Reconstruct one past experiment in full |

Returns, in one payload: prompt, model, parameters, stimulus, response,
performance, validation, metrics, movement, errors, logs and audit entries — plus
the actor and the origin of the request.

Also returns `reproducible` and, when false, `missing_for_reproduction`: exactly
which pieces are absent. A record that merely looks complete is worse than one
that admits a gap.

---

## Audit

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/audit` | Browse the trail, filterable |
| `GET` | `/audit/actions` | The closed catalogue of auditable actions |
| `GET` | `/audit/entity/{type}/{id}` | Everything that happened to one entity |

Filters: `action`, `outcome`, `actor_email`, `entity_type`, `entity_id`,
`project_id`, `since`, `until`.

Entries are append-only; there is no write endpoint by design.

---

## Export

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/export/executions.csv` | Analysis-ready CSV |
| `POST` | `/export/executions.jsonl` | Newline-delimited JSON, streamed |
| `POST` | `/export/executions.json` | Same rows as JSON |
| `GET` | `/export/columns` | Stable column order |

```http
POST /api/v1/export/executions.csv
{
  "project_id": "…",
  "since": "2026-07-01T00:00:00Z",
  "only_validated": false,
  "include_prompts": false
}
```

`only_validated` defaults to **false**: excluding failures silently biases any
success rate computed downstream. `include_prompts` and `include_emg_matrix`
default to false because they multiply file size by roughly thirty and far more
respectively.

---

## WebSockets

### `/ws/simulator`

Read-only feed of **validated** movements. A rejected response produces a
`{"type": "rejected", …}` frame so the interface can explain the failure without
moving the hand.

### `/ws/emg/{session_key}`

Live stimulus ingestion.

```json
{"type": "configure", "sampling_configuration_id": "…", "auto_run": true}
{"session_id": "…", "sequence": 0, "window": {…}, "auto_run": true}
```

With `auto_run`, every frame runs the full execution path — same prompt assembly,
same validation, same persistence as a manual run. Live and manual windows carry
different `source_mode` values so they are never silently pooled in an analysis.

---

## Status codes

| Code | Meaning here |
|---|---|
| `200` / `201` | Success |
| `204` | Deleted |
| `400` | The request is coherent but the configuration is not usable |
| `404` | Not found |
| `409` | Conflicts with current state (e.g. restoring a project that is not deleted) |
| `422` | Payload failed validation — a field list comes back |
| `503` | A dependency is unreachable (e.g. LM Studio) |

A model producing an invalid command is **not** an HTTP error. It is a
successful execution with `validation_passed: false`, because the failure is the
experimental result.
