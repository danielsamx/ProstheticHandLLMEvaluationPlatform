# Overview

**Languages:** [English](README.md) · [Español](../es/README.md)

Research platform for benchmarking large language models on one narrow,
safety-critical task: **turning an 8-channel surface EMG matrix into a validated
control command for the HANDi EPN V3 prosthetic hand.**

Not a chatbot. No conversations, no memory, no follow-up. Each execution is an
independent experiment: one frozen prompt, one EMG window, one model, one JSON
response, seven validation stages, one permanent record.

---

## Why the design looks like this

The claim the platform has to support is *"model A produces more accurate, more
consistent and safer prosthetic commands than model B"*. That is only defensible
if everything except the model is held constant. The architecture enforces it
structurally rather than by convention:

| Mechanism | Guarantee |
|---|---|
| Four-block prompt, first three frozen | Only the EMG payload varies between runs |
| `frozen_context_sha256` on every execution | Two runs are provably comparable, or provably not |
| Immutable prompt versions | Any published result reproduces byte for byte |
| Hardware spec compiled into code | No RAG variance, no retrieval drift, no PDF at runtime |
| Validation before the simulator | An unsafe pose is unrenderable, not merely discouraged |
| Versioned mechanical limit profiles | The manual contradicts itself; the platform records which reading applied |
| Append-only audit trail | Every change has an actor, a time and a diff |

---

## The prosthesis

Compiled from four technical manuals during development. **The PDFs are never
read at runtime** — no RAG, no embeddings, no vector store. Everything lives in
`backend/app/domain/`.

**HANDi EPN V3** — Escuela Politécnica Nacional, Laboratorio "Alan Turing", built
on the open-source HANDi Hand platform.

- ESP32 (Wemos D1 R32) + 2× Adafruit Motor Shield V3
- 5× Pololu 380:1 gearmotors with 12 CPR encoders, plus an MG90S servo
- 6 commanded degrees of freedom, 15 modelled joints
- 11 rotary potentiometers, 5 fingertip force sensors
- Bluetooth SPP, device name `Handi EPN V3`

| Cmd | Digit | Range (Tabla 5) | Range (Anexo A) |
|-----|-------|-----------------|-----------------|
| `A` | pinky | 0–600 | 0–350 |
| `B` | ring | 0–550 | 0–350 |
| `C` | middle | 0–600 | 0–440 |
| `D` | index | 0–550 | 0–350 |
| `E` | thumb rotation | 0–130 | 0–120 |
| `F` | thumb flexion | 0–400 | 0–100 |

Fourteen preset gestures: `O C P R W Y L M H U G S X I`.

> **The `C` ambiguity.** A bare `C` closes the hand; `C400` addresses the middle
> finger. Resolved by the numeric suffix, documented in the technical context,
> and covered by a regression test.

> **The range discrepancy.** Tabla 5 and Anexo A publish different maxima. Rather
> than silently choosing, the platform ships three versioned profiles —
> `TABLE_5_V3` (default), `ANNEX_A_V3`, `INTERSECTION` — and stamps every
> execution with the one it ran under.

Full detail: [hardware specification](hardware.md).

---

## The prompt

```
┌────────────────────────┐
│ 1 · SYSTEM PROMPT      │  frozen · behaviour contract
├────────────────────────┤
│ 2 · TECHNICAL CONTEXT  │  frozen · generated from the domain model
├────────────────────────┤
│ 3 · EMG KNOWLEDGE      │  frozen · electrode map and how to read it
├────────────────────────┤
│ 4 · DYNAMIC PROMPT     │  varies · EMG matrix and/or derived features
└────────────────────────┘
            ↓  LiteLLM  ↓
        JSON response
```

The researcher never assembles this. `build_prompt()` does it before every
inference and returns SHA-256 digests of each block.

Blocks 2 and 3 are **generated from `app/domain/`**, not transcribed — so the
limits the model is told about can never drift from the limits the validator
enforces, and the electrode map in the prompt is the one the feature extractor
groups by.

The three frozen blocks hash together into `frozen_context_sha256`, which is both
the comparability key and the identity of a **prompt configuration**: distinct
setups are deduplicated, and every execution points at the one that produced it.

---

## The stimulus

```
N rows (time steps, ascending) × 8 columns (CH1…CH8)
raw converter output — no filtering, rectification, normalisation or scaling
```

Features (`rms`, `mav`, `zc`, `ssc`, `wl`, `min`, `max`, `variance`) are
**derived by the backend**, never supplied. Anything a client sends is discarded
and recomputed, so a window whose summary contradicts its waveform cannot exist.

A transposed matrix is detected and named explicitly — it is the mistake most
likely to silently corrupt an experiment.

---

## Validation

```
parse → schema → protocol → consistency → range → kinematic → safety
```

Failure at any stage means **the simulator does not move**, the execution is
marked failed, and every issue is stored with a queryable code. The model's own
safety self-assessment is advisory: the backend re-derives every field
independently.

---

## Stack

**Backend** — Python 3.13 · FastAPI · SQLAlchemy 2 (async) · PostgreSQL 17 ·
Alembic · LiteLLM · Pydantic v2

**Frontend** — Angular 22 (zoneless, signals) · Angular Material 3 · TailwindCSS
· RxJS · Three.js

---

## Running it

```bash
cp .env.example .env
docker compose up --build
```

Interface at http://localhost:4200, API at http://localhost:8000/docs.

Full instructions: [installation and deployment](installation.md).

---

## Where to go next

| You are | Read |
|---|---|
| Running experiments | [User manual](user-manual.md) |
| Setting the system up | [Installation](installation.md) |
| Extending the platform | [Architecture](architecture.md) · [Developer guide](developer-guide.md) |
| Integrating with the API | [API reference](api.md) |
| Querying the record | [Database](database.md) |
| Working on the hardware | [Hardware specification](hardware.md) |
