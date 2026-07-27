# Architecture

## Request path

```
Angular left panel  ──POST /executions/run──►  FastAPI
                                                 │
                                                 ├─ resolve configuration + prompt versions
                                                 ├─ persist the EMG window (content-addressed)
                                                 ├─ build_prompt()  → 3 blocks + 5 SHA-256 digests
                                                 ├─ LiteLLM  → LM Studio / hosted provider
                                                 ├─ validate_response()  → 7 stages
                                                 ├─ compute_metrics()
                                                 ├─ persist execution + validation + metrics
                                                 └─ if passed → SimulatorMovement + WS broadcast
                                                                        │
Three.js simulator  ◄──── /ws/simulator ─────────────────────────────────┘
```

The dashed line matters: the simulator is downstream of validation, never
parallel to it. A rejected response produces a `rejected` frame that the UI
displays *without* moving the hand.

## Layers

| Layer | Package | Responsibility |
|---|---|---|
| Domain | `app/domain` | The prosthesis, as code. No I/O, no framework imports. |
| Contracts | `app/schemas` | Pydantic v2 models: LLM output, EMG, HTTP payloads |
| Prompts | `app/prompts` | Three blocks + deterministic assembly |
| Validation | `app/validation` | Seven-stage pipeline, pure functions over strings |
| Persistence | `app/models`, `app/db` | SQLAlchemy 2 mappers, async session |
| Services | `app/services` | LiteLLM gateway, orchestrator, metrics, EMG |
| Transport | `app/api`, `app/ws` | FastAPI routers and WebSocket channels |

`app/domain` is the only layer with no dependencies on the others, which is what
lets the same definitions drive the validators, the generated prompt text, the
API's `/hand/spec` payload and the frontend rig.

## Why the technical context is generated

Writing the hardware description by hand would create two sources of truth: the
prose the model reads, and the constants the validator enforces. They would
drift, and the drift would be invisible — the model would be told one limit and
judged against another.

`build_technical_context()` renders the block from `hand_spec.py`. Change a
limit in the domain and the prompt changes with it. The UI still allows free
editing (a hand-written context is a legitimate experimental variable), but the
**Regenerate** button always restores the canonical text, and a generated
context is flagged `generated_from_domain=True` so the provenance is queryable.

## Why prompt versions are immutable

An execution stores both a foreign key to the version row *and* the literal
text plus its digest. The foreign key gives you navigability; the snapshot gives
you reproducibility even if the row is later deleted. Editing a prompt in the UI
creates a new row rather than mutating the old one, so a result published six
months ago still resolves to exactly the bytes that produced it.

## Comparability as a first-class property

`frozen_context_sha256 = SHA256(system_prompt ‖ separator ‖ technical_context)`

It is stored on every execution and on every experiment. `GET
/experiments/{id}/comparison` groups executions by model and returns a
`comparable` boolean that is false when more than one distinct hash appears in
the set. The platform would rather return a leaderboard marked
*"not comparable"* than an authoritative-looking ranking built on unequal
conditions.

## Determinism measurement

Repetitions of one run share a `repetition_group` UUID. Each execution stores a
`response_fingerprint`: SHA-256 of the parsed response canonicalised with sorted
keys and no whitespace. Within a group:

```
determinism_rate = modal fingerprint frequency / valid responses
```

At temperature 0 with a fixed seed, anything below 1.0 is evidence that the
runtime is not honouring the seed — which is common with local GGUF backends and
is precisely the kind of thing a prosthetics researcher needs to know before
trusting a model in a control loop.

## Failure taxonomy

Failure is recorded twice, deliberately:

- `validation_issues` — one row per issue, with a stable `code`, for analysis
  (*how* does this model fail?)
- `execution_errors` — one row per blocking error, categorised, for triage
  (*what broke?*)

Aggregating `code` across executions is what turns "model B fails 30 % of the
time" into "model B fails because it emits prose before the JSON", which is an
actionable finding.

## Frontend state

`LabStore` is a signal-based store with no conversation state whatsoever. An
execution is a pure function of `(configuration, frozen prompts, EMG window)`.
Nothing carries over between runs except the presets the researcher explicitly
saved.

The app runs zoneless: signals drive every view, and keeping the Three.js render
loop out of Angular's change detection avoids a per-frame tick over the whole
component tree.

## Simulator safety

Three independent barriers, so no single bug moves the hand incorrectly:

1. The backend only broadcasts poses that cleared all seven stages.
2. `HandScene` exposes `applyPose()` as its sole movement entry point — there
   are no orbit controls, no sliders, no drag handles.
3. `applyPose()` clamps every angle against the joint limits from `/hand/spec`
   before writing a transform.

## Live EMG

`/ws/emg/{session_key}` accepts a `configure` message pinning a sampling
configuration, then a stream of `EmgStreamFrame` payloads. With `auto_run`, each
frame runs the full execution path — same prompt assembly, same validation, same
persistence as a manual run. Live and manual windows are tagged with different
`source_mode` values so they are never silently pooled in an analysis.

## Extension points

- **Real hardware** — subscribe to `/ws/simulator`, open Bluetooth SPP to
  `Handi EPN V3`, forward `serial_command` verbatim; flip
  `dispatched_to_hardware`.
- **Photorealistic mesh** — `HandScene.loadGltf(url)` matches bones by joint id.
- **New provider** — insert an `llm_providers` row with the LiteLLM prefix.
- **New limit profile** — add to `LIMIT_PROFILES`; contexts, validators and the
  UI dropdown follow automatically.
