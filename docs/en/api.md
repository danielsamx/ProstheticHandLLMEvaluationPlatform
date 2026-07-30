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
| `GET` | `/hand/output-contract` | The JSON Schema the LLM must satisfy |

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

**Four** versioned artefacts. Editing creates a new version; existing rows are
never modified.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/prompts/system` | System prompt versions |
| `POST` | `/prompts/system` | New version |
| `POST` | `/prompts/system/{id}/activate` | Make active |
| `GET` | `/prompts/technical-context` | Technical context versions |
| `GET` | `/prompts/technical-context/generated` | Regenerate canonically from the domain model |
| `POST` | `/prompts/technical-context` | New version |
| `POST` | `/prompts/technical-context/{id}/activate` | Make active |
| `GET` | `/prompts/emg-context` | EMG knowledge versions |
| `GET` | `/prompts/emg-context/generated` | Regenerate canonically from the domain model |
| `POST` | `/prompts/emg-context` | New version |
| `POST` | `/prompts/emg-context/{id}/activate` | Make active |
| `GET` | `/prompts/dynamic-templates` | Dynamic templates |
| `POST` | `/prompts/dynamic-templates` | New template |
| `POST` | `/prompts/preview` | Assemble the final prompt **without spending a token** |

Block 3 (EMG knowledge) is a separate artefact from block 2 on purpose. "What can
this hand do?" changes only when the hardware does; "is co-contraction a stop or
physiological coactivation?" is a methodological position that gets revised
repeatedly. Sharing one artefact would mean every experiment on the second
question also reversioned the first, and the two effects could not be told apart.

```http
POST /api/v1/prompts/preview
{
  "window": { "samples": [[…]], "source_mode": "manual", "sample_rate_hz": 1000 },
  "dynamic_content": "matrix",
  "matrix_max_rows": null,
  "limit_profile": "TABLE_5_V3",
  "context_window": 8192
}
```

`preview` returns the **four** blocks, the assembled messages, the joined
`full_prompt`, character counts, the token budget per block and all six digests —
including `frozen_context_sha256`, the comparability key and the deduplication key
for prompt configurations.

Two response fields report what was *actually* rendered rather than what was
requested: `matrix_rows_sent` and `dynamic_content`. A row cap decimates with a
whole-number stride, so a cap of 64 on 404 rows yields 58; echoing the request
back would misreport the stimulus.

`budget_advice` is expressed in rows, not tokens — "this context holds roughly 159
rows" is something a caller can act on.

---

## Sampling configurations

How the model is asked: the decoding parameters, plus the one switch that is not a
decoding parameter.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/configurations` | List, newest first |
| `POST` | `/configurations` | Create |
| `GET` | `/configurations/{id}` | Retrieve |
| `PUT` | `/configurations/{id}` | Replace |
| `DELETE` | `/configurations/{id}` | Remove |
| `GET` | `/presets` | Saved lab presets |

```http
POST /api/v1/configurations
{
  "name": "greedy · no thinking",
  "model_id": "…",
  "temperature": 0.0,
  "top_p": 1.0,
  "max_tokens": 1024,
  "seed": 42,
  "response_format": "json_object",
  "disable_reasoning": true
}
```

**`disable_reasoning` defaults to `true`** and is the most consequential field here
for a reasoning model. A Qwen3-class model splits its output — working-out to
`reasoning_content`, answer to `content` — and given a hard classification with a
token ceiling it can spend the whole ceiling deliberating and return an empty
`content`. The platform would then record a parse failure for a model that was
still thinking.

When it is true, **two** switches are sent, because two conventions exist and
runtimes disagree about which they read:

| Sent | Convention | Read by |
|---|---|---|
| `chat_template_kwargs: {"enable_thinking": false}` | Qwen3 | The chat template |
| `reasoning_effort: "none"` | OpenAI | The runtime's inference layer |

A runtime that does not recognise one ignores it, so sending both costs nothing and
covers both families.

`response_format` accepts `text`, `json_object` and `json_schema`. A `json_object`
request is **upgraded** to `json_schema` for runtimes whose OpenAI-compatible layer
rejects the plain spelling — LM Studio among them. Upgrading rather than
downgrading to free text is deliberate: a schema makes malformed JSON
*undecodable*, and that guarantee is worth keeping.

Unknown parameters are dropped per model rather than sent and rejected: a runtime
that has never heard of `top_k` fails the whole request over it.

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
  "ground_truth_gesture": "close"
}
```

**Values pass through unchanged.** There is no normalisation parameter, and the
request schema forbids unknown fields — nothing between the electrode and the
prompt rescales anything, so what the model is judged on is what the hardware
produced. `observed_peak` comes back only so an interface can show the signal's
range; nothing in the platform acts on it.

Permissive about delimiters and header labels — acquisition tools emit `CH0…CH7`
as readily as `CH1…CH8`, and a label-only first line is skipped by shape rather
than by matching specific names. Strict about the matrix itself: a transposed
matrix (8 rows × N columns) would corrupt every derived feature, so it is detected
and named explicitly rather than accepted.

---

## Executions

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/executions/run` | Run one experiment, optionally repeated |
| `GET` | `/executions` | List, filterable |
| `GET` | `/executions/stats` | Aggregates computed **in SQL**, not over a loaded page |
| `GET` | `/executions/configurations` | Distinct frozen prompt setups, with results per model |
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
  "repetitions": 5,
  "expected_serial_command": "C",
  "dynamic_content": "matrix",
  "matrix_max_rows": null
}
```

`expected_serial_command` is the answer key. It is stored on the execution,
compared against the **normalised** command so formatting never counts as a wrong
answer, and **never placed in any prompt**. Runs without one are excluded from the
accuracy denominator: "not compared" and "compared and wrong" are different facts.

With `repetitions > 1` the response includes `determinism`: distinct responses
and the modal agreement rate. At temperature 0 with a fixed seed, anything below
1.0 means the runtime is not honouring the seed.

`replay-movement` only works for executions that passed validation, so it cannot
resurrect an unsafe pose. It also writes a `replay` row to the movement log — it
moved the hand, so it is recorded like anything else that did.

### `GET /executions/stats`

Returns `comparable: false` when the matching rows did not all share one
`frozen_context_sha256`, plus `command_labelled` / `command_matched` /
`command_accuracy`. The denominator travels with the rate on purpose: 100% of three
runs and 100% of three hundred are different claims.

### `GET /executions/configurations`

One row per distinct combination of the three frozen blocks, keyed on
`frozen_context_sha256`. Each carries its label (`S1.0 · T1.1 · E1.1`), the three
block versions, the frozen text as it stood, `first_used_at` / `last_used_at`, and
`by_model` — results broken down per model, because a configuration is only
comparable within one.

---

## Movement

Commands that reached the simulator, the prosthesis, or both. Distinct from the
execution history: that records what models *answered*, this records what *moved
the hand*.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/movement/send` | Validate a typed command and publish it to the simulator |
| `POST` | `/movement/log/{id}/delivered` | The browser reporting what the hardware did |
| `GET` | `/movement/log` | The log, newest first. `limit` ≤ 1000, `source` filter |

```http
POST /api/v1/movement/send
{
  "serial_command": "A320,B240",
  "handedness": "right",
  "limit_profile": "TABLE_5_V3",
  "notes": "checking the link after a firmware flash"
}
```

A typed command goes through the **same seven validation stages** a model's answer
does — not a parallel checker. Two definitions of "safe" would drift, and the
guarantee would become whichever one happened to run. The mechanical stops do not
care who chose the number. A rejected command comes back as `400` carrying the
validator's own message, which already names the actuator, the value and the
profile that refused it.

The response reports `simulator_clients`: zero means the command was accepted and
published but nothing was listening, which is a different outcome from rejection
and is reported as one.

`POST /movement/log/{id}/delivered?transport=serial` is a **separate call** because
the two destinations succeed and fail independently — the simulator renders from
the backend, the hardware is driven from the browser, and the backend cannot reach
a serial port. One combined write would have to guess at the half it cannot see.
Pass `error=…` instead to record a failed write.

`GET /movement/log` filters on `source`: `execution`, `manual` or `replay`. The
three answer different questions — evidence, a check on the plumbing, and neither
— so counting them together would be wrong.

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
