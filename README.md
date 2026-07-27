# Prosthetic Hand LLM Evaluation Platform

Research platform for benchmarking large language models on a single, narrow,
safety-critical task: **turning an 8-channel surface EMG window into a validated
control command for the HANDi EPN V3 prosthetic hand.**

This is not a chatbot. There are no conversations, no chat history and no
conversational memory anywhere in the system. Every execution is an independent
experiment: one frozen prompt, one EMG window, one model, one JSON response,
seven validation stages, one recorded result.

---

## 1. Why the design looks like this

The scientific claim the platform has to support is *"model A produces more
accurate, more consistent and safer prosthetic commands than model B"*. That
claim is only defensible if everything except the model is held constant. The
architecture enforces that structurally rather than by convention:

| Mechanism | What it guarantees |
|---|---|
| Three-block prompt with the first two frozen | Only the EMG payload varies between runs |
| `frozen_context_sha256` on every execution | Two runs are provably comparable, or provably not |
| Immutable prompt versions (edits create new rows) | Any published result can be reproduced byte for byte |
| Hardware spec compiled into code, not retrieved | No RAG variance, no retrieval drift, no PDF at runtime |
| Validation before the simulator, not after | An unsafe pose is unrenderable, not merely discouraged |
| Versioned mechanical limit profiles | The manual contradicts itself; the platform records which reading was used |

---

## 2. The prosthesis

The hardware description is compiled from four technical manuals analysed during
development. **The PDFs are never read at runtime** — no RAG, no embeddings, no
vector store. Everything lives in `backend/app/domain/`.

**HANDi EPN V3** (Escuela Politécnica Nacional, Laboratorio "Alan Turing"),
built on the open-source HANDi Hand platform:

- **Controller** — ESP32 (Wemos D1 R32) + 2× Adafruit Motor Shield V3
- **Actuation** — 5× Pololu 380:1 HPCB 6 V gearmotors with 12 CPR magnetic
  encoders, plus 1× MG90S servo for thumb rotation
- **Driven DOF** — 6, one per serial command letter
- **Kinematic joints** — 15 modelled (D0 thumb rotation, then P/I/D per digit)
- **Proprioception** — 11 rotary potentiometers via a CD74HC4067 16:1
  multiplexer (channels C5..C15), 5 fingertip FSRs
- **Link** — Bluetooth SPP, device name `Handi EPN V3`, line-oriented ASCII

### Command set

| Cmd | Digit | Actuator | Range (Tabla 5) | Range (Anexo A) |
|-----|-------|----------|-----------------|-----------------|
| `A` | D5 | pinky | 0–600 | 0–350 |
| `B` | D4 | ring | 0–550 | 0–350 |
| `C` | D3 | middle | 0–600 | 0–440 |
| `D` | D2 | index | 0–550 | 0–350 |
| `E` | D1 | thumb lower / rotation | 0–130 | 0–120 |
| `F` | D1 | thumb upper / flexion | 0–400 | 0–100 |

Fourteen preset gestures: `O` open, `C` close, `P` pinch, `R` spiderman,
`W` partial claw, `Y` OK, `L` thumbs up, `M` call me, `H` three, `U` four,
`G` point, `S` stop, `X` calibrate, `I` init shields.

> **The `C` ambiguity.** A bare `C` closes the whole hand; `C400` addresses the
> middle finger. The parser resolves this by the presence of a numeric suffix,
> the technical context documents it explicitly, and there is a regression test
> for it.

> **The range discrepancy.** Tabla 5 in the manual body and Anexo A in the
> glossary publish different maxima. Rather than silently choosing one, the
> platform ships three versioned profiles — `TABLE_5_V3` (default),
> `ANNEX_A_V3` and `INTERSECTION` — and stamps every execution with the one it
> ran under. The same command can legitimately pass under one and fail under
> another; that is recorded, not hidden.

---

## 3. Prompt architecture

```
┌──────────────────────────────────────┐
│            SYSTEM PROMPT             │  frozen · behaviour contract
├──────────────────────────────────────┤
│          TECHNICAL CONTEXT           │  frozen · generated from the domain model
├──────────────────────────────────────┤
│           DYNAMIC PROMPT             │  varies · EMG window + hand + metadata
└──────────────────────────────────────┘
                   │
                   ▼
                LiteLLM
                   │
                   ▼
             JSON response
```

The researcher **never** assembles this. `build_prompt()` does it before every
inference and returns SHA-256 digests of each block.

1. **System Prompt** — role, output discipline, refusal rules. No numbers, so it
   can be versioned independently of the hardware description.
2. **Technical Context** — generated from `app/domain/` rather than transcribed,
   so the text the model reads can never drift from the validators the response
   is checked against. Fully editable in the UI; edits create a new version.
3. **Dynamic Prompt** — the only block that changes: the raw EMG matrix, the
   derived feature table, the hand, the experiment type and a pseudonymous
   subject reference.

---

## 4. Validation — the safety gate

```
parse → schema → protocol → consistency → range → kinematic → safety
```

| Stage | Rejects |
|---|---|
| `parse` | Not JSON. Fenced or prose-wrapped JSON is recovered but flagged. |
| `schema` | Missing, extra or malformed fields; wrong hand; unknown EMG channel |
| `protocol` | Malformed serial frame, invented command letter, duplicate actuator |
| `consistency` | `serial_command` disagreeing with `intent`/`gesture`/`commands` |
| `range` | Position outside the active limit profile |
| `kinematic` | Joint angle outside its mechanical range |
| `safety` | Exclusivity, speed envelope, collision risk, duration plausibility |

**A failure at any stage means the simulator does not move**, the execution is
marked failed and every issue is stored with a queryable code. The model's own
`safety` self-assessment is advisory only — the backend re-derives every field
independently, and a dishonest self-report is recorded as a warning metric.

---

## 4b. The EMG stimulus

The input is a **raw sample matrix**, not a summary:

```
N rows (time steps, ascending) × 8 columns (CH1…CH8)
amplitudes normalised to [-1.0, 1.0]
```

Read *across* a row for one instant, *down* a column for one electrode. A 200×8
window at 1 kHz is 200 ms.

Features (`rms`, `mav`, `zc`, `ssc`, `wl`, `min`, `max`, `variance`) are
**derived by the backend** and printed beneath the matrix — never supplied by
the caller. Anything a client sends in `features` is discarded and recomputed,
so a window whose summary contradicts its waveform cannot exist.

Windows longer than 256 rows are decimated with a uniform stride for the prompt,
and the excerpt is labelled as such; the feature table is always computed from
the complete window. Decimation is a stride rather than an average because
averaging would smooth away exactly the high-frequency content that `zc` and
`ssc` measure.

Three ways in:

| Route | Use |
|---|---|
| Paste / import | CSV, TSV, whitespace or JSON. A `CH1,CH2,…` header is ignored. Optional auto-normalise for raw µV or ADC counts. |
| Synthesise | Band-limited noise at per-gesture target RMS, labelled with a ground truth so accuracy is scored automatically. Seeded, therefore replayable across every model. |
| Live stream | `/ws/emg/{session}` pushes windows from the acquisition hardware; with `auto_run`, each frame fires a full execution. |

A transposed matrix (8 rows × N columns) is detected and named explicitly rather
than accepted — it is the single mistake most likely to silently corrupt an
experiment.

---

## 5. Stack

**Backend** — Python 3.13 · FastAPI · SQLAlchemy 2 (async) · PostgreSQL 17 ·
Alembic · LiteLLM · Pydantic v2

**Frontend** — Angular 22 (zoneless, signals) · Angular Material 3 ·
TailwindCSS · RxJS · Three.js

---

## 6. Running it

### With Docker

```bash
cp .env.example .env          # then edit
docker compose up --build
```

- API → http://localhost:8000/docs
- UI → http://localhost:4200

### Locally

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.seeds.seed
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm start
```

### LM Studio (primary runtime)

1. Open LM Studio, load a model.
2. Start the local server (**Developer → Start Server**, default port `1234`).
3. In the left panel the LM Studio chip turns green.
4. Click **Import loaded models** — the catalogue is populated from whatever is
   actually loaded, so the dropdown never lies about availability.

LiteLLM routes these as `lm_studio/<model-key>`. `litellm.drop_params` is on:
a GGUF runtime that ignores `top_k` or `seed` degrades to "not applied" rather
than erroring, and the dropped parameter is reported on the execution record.
Local providers are flagged `is_local`, so cost is recorded as 0 and
tokens/second becomes the meaningful efficiency metric.

---

## 7. Interface

Exactly 50 / 50.

Light theme throughout, built on five colours: `#001F3F` navy, `#D81B60` pink,
`#FFC107` amber, `#FFFFFF` white, `#000000` black. Navy carries structure and
valid states, pink carries the primary action and failures, amber carries
warnings. Material 3 system tokens are pinned to those exact hex values so
Material components and Tailwind utilities never disagree.

**Left — the laboratory.** Provider, model, temperature, top-p, top-k, max
tokens, seed, frequency and presence penalties, response format, hand, limit
profile, repetitions. The three prompt blocks (two editable, one read-only).
The EMG matrix panel: eight stacked traces, paste/import/synthesise, and a
read-only derived-feature table. A **manual / live toggle** switches between a
hand-supplied matrix and a streaming WebSocket session. Saved configurations and
full execution history, both replayable.

**Right — the simulator.** A procedurally generated anatomical hand built from
lofted superelliptical cross-sections rather than primitives: tapered phalanges
with condyle bulges at each joint, thenar and hypothenar eminences, metacarpal
tendon ridges on the dorsum, glossy nail plates, PBR skin with sheen and faked
subsurface scattering, image-based lighting and a soft-shadowed three-point rig.

**Pose and camera are separated deliberately.** The camera is fully yours —
drag to orbit, scroll to zoom, right-drag to pan, with a reset button. The hand
itself has no manual controls: `applyPose()` is its only movement entry point,
fed exclusively by validated backend frames, and angles are clamped against the
backend's joint limits before they reach a transform.

A left/right toggle sits in the viewport header. Switching **rebuilds the rig
with negated X** rather than applying `scale.x = -1`, because a negative scale
inverts every surface normal and breaks both the lighting and the shadow
terminator. The current pose is carried across the rebuild.

`loadGltf()` remains as a drop-in slot for a photogrammetry-grade mesh — bones
are matched by name against the joint ids, so no control logic changes.

---

## 8. Metrics recorded per execution

**Compliance** — valid JSON · bare JSON (no fences) · schema · protocol ·
within mechanical limits · safety

**Accuracy** (when the window carries a ground-truth label) — gesture
correctness · pose MAE · pose similarity · confidence calibration error

**Behaviour** — intent · detected pattern · actuators commanded · preset vs
custom pose · refusal rate

**Efficiency** — latency · time to first token · prompt/completion tokens ·
cost · tokens per second · output token efficiency

**Determinism** — canonical response fingerprint per repetition; identical
digests across repetitions at temperature 0 are direct evidence of determinism,
and divergence quantifies sampling instability.

`GET /experiments/{id}/comparison` returns the cross-model leaderboard with a
`comparable` flag that is **false** when the rows were not produced under the
same frozen context — the platform refuses to imply a ranking it cannot support.

---

## 9. Layout

```
backend/
  app/
    domain/        hand_spec · kinematics · protocol     ← the manuals, as code
    prompts/       system · technical context · dynamic · builder
    validation/    seven-stage pipeline + result objects
    models/        17 SQLAlchemy tables
    services/      LiteLLM gateway · execution orchestrator · metrics · EMG
    api/v1/        hand · providers · configurations · prompts · emg ·
                   executions · experiments
    ws/            live EMG ingestion + simulator fan-out
  alembic/         initial migration
  tests/           77 tests over domain, protocol, validation and prompts
frontend/
  src/app/
    core/          typed models · API client · signal store · sockets
    features/lab/  model config · EMG panel · prompt blocks · results
    features/simulator/  Three.js scene · procedural rig · PBR skin
```

---

## 10. Database

17 tables. Users · providers · models · sampling configurations · lab presets ·
system prompt versions · technical context versions · dynamic prompt templates ·
EMG windows (raw matrix + cached features) · EMG stream sessions · experiments ·
executions · validation results · validation issues · execution errors ·
execution metrics · simulator movements.

An execution snapshots the literal prompt text, the model and decoding
parameters, and all five content hashes — so a result survives later editing or
deletion of the rows it referenced.

A `simulator_movements` row exists **only** when validation passed. The absence
of a row for a failed execution is itself the audit trail proving the safety
gate held.

---

## 11. Testing

```bash
cd backend && python -m pytest tests -q
```

149 tests. Coverage focuses on the parts where a mistake reaches hardware or
silently corrupts an experiment: mechanical limits per profile, the `C` command
ambiguity, serial round-tripping, each of the seven validation stages, the
invariant that the frozen context hash is stable across EMG windows but changes
with the limit profile, and the EMG matrix contract — shape, amplitude bounds,
column-vs-row orientation, header handling, transposition detection, deadband
behaviour in the frequency features, and the guarantee that supplied features
are discarded and recomputed from the signal.

Two of them are not unit tests at all:

* `test_imports.py` walks every internal `from app.x import y` and checks the
  name exists. A renamed constant with one stale importer passes every unit test
  and then fails at container start, inside a uvicorn worker — this catches it
  in CI instead, with no database or web framework needed.
* `test_real_acquisition.py` runs the full path over an actual recording from
  the lab hardware (`CH0..CH7` header, 404 rows of signed converter counts),
  including the calibration trap where the declared full scale decides whether a
  window of movement reads as rest.

---

## 12. Toward real hardware

`SimulatorMovement.dispatched_to_hardware` and the normalised
`serial_command` are already in place. A hardware bridge subscribes to
`/ws/simulator`, opens the Bluetooth SPP link to `Handi EPN V3` and forwards
`serial_command` verbatim — the frame has already cleared every validation
stage, so the bridge needs no logic of its own beyond transport.
