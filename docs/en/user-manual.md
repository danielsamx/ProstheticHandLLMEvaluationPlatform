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
  "intent": "gesture",
  "gesture": "C",
  "serial_command": "C",
  "detected_pattern": "power_grasp",
  "confidence": 0.91
}
```

…which the simulator then renders as a closing hand.

`hand` may still be present and is **ignored**. The EMG of a grasp is the same
signal whichever hand produced it, so asking the model to name the side made it
guess at something the recording cannot tell it — and a wrong guess used to fail a
run that was otherwise correct.

Declining to act is also a valid answer, and it looks like this:

```json
{ "intent": "no_action", "serial_command": "" }
```

**Empty, not `S`.** `S` is STOP, a command that does something.

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
2. **Choose a provider and model** in *Model & decoding*, and confirm the thinking
   button is navy — suppressed.
3. **Set the decoding parameters.** Start at temperature 0 with a fixed seed.
4. **Load an EMG window** — paste a matrix or import a CSV.
5. **Choose what the dynamic block carries** — Matrix, Features or Both — and check
   the budget cards say it fits.
6. *(Optional)* **Type the expected serial command**, so the run is scored rather
   than merely validated.
7. *(Optional)* **Preview the prompt** in *Prompt blocks → 4 · Dynamic*, or the full
   prompt, to see exactly what the model will receive.
8. **Press Run Evaluation.**
9. **Read the result**: validation trace, metrics, raw response.
10. **Watch the simulator** — it moves only if validation passed.
11. **Repeat with another model**, changing nothing else.
12. **Export** when you have enough runs to analyse.

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

### The thinking button — not a decoding parameter

Beside **Refresh**, in the provider/model row rather than among the knobs above,
because it is a property of *how the model is asked* rather than of how it samples.

**Filled navy = thinking suppressed** (the default). **Amber outline = thinking
allowed.** Amber is the state that produces confusing results, so it is the one
drawn to catch your eye.

A reasoning model — anything Qwen3-class — splits its reply: the working-out goes to
a `reasoning_content` field, the answer to `content`. Given a hard classification and
a token ceiling, it can spend the ceiling deliberating and leave `content` **empty**,
and the platform records a parse failure for a model that was still thinking. This is
the single most common reason a run "fails" for no visible reason.

When suppressed, two switches are sent — `enable_thinking: false` (the Qwen3
convention, read by the chat template) and `reasoning_effort: "none"` (the OpenAI
spelling, read by the runtime). Runtimes disagree about which they honour, and one
that does not recognise a switch simply ignores it.

If a run's answer arrives on the reasoning channel anyway, the platform reads it as a
fallback **and records which channel it came from**. Treat that as a signal that the
suppression did not take, not as a success.

### Repetitions

Set **Repetitions** above 1 to run the identical experiment several times. The
result panel then reports a **determinism rate**: at temperature 0 with a fixed
seed, anything below 100% means the runtime is not honouring the seed. That is
worth knowing before you trust a model in a control loop.

---

## 9. Prompts

Every prompt sent to a model has **four** blocks, assembled by the backend:

```
┌────────────────────────┐
│ 1 · SYSTEM PROMPT      │  frozen — how the model must behave
├────────────────────────┤
│ 2 · TECHNICAL CONTEXT  │  frozen — what the hardware is
├────────────────────────┤
│ 3 · EMG KNOWLEDGE      │  frozen — how to read the signal
├────────────────────────┤
│ 4 · DYNAMIC PROMPT     │  varies — the EMG window
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

The prosthesis: actuators and their ranges, preset gestures, command syntax,
safety rules. **Generated from the code**, not written by hand — so the limits the
model is told about can never drift from the limits the validator enforces.

**Nothing about Bluetooth.** It once opened with "Bluetooth protocol / ASCII",
describing a link the model has no part in: it does not open the socket, choose the
baud rate, or see the wire. The command *syntax* is what it needs, and that is what
remains.

Editing is allowed (a hand-written context is a legitimate experimental
variable), and **Regenerate** always restores the canonical text.

### Block 3 — EMG knowledge

How to read the signal: the electrode map, which descriptors to weigh, and the
conditions under which STOP is the right answer.

Separate from block 2 on purpose. "What can this hand do?" changes only when the
hardware changes; "is co-contraction a stop, or physiological coactivation?" is a
methodological position you will revise repeatedly. Sharing one artefact would mean
every experiment on the second question also reversioned the first, and no effect
could be attributed to either.

This block carries the correction that mattered most in practice. An earlier
version said that near-equal flexor and extensor activity meant STOP — which is
wrong physiologically, because a normal grasp recruits antagonists to stabilise the
wrist, and it turned ordinary grasping into an emergency halt. STOP now requires
four conditions together, and the third does the real work: **rule out every
supported gesture first.**

It also states what inaction means: *"no_action means the hand does not move. It is
never S, and never O."* Without that line, models answering `no_action` filled the
command field with `S` — STOP — because the schema demanded a command and STOP was
the most-mentioned gesture in the prompt.

### Block 4 — Dynamic prompt

Read-only, and the only block that changes. Three buttons choose what it carries —
**Matrix**, **Features**, **Both** — and they apply immediately, so the block and
the token budget re-render as you press them.

**Rows sent** caps how much of the matrix is printed; press **Apply** to commit the
number. The cap decimates with a uniform stride rather than truncating, so the model
sees the whole movement instead of the pre-movement baseline. Because the stride is
a whole number, 64 on 404 rows yields 58 — and the panel reports what was actually
sent, not what you asked for.

### Reading the whole thing

**Preview · count tokens** assembles the exact prompt without spending anything, and
you can switch between the dynamic block alone and the **full prompt** — all four
blocks joined as the model will see them.

The budget cards break the total down by block. When it will not fit, the advice
names a row count you can act on rather than a token count you cannot.

### Versioning

Editing blocks 1, 2 or 3 creates a **new version**; existing versions are never
modified. A result published six months ago still resolves to the exact bytes that
produced it. All four ship at version **1.0**.

### Prompt configurations

The three frozen blocks together are hashed into `frozen_context_sha256`, and every
execution points at the **distinct configuration** that digest identifies. They are
deduplicated: three hundred runs under one setup leave one row, changing a block
files a second, and changing it back reuses the first.

Two runs under the same configuration are directly comparable. When a set spans
more than one, the platform reports **not comparable** rather than presenting a
ranking it cannot support.

The configurations table breaks results down **per model**, because a configuration
is only comparable within one.

---

## 10. The EMG stimulus

The input is a **raw sample matrix**:

```
N rows (time steps, ascending) × 8 columns (CH1…CH8)
raw converter output — nothing is filtered, rectified, normalised or scaled
```

Read *across* a row for one instant in time; read *down* a column to follow one
electrode. A 200×8 window at 1 kHz is 200 ms of signal.

| Column | Electrode | Group |
|---|---|---|
| CH1–CH4 | Flexors (volar forearm) | Closing |
| CH5–CH7 | Extensors (dorsal forearm) | Opening |
| CH8 | Brachioradialis | Postural |

### Loading one

**Paste matrix.** Rows pasted directly: CSV, TSV, whitespace or JSON. A header line
is ignored, whether it reads `CH0…CH7` or `CH1…CH8`.

**Import CSV.** Your acquisition file. Same header handling; a UTF-8 BOM is
stripped.

**Copy CSV / Clear.** The loaded window back out, or discarded.

**Stream live.** Switch **Live acquisition** on; the acquisition hardware pushes
windows over a WebSocket. With **Auto-run each frame**, every frame fires a full
execution.

The synthetic-window picker used to sit first in this row. It generated signals with
a known ground truth, which is useful for testing the platform, but a run against
synthesised EMG is not evidence about a model — and sitting first, it read as the
primary way in. The generator is still available at `GET /api/v1/emg/synthetic` for
checking the pipeline itself.

### No amplitude scaling — read this

**Values pass through unchanged.** There is no normalisation setting, no declared
full scale, no divisor. Nothing between the electrode and the prompt rescales
anything.

This is deliberate and it is the whole point of the measurement: what the model is
judged on is what the hardware produced. An earlier version of the platform divided
by a declared converter range, which meant every comparison depended on a number
typed by hand — and a wrong one silently made recordings incomparable while
everything still looked fine.

The interface reports `observed_peak` so you can see the signal's range. Nothing
acts on it.

**What survives the lack of scaling** is the quantity that was always the right one
to reason about: the **balance between muscle groups**. Gain, electrode placement
and subject all shift the absolute scale; the ratio survives all three, which is why
block 3 tells the model to weigh the pattern rather than any single threshold.

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
| **schema** | Missing or extra fields, unknown channel. `serial_command` may be empty **only** for `no_action` |
| **protocol** | Malformed serial frame, invented command letter |
| **consistency** | `serial_command` disagreeing with the structured fields |
| **range** | A position outside the mechanical limits |
| **kinematic** | A joint angle outside its physical range |
| **safety** | Exclusivity, speed, collision risk |

This is the diagnostic view. "Model B fails 30% of the time" is not actionable;
"model B fails at `parse` because it prefixes JSON with an explanation" is.

A declared inaction with an empty command short-circuits the last five stages —
there is nothing to check — and passes. It is a legitimate answer, recorded as
`refused_to_act` rather than as a failure.

### Metrics

Latency, tokens, cost, throughput, intent, detected pattern, confidence, and —
when you supplied an expected serial command — **Match**: ✓, ✗, or – for a run that
was never labelled.

Read **Match** and pass rate together. Passing validation only means the command
was well formed, in range and safe; a model that answers `O` to every window scores
100% on validation and 0% on control.

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
passed validation have a movement, so replay can never resurrect an unsafe pose. A
replay is logged like anything else that moved the hand.

### Testing a command by hand

The **Actuator state** row in the simulator has a text field and a **Test** button.
Type `C`, press Test, watch the hand close.

This separates two failures that look identical from the outside. When a run produces
no movement, the cause is either the model's answer or the plumbing — validator,
WebSocket, serial link, firmware. Every diagnostic that starts with an inference has
the model's judgement in the way; typing a command settles it without one.

It is **not** a shortcut around validation: a typed command goes through the same
seven stages. The mechanical stops do not care who chose the number, and a typo in a
text field can strip a gearmotor exactly as well as a bad model can.

A rejected command shows the validator's own message, which already names the
actuator, the value and the profile that refused it. `· no client` means accepted but
nothing was listening — a different outcome from rejection.

### The movement log

`/logs` — every command that moved the hand, which is **not** the same list as the
execution history. That records what models *answered*; this records what was
*transmitted*.

The two diverge in both directions. A pose that resolved is not a pose that was
delivered — the prosthesis link can be closed or drop mid-session. And commands no
model produced (manual tests, replays) move the hand exactly as a model's answer
does, and would otherwise be movements with no record explaining them.

Two destination columns rather than one "delivered" flag, because the simulator
renders from the backend while the hardware is driven from the browser: either can
arrive while the other does not, and that asymmetry is what you are usually trying to
diagnose.

Filter by origin — **Model** is evidence, **Manual** is a check on the plumbing,
**Replay** is neither.

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

### Every response fails at `parse`, or the response is empty

**Check the thinking button first.** An empty `content` from a reasoning model is by
far the most common cause, and it looks exactly like a malformed reply in the
metrics. Suppress thinking and run it again before changing anything else.

If the response is prose wrapped around the JSON instead:

1. Set **Response format** to `json_object` or `json_schema`.
2. Set temperature to 0.
3. Try a model with better instruction-following — small quantised models often
   cannot suppress a preamble.

Prose around the answer is a legitimate finding, not just a nuisance: it is the model
failing the task. An empty answer from an unsuppressed reasoning model is not — that
is a configuration problem, and recording it as the model's failure would be wrong.

### The model answers `no_action` when the EMG clearly shows a movement

Three things to check, in this order:

1. **Thinking suppressed?** See above.
2. **Does the prompt fit?** If LM Studio's *load* context is 8192 and the budget
   cards say 17,608 tokens, the matrix is being truncated and the model is reading a
   different stimulus from the one you chose. Switch to **Features**, or raise the
   load context, or cap the rows deliberately.
3. **Are you comparing against LM Studio's chat?** The chat runs at temperature 0.8
   with top-p 0.95 and your conversation history in context. It is a different
   experimental condition, not a second opinion.

`no_action` paired with a command — `{"intent": "no_action", "serial_command": "S"}` —
is a different matter and now fails at `consistency`. `S` is STOP, which *does*
something; inaction means the field is empty.

### Every response fails at `range`

The model is emitting positions outside the mechanical limits. Check which limit
profile is active — the same command can be legal under `TABLE_5_V3` and illegal
under `ANNEX_A_V3`, because the manual publishes two different envelopes.

### Every response fails at `range`

The model is emitting positions outside the mechanical limits. Check which limit
profile is active — the same command can be legal under `TABLE_5_V3` and illegal
under `ANNEX_A_V3`, because the manual publishes two different envelopes.

### Repeats differ at temperature 0

The runtime is not honouring the seed. Common with GGUF backends. Check the
execution record for **dropped parameters** — it lists exactly what the runtime
ignored.

### The run times out

`LLM_REQUEST_TIMEOUT_S` defaults to 1800 seconds, which is generous on purpose: a
large model with **GPU Offload at 0** can take minutes for a few hundred tokens. If
you see a timeout well under that number, an old value in `.env` is overriding the
default — Compose reads that file for interpolation *and* passes it into the
container, so a stale line there wins twice.

Both retry counters are zero by design. A silently retried experiment spends three
times the wall clock and records one result.

### The simulator does not move

First, distinguish the two cases:

- **A banner naming a stage** — validation failed, and this is correct behaviour. The
  banner names the stage and the reason.
- **No banner, nothing happens** — the plumbing, not the model. Type `C` into the
  **Test** field in the Actuator state row. If the hand moves, the transport is fine
  and the problem is upstream; if it does not, check the movement log at `/logs` to
  see whether the command was even recorded as published.

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
- **Supply the expected serial command.** Without an answer key, a model that
  replies `O` to every window scores 100% on validation and 0% on control, and
  nothing in the record can tell the difference.
- **Keep the thinking button in one state** across a comparison, and note which. It
  changes which channel the answer arrives on, which is not a small difference.
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
