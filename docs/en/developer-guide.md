# Developer guide

**Languages:** [English](developer-guide.md) · [Español](../es/guia-desarrollador.md)

---

## Layout

```
backend/
  app/
    domain/        The prosthesis, as code. No I/O, no framework imports.
    schemas/       Pydantic v2 contracts
    prompts/       Three blocks + deterministic assembly
    validation/    Seven-stage pipeline, pure functions over strings
    models/        SQLAlchemy 2 mappers (21 tables)
    db/            Engine and session factory
    services/      LiteLLM gateway, orchestrator, metrics, EMG, audit, export
    core/          Settings, logging, request context, middleware
    api/v1/        FastAPI routers
    ws/            WebSocket channels
    seeds/         Idempotent seed
  alembic/         Migrations
  tests/           189 tests
frontend/
  src/app/
    core/          Typed models, API client, signal store, sockets
    features/lab/  Model config, EMG panel, prompt blocks, results
    features/simulator/  Three.js scene, procedural rig, PBR skin
docs/              Bilingual documentation
scripts/           Development and verification helpers
```

`app/domain` is the only layer with no dependency on the others. That is what
lets one set of definitions drive the validators, the generated prompt text, the
`/hand/spec` payload and the frontend rig simultaneously.

---

## Dependency rule

```
domain  ←  schemas  ←  prompts / validation  ←  services  ←  api / ws
   ↑                                              ↓
   └──────────────── models / db ─────────────────┘
```

Arrows point towards the dependency. `domain` importing from `services` would be
a layering violation and is the first thing to check in review.

---

## Adding things

### A new limit profile

One place:

```python
# app/domain/hand_spec.py
class LimitProfileId(str, Enum):
    WORN_UNIT_V1 = "WORN_UNIT_V1"

LIMIT_PROFILES = {
    LimitProfileId.WORN_UNIT_V1: LimitProfile(
        LimitProfileId.WORN_UNIT_V1,
        "Measured envelope, unit #3 after 400 hours",
        source="Bench measurement 2026-07-12",
        notes="Reduced travel from linkage wear.",
        limits={Actuator.A_PINKY: (0, 520), ...},
    ),
}
```

The technical context, the validators, the seed and the UI dropdown all follow
automatically. This is the payoff for generating the prompt from the domain
rather than writing it by hand.

### A new provider

Insert a row in `llm_providers` with the LiteLLM prefix. No code change.

### A new validation stage

1. Add to `ValidationStage` in `app/validation/results.py`.
2. Implement in `validate_response`, in pipeline order.
3. Return early on error — later stages assume earlier ones passed.
4. Add a test for the specific rejection.

Use `Severity.WARNING` for anything that should be *recorded* rather than
*blocked*. The collision heuristic is a warning because its severity depends on
whether an object is in the grasp.

### A new audited action

```python
# app/models/audit.py
class AuditAction(str, Enum):
    DATASET_IMPORTED = "dataset.imported"
```

Then call `audit_service.record(...)` from the operation. The catalogue is closed
on purpose: free-text actions drift into a dozen spellings of the same event and
stop being aggregatable.

### A new export column

Append to `export_service.BASE_COLUMNS` and populate it in `_flatten`. **Append,
never reorder** — analysis scripts index positionally.

---

## Testing

```bash
cd backend && python -m pytest tests -q
python -m pytest tests/test_validation.py -q -k range
```

No database or web framework is needed: the suite covers the layers where a
mistake reaches hardware or corrupts an experiment, and those layers are pure.

| File | Covers |
|---|---|
| `test_domain.py` | Mechanical limits, gestures, kinematics |
| `test_protocol.py` | Serial codec, the `C` ambiguity, round-tripping |
| `test_validation.py` | All seven stages |
| `test_prompts.py` | Assembly, frozen-context invariants |
| `test_emg_matrix.py` | Matrix contract, features, parsing, synthesis |
| `test_real_acquisition.py` | The full path over a real recording from the lab |
| `test_governance.py` | Audit diffing, traceability, export |
| `test_imports.py` | Static import audit and CORS behaviour |

### Two tests that are not unit tests

`test_imports.py` walks every internal `from app.x import y` and checks the name
exists. A renamed constant with one stale importer passes every unit test and
then fails at container start, inside a uvicorn worker. This catches it in CI
instead.

`test_real_acquisition.py` runs the full path over an actual recording,
including the calibration trap where the declared full scale decides whether a
window of movement reads as rest.

### Frontend

```bash
python scripts/check_frontend.py    # no node_modules needed
cd frontend && npx tsc --noEmit     # full type check
```

`check_frontend.py` catches a stray backtick closing a component template early —
Angular NG1002. Counting backticks for balance does **not** catch it: a pair of
stray backticks keeps the total even while still breaking the decorator.

---

## Conventions

### Python

Ruff, line length 100, target 3.13. Full type annotations. Pydantic v2 for every
boundary contract.

Comments explain **why**, not what. `# increment counter` above `counter += 1` is
noise; a comment explaining why the counter must not reset on retry is not.

### TypeScript

Angular 22, standalone components, zoneless. Signals for all state; RxJS only at
the HTTP boundary. `ChangeDetectionStrategy.OnPush` everywhere.

The `LabStore` holds no conversation state, and must not acquire any. An
execution is a pure function of `(configuration, frozen prompts, EMG window)`.

### Migrations

Every schema change gets a migration with a working `downgrade()`. If data cannot
be migrated faithfully, delete it and say so in the docstring — `0002` does
exactly this, because a feature vector does not determine the waveform it came
from and back-filling one would fabricate data.

---

## Invariants

Break any of these and the platform stops being a research instrument.

1. **The simulator only renders validated poses.** `applyPose` is its sole
   movement entry point, and it clamps against the backend's joint limits before
   writing a transform.
2. **Prompt versions are immutable.** Editing inserts; it never updates.
3. **The frozen context hash is the comparability key.** A comparison across
   different hashes must be reported as not comparable.
4. **The technical context is generated, not authored.** Otherwise the limits the
   model is told about drift from the limits the validator enforces.
5. **Failures are stored, not discarded.** They are the most informative rows in
   an export.
6. **Audit entries are append-only.** No update or delete path exists.

---

## Debugging

### Backend

Logs are structured JSON on stdout:

```bash
docker compose logs backend -f | jq 'select(.level == "ERROR")'
docker compose logs backend -f | jq 'select(.request_id == "…")'
```

Every response carries `X-Request-ID`; the same value is on the execution row and
its audit entries.

### The prompt actually sent

```bash
curl localhost:8000/api/v1/executions/{id}/prompt | jq -r .dynamic_prompt
```

Stored verbatim, not reconstructed.

### Full provenance

```bash
curl localhost:8000/api/v1/traceability/{id} | jq '{reproducible, missing_for_reproduction}'
```

### Frontend

Zoneless, so `ng.applyChanges()` in the console does nothing useful. Read the
signals instead. The Three.js scene exposes `stats()` with fps and triangle
count.

---

## Performance notes

Two costs dominate, and both were measured rather than guessed.

**Skin textures.** Three 1024×1024 buffers of fractal noise — around three
million pixels, several trigonometric calls each, on the main thread. Roughly a
second. They are generated once per session and shared; nothing about them
depends on handedness, so regenerating them on every hand switch was pure waste.

**Rig construction.** Both hands are built once and toggled by visibility. The
second is warmed in `requestIdleCallback` so even the first switch is instant.

Mirroring with `scale.x = -1` would avoid the second rig entirely, but it inverts
every surface normal and wrecks both the lighting and the shadow terminator. The
geometry is regenerated with negated X instead.

---

## Extension points

| Goal | Where |
|---|---|
| Real hardware | Subscribe to `/ws/simulator`, open Bluetooth SPP to `Handi EPN V3`, forward `serial_command` verbatim |
| Photorealistic mesh | `HandScene.loadGltf(url)`; bones matched by joint id |
| New provider | Row in `llm_providers` |
| New limit profile | `LIMIT_PROFILES` in `hand_spec.py` |
| New metric | Column on `execution_metrics`, populate in `metrics_service` |
| New export format | Function in `export_service`, route in `api/v1/governance.py` |
