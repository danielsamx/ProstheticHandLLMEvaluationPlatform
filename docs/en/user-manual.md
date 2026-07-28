# User manual

*Prosthetic Hand LLM Evaluation Platform — HANDi EPN V3*

**Languages:** [English](user-manual.md) · [Español](../es/manual-usuario.md)

---

## Table of contents

1. [What this system is for](#1-what-this-system-is-for)
2. [Before you start](#2-before-you-start)
3. [Signing in](#3-signing-in)
4. [The screen, module by module](#4-the-screen-module-by-module)
5. [A complete run, start to finish](#5-a-complete-run-start-to-finish)
6. [Projects](#6-projects)
7. [Choosing a model](#7-choosing-a-model)
8. [Decoding parameters](#8-decoding-parameters)
9. [Prompts](#9-prompts)
10. [The EMG stimulus](#10-the-emg-stimulus)
11. [Running an evaluation](#11-running-an-evaluation)
12. [Reading the results](#12-reading-the-results)
13. [History and replay](#13-history-and-replay)
14. [Saved configurations](#14-saved-configurations)
15. [Exporting for analysis](#15-exporting-for-analysis)
16. [Traceability and audit](#16-traceability-and-audit)
17. [Troubleshooting](#17-troubleshooting)
18. [Good practice](#18-good-practice)

---

## 1. What this system is for

The platform answers one question: **which language model turns surface EMG into
the most accurate, most consistent and safest control commands for a prosthetic
hand?**

It is not a chatbot. There is no conversation, no memory, no follow-up. Each run
is a self-contained experiment: one frozen prompt, one EMG window, one model, one
JSON response, seven validation stages, one permanent record.

That design is deliberate. If the model could remember the previous question, you
could no longer attribute a difference in results to the model itself — it might
just be reacting to context you did not control.

### What a successful run produces

A JSON command the prosthesis firmware could execute verbatim, for example:

```json
{
  "hand": "right",
  "intent": "gesture",
  "gesture": "C",
  "serial_command": "C",
  "detected_pattern": "power_grasp",
  "confidence": 0.91
}
```

…which the simulator then renders as a closing hand.

---

## 2. Before you start

| Requirement | Detail |
|---|---|
| Browser | Chrome, Edge, Firefox or Safari, current version |
| Screen | 1280 px wide or more is comfortable; below 768 px the panels stack |
| Backend | Running and reachable — the top bar shows the connection state |
| A model | At least one, either loaded in LM Studio or reachable through an API key |

### If you are using LM Studio

LM Studio is the primary runtime for this project, because it keeps the models,
the data and the results on your own machine.

1. Open LM Studio and load a model.
2. Go to **Developer → Start Server** (default port 1234).
3. Confirm the log shows `http://localhost:1234/v1/models` among the endpoints.
4. In the platform's top bar, the **LM Studio** chip should be amber. If it is
   pink, the backend cannot reach it — see [Troubleshooting](#17-troubleshooting).

---

## 3. Signing in

Where authentication is enabled, sign in with the address your institution
issued. Your identity is attached to everything you do — every execution, every
prompt edit, every export — because that is what makes the record auditable.

If the platform is deployed on a single trusted workstation, authentication may
be disabled. In that case executions are recorded without an actor, and the
audit trail identifies the session and the machine rather than a person.

**Signing out** ends the session and is itself an audited event.

---

## 4. The screen, module by module

The window is split exactly in half.

```
┌──────────────────────────────────────────────────────────────────┐
│  EPN · FIS logo   Prosthetic Hand LLM Evaluation Platform    ●●●  │  Top bar
├───────────────────────────────┬──────────────────────────────────┤
│                               │                                  │
│   LABORATORY (left)           │   SIMULATOR (right)              │
│                               │                                  │
│   ▸ Model & decoding          │   3D hand                        │
│   ▸ EMG input · 8 channels    │   Left / Right toggle            │
│   ▸ Prompt blocks             │   Drag to rotate, scroll to zoom │
│   ▸ Result                    │                                  │
│   ▸ Configurations & history  │   Actuator read-out A–F          │
│                               │                                  │
│   [ Run Evaluation ]          │                                  │
└───────────────────────────────┴──────────────────────────────────┘
```

### Top bar

Status at a glance:

| Chip | Meaning |
|---|---|
| **6 DOF / 11 POT / 5 FSR** | The prosthesis specification the backend loaded |
| **LM Studio** (amber) | Reachable, with N models loaded |
| **LM Studio** (pink) | Not reachable |
| **sensors** (amber) | The simulator feed is connected |

### Left panel — the laboratory

Five collapsible sections; **Model & decoding**, **EMG input** and **Result** are
open by default because they are the ones you touch on every run.

### Right panel — the simulator

An anatomical hand rendered from the validated command.

**You control the camera; you do not control the hand.** Drag to orbit, scroll to
zoom, right-drag to pan, and use the reset button to return to the default view.
The pose itself only ever comes from a model response that passed every
validation stage — there is no slider to move a finger by hand, on purpose.

---

## 5. A complete run, start to finish

1. **Pick a project** so the run is filed where you will look for it later.
2. **Choose a provider and model** in *Model & decoding*.
3. **Set the decoding parameters.** Start at temperature 0 with a fixed seed.
4. **Load an EMG window** — paste a matrix, import a CSV, or generate a labelled
   synthetic one.
5. *(Optional)* **Preview the prompt** in *Prompt blocks → 3 · Dynamic* to see
   exactly what the model will receive.
6. **Press Run Evaluation.**
7. **Read the result**: validation trace, metrics, raw response.
8. **Watch the simulator** — it moves only if validation passed.
9. **Repeat with another model**, changing nothing else.
10. **Export** when you have enough runs to analyse.

---

## 6. Projects

A **project** is the container for a line of investigation. An **experiment**
inside it pins one set of frozen conditions; the **executions** are the
individual runs.

```
Project  "Grasp classification across 7B models"
  └── Experiment  "Table 5 limits, right hand, temperature 0"
        ├── Execution  qwen2.5-7b   · rep 0
        ├── Execution  qwen2.5-7b   · rep 1
        └── Execution  llama-3.1-8b · rep 0
```

### Creating one

`POST /api/v1/projects` with a name; the URL slug is generated and de-duplicated
automatically. Record the **research question** — it is the field that makes a
project understandable to someone reading it a year later, including you.

### Archiving and deleting

Archiving hides a project from the active list. Deleting is a **soft delete**:
the row is flagged, nothing is destroyed, and it can be restored. Experiments
that produced published results stay reconstructible forever — a hard delete
would break the traceability the platform exists to provide.

---

## 7. Choosing a model

### Local models via LM Studio

1. Load the model in LM Studio and start its server.
2. Press **Import loaded models** in the left panel.
3. The catalogue is filled from what is *actually loaded*, so the dropdown never
   offers a model that is not there.

New entries are registered conservatively: JSON mode on, JSON Schema off, seed
and top-k available. Raise those flags per model once you have verified the
runtime honours them.

### Hosted models

Set the provider's API key in `.env` and restart the backend. Hosted models
report a real monetary cost; local models report zero, and tokens per second
becomes the meaningful efficiency measure instead.

### What to compare

Comparing a 7B local model against a hosted frontier model tells you little on
its own — they differ in far more than one variable. The informative comparisons
are between models of similar size, or between configurations of one model.

---

## 8. Decoding parameters

| Parameter | Range | Notes |
|---|---|---|
| **Temperature** | 0–2 | 0 for reproducibility. Anything above makes repeats diverge. |
| **Top-P** | 0.01–1 | Leave at 1 when temperature is 0. |
| **Top-K** | ≥1 | Disabled unless the model declares support. |
| **Max tokens** | ≥1 | 1024 is ample; the response is a small JSON object. |
| **Seed** | any integer | Fixing it is what makes a run replayable. |
| **Frequency / presence penalty** | −2 to 2 | Leave at 0. Penalising repetition on a fixed JSON schema hurts. |
| **Response format** | text / json_object / json_schema | Prefer the strictest the model supports. |

> **A knob greyed out** means the catalogue records that this model does not
> support it. Sending it anyway would have it silently dropped, and the run would
> look reproducible when it is not.

### Repetitions

Set **Repetitions** above 1 to run the identical experiment several times. The
result panel then reports a **determinism rate**: at temperature 0 with a fixed
seed, anything below 100% means the runtime is not honouring the seed. That is
worth knowing before you trust a model in a control loop.

---

## 9. Prompts

Every prompt sent to a model has three blocks, assembled by the backend:

```
┌────────────────────────┐
│ 1 · SYSTEM PROMPT      │  frozen — how the model must behave
├────────────────────────┤
│ 2 · TECHNICAL CONTEXT  │  frozen — what the hardware is
├────────────────────────┤
│ 3 · DYNAMIC PROMPT     │  varies — the EMG window
└────────────────────────┘
```

**You never write the final prompt.** The backend assembles it before every
inference. That asymmetry is the experimental design made visible: you control
the constants, the platform controls the variable.

### Block 1 — System prompt

Behaviour only: respond in JSON, never in prose, never invent a command, refuse
rather than guess. Contains no numbers, so it can be versioned independently of
the hardware description.

### Block 2 — Technical context

The prosthesis: commands, ranges, kinematics, protocol, safety rules, output
schema. **Generated from the code**, not written by hand — so the limits the
model is told about can never drift from the limits the validator enforces.

Editing is allowed (a hand-written context is a legitimate experimental
variable), and **Regenerate** always restores the canonical text.

### Block 3 — Dynamic prompt

Read-only. Press **Preview assembled prompt** to see exactly what will be sent,
without spending a token.

### Versioning

Editing block 1 or 2 creates a **new version**; existing versions are never
modified. A result published six months ago still resolves to the exact bytes
that produced it.

### The frozen context hash

Under the preview you will find `frozen_context_sha256`. Two runs sharing that
value saw identical constants and are directly comparable. When they differ, the
comparison endpoint flags the set as **not comparable** rather than presenting a
ranking it cannot support.

---

## 10. The EMG stimulus

The input is a **raw sample matrix**:

```
N rows (time steps, ascending) × 8 columns (CH1…CH8)
amplitudes normalised to [-1.0, 1.0]
```

Read *across* a row for one instant in time; read *down* a column to follow one
electrode. A 200×8 window at 1 kHz is 200 ms of signal.

| Column | Electrode | Group |
|---|---|---|
| CH1–CH4 | Flexors (volar forearm) | Closing |
| CH5–CH7 | Extensors (dorsal forearm) | Opening |
| CH8 | Brachioradialis | Postural |

### Three ways to load one

**Paste or import.** CSV, TSV, whitespace or JSON. A header line is ignored,
whether it reads `CH0…CH7` or `CH1…CH8`.

**Synthesise.** Pick a gesture from the dropdown. The window is generated with a
known ground truth, so accuracy is scored automatically. Seeded, therefore
replayable across every model.

**Stream live.** Switch **Live acquisition** on; the acquisition hardware pushes
windows over a WebSocket. With **Auto-run each frame**, every frame fires a full
execution.

### Amplitude scaling — read this

Acquisition hardware produces converter counts, not normalised values, so the
import step has to rescale them. How it does that matters:

| Mode | What it does | When |
|---|---|---|
| **Declared full scale** | Divides by the converter's range | **Default.** Use this. |
| **Already −1…1** | Rejects anything outside range | Data already normalised |
| **Per-window peak** | Divides by this window's own maximum | Almost never |

> **Why peak scaling is dangerous.** It normalises each window by its own
> maximum, so a resting window and a maximal grasp both come out peaking at 1.0.
> The amplitude difference between them — the thing this platform compares — is
> destroyed. The interface warns you whenever it is selected.

Set **Full scale** to your hardware's actual converter range (512 for a 10-bit
signed ADC, 2048 for 12-bit). If you leave it blank the value is inferred from
the window and flagged, because an inferred divisor differs between recordings
and makes them incomparable.

**Check the aggregate reading.** The technical context tells the model that a
mean RMS below 0.10 means rest. If your recording of a movement reports mean RMS
0.03, the declared full scale is too large and the model is being told "rest"
about a window of activity.

### The traces

Eight stacked plots: pink for flexors, navy for extensors, amber for
brachioradialis. The three-way split makes the flexor/extensor balance — which is
what decides open from close — readable at a glance.

### The feature table

Read-only. RMS, MAV, zero crossings, slope sign changes, waveform length, min,
max. **Derived from the matrix by the backend**, never supplied by you: a window
whose summary contradicted its waveform would be undetectable otherwise.

---

## 11. Running an evaluation

Press **Run Evaluation**. The button is disabled until a configuration is
selected and the matrix is valid.

What happens:

1. The prompt is assembled and hashed.
2. The request goes to the model through LiteLLM.
3. The response passes through seven validation stages.
4. Everything is written to the database.
5. **If and only if validation passed**, the simulator receives the pose.

A failed run is still a complete record — the prompt, the response, the failure
reason and the timings are all stored. Failures are data.

---

## 12. Reading the results

### The headline

Green banner and a serial command, or a pink banner naming the stage that
rejected the response.

### The validation trace

Seven segments:

```
parse → schema → protocol → consistency → range → kinematic → safety
```

Navy = passed, pink = the stage that rejected it, grey = never reached.

| Stage | Rejects |
|---|---|
| **parse** | Not JSON. Prose, apologies, code fences. |
| **schema** | Missing or extra fields, wrong hand, unknown channel |
| **protocol** | Malformed serial frame, invented command letter |
| **consistency** | `serial_command` disagreeing with the structured fields |
| **range** | A position outside the mechanical limits |
| **kinematic** | A joint angle outside its physical range |
| **safety** | Exclusivity, speed, collision risk |

This is the diagnostic view. "Model B fails 30% of the time" is not actionable;
"model B fails at `parse` because it prefixes JSON with an explanation" is.

### Metrics

Latency, tokens, cost, throughput, intent, detected pattern, confidence, and —
when the window is labelled — whether the gesture was correct.

### Determinism

With repetitions above 1: how many distinct responses came back, and the modal
agreement rate.

### Raw response

Expandable. Worth reading when a model fails at `parse` — the failure is usually
visible immediately.

---

## 13. History and replay

The **Configurations & execution history** section lists recent runs: model,
time, latency, and either the serial command or the failing stage.

**Replay** re-renders a stored movement in the simulator. Only executions that
passed validation have a movement, so replay can never resurrect an unsafe pose.

---

## 14. Saved configurations

The bookmark button next to **Run Evaluation** saves the current model and
decoding parameters under a name. Saved configurations appear in the history
section and are applied with one click.

Save a configuration **before** starting a comparison, then apply the same one to
every model. That is what keeps the comparison honest.

---

## 15. Exporting for analysis

`POST /api/v1/export/executions.csv` (also `.jsonl` and `.json`).

One row per execution with every variable already flattened — model, decoding
parameters, stimulus descriptors, outcome, cost, timing — so the file loads
straight into pandas or R with no joins.

```python
import pandas as pd

df = pd.read_csv("executions-20260728-101500.csv")

# Validation pass rate by model, only within one frozen context
comparable = df[df.frozen_context_sha256 == df.frozen_context_sha256.mode()[0]]
comparable.groupby("litellm_model").validation_passed.mean().sort_values()
```

Filter by project, experiment, date range or model. Two defaults are deliberate:

- **Failures are included.** Excluding them would silently bias any success rate
  you compute.
- **Prompts and matrices are excluded.** They multiply file size roughly
  thirtyfold and far more respectively. Enable them when you need them.

`GET /api/v1/export/columns` returns the stable column order, so a script can
rely on it across releases.

---

## 16. Traceability and audit

### Reconstructing a past run

`GET /api/v1/traceability/{execution_id}` returns, in one payload: which prompt,
which model, which parameters, which stimulus, what came back, how long it took,
how many tokens, who ran it, from where, and when.

It also returns **`reproducible`**, and when that is false, exactly which pieces
are missing. A record that merely looks complete is worse than one that admits a
gap.

### The audit trail

`GET /api/v1/audit` — every project created, prompt edited, model imported,
configuration changed, export requested, session opened or closed. Each entry
records the actor, the action, the time, the outcome and a field-level diff of
what changed.

The trail is **append-only**. Entries are never updated or deleted.

`GET /api/v1/audit/entity/{type}/{id}` shows everything that has happened to one
entity.

---

## 17. Troubleshooting

### "LM Studio is not reachable"

| Check | How |
|---|---|
| Is the server started? | LM Studio → Developer → Start Server |
| Is a model loaded? | Just-in-time loading is not always enough |
| Right port? | The log should show `http://localhost:1234/v1/models` |
| Backend in Docker? | It reaches your machine at `host.docker.internal`, not `localhost`. Leave `LM_STUDIO_API_BASE` unset in `.env` and the default applies. |

### "Cannot reach the backend"

```bash
docker compose ps            # is it up?
docker compose logs backend --tail 40
curl http://localhost:8000/health
```

If the API is up but the browser cannot reach it, it is CORS. Reaching the UI at
`127.0.0.1` or a LAN address is a *different origin* from `localhost`; in
development the backend accepts loopback and private ranges on any port.

### The model catalogue is empty

Reload the page after a backend restart. If it stays empty, load a model in LM
Studio and press **Import loaded models**.

### Every response fails at `parse`

The model is writing prose around the JSON. Try:

1. Set **Response format** to `json_object` or `json_schema`.
2. Set temperature to 0.
3. Try a model with better instruction-following — small quantised models often
   cannot suppress a preamble.

This is a legitimate finding, not just a nuisance: it is the model failing the
task.

### Every response fails at `range`

The model is emitting positions outside the mechanical limits. Check which limit
profile is active — the same command can be legal under `TABLE_5_V3` and illegal
under `ANNEX_A_V3`, because the manual publishes two different envelopes.

### Repeats differ at temperature 0

The runtime is not honouring the seed. Common with GGUF backends. Check the
execution record for **dropped parameters** — it lists exactly what the runtime
ignored.

### A movement window reads as "rest"

The declared full scale is too large for your hardware. See
[Amplitude scaling](#10-the-emg-stimulus).

### The simulator does not move

Correct behaviour when validation failed. Read the banner: it names the stage and
the reason.

### The hand-switch is slow the first time

The second rig is built on first use. Subsequent switches are instant.

---

## 18. Good practice

### For a defensible comparison

1. **Freeze the prompts first.** Do not edit them mid-comparison.
2. **Check the frozen context hash.** Different hashes mean incomparable runs.
3. **Use the same EMG windows** across every model. The checksum proves it.
4. **Temperature 0, fixed seed**, at least to start.
5. **Repeat.** A single run of a stochastic system tells you almost nothing.
6. **Record the limit profile** in your write-up. It changes what counts as a
   valid answer.

### For a trustworthy record

- Write the **research question** on the project. Your future self will need it.
- Use **labelled windows** where you can — accuracy is then scored without
  manual annotation.
- **Declare the full scale.** An inferred one is not comparable across
  recordings.
- **Do not delete failed runs.** They are the most informative rows in the file.

### For a meaningful evaluation

- Compare **like with like**. A 7B local model against a hosted frontier model
  differs in too many variables to attribute anything.
- Look at **how** models fail, not only how often.
- Treat a **refusal as a success** when the input is genuinely ambiguous.
  Refusing to move is safer than moving incorrectly, and the system prompt says
  so explicitly.
- Watch **calibration**, not just accuracy. A model that is confidently wrong is
  more dangerous in a control loop than one that is uncertain and correct.
