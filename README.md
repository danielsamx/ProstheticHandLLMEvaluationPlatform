<div align="center">

<img src="frontend/src/assets/logo.webp" alt="Escuela Politécnica Nacional · Facultad de Ingeniería de Sistemas" width="250" height="96">

# Prosthetic Hand LLM Evaluation Platform

**HANDi EPN V3 · EMG → validated control commands**

[Documentación en español](docs/README.md)

</div>

---

Research platform for benchmarking large language models on one narrow,
safety-critical task: **turning an 8-channel surface EMG matrix into a validated
control command for the HANDi EPN V3 prosthetic hand.**

Not a chatbot. No conversations, no memory. Each execution is an independent
experiment: one frozen prompt, one EMG window, one model, one JSON response,
seven validation stages, one permanent record.

```bash
cp .env.example .env
docker compose up --build
```

Interface at http://localhost:4200 · API at http://localhost:8000/docs

| I want to… | Read |
|---|---|
| Run experiments | [User manual](docs/en/user-manual.md) |
| Install the system | [Installation & deployment](docs/en/installation.md) |
| Understand the design | [Architecture](docs/en/architecture.md) |
| Integrate with the API | [API reference](docs/en/api.md) |
| Query the record | [Database](docs/en/database.md) |
| Contribute code | [Developer guide](docs/en/developer-guide.md) |
| Know the hardware | [Hardware specification](docs/en/hardware.md) |

---

## Table of contents

- [How one run works](#how-one-run-works)
- [The laboratory, control by control](#the-laboratory-control-by-control)
  - [1 · Provider and model](#1--provider-and-model)
  - [2 · Decoding parameters](#2--decoding-parameters)
  - [3 · EMG input](#3--emg-input)
  - [4 · What the dynamic prompt carries](#4--what-the-dynamic-prompt-carries)
  - [5 · Expected serial command](#5--expected-serial-command)
  - [6 · The three prompt blocks](#6--the-three-prompt-blocks)
- [Live mode](#live-mode)
- [Connecting the physical prosthesis](#connecting-the-physical-prosthesis)
- [Reading the result](#reading-the-result)
- [The dashboard](#the-dashboard)

---

## How one run works

```
EMG window (N × 8 raw)
        │
        ▼
  Prompt assembly ─── block 1 System  ─┐
                      block 2 Context ─┤ frozen: identical on every run
                      block 3 Dynamic ─┘ variable: the only thing that changes
        │
        ▼
     The model ────► one JSON object
        │
        ▼
  parse → schema → protocol → consistency → range → kinematic → safety
        │                                                          │
        │ any stage fails                                          │ all pass
        ▼                                                          ▼
   recorded, hand does not move                        simulator (+ prosthesis)
```

The split between *frozen* and *variable* is the whole experimental design.
Blocks 1 and 2 are byte-identical across runs, so when two models disagree the
difference is attributable to the model rather than to the prompt. Block 3 is
the stimulus.

**You never write the prompt.** The backend assembles it. You choose what goes
into it, and you can read exactly what will be sent before spending a token.

---

## The laboratory, control by control

### 1 · Provider and model

**Provider** is fixed to LM Studio. Everything runs locally: no data leaves the
machine, there are no per-token costs, and a run can be repeated a year from now
without depending on a hosted model that may have been retired or silently
updated underneath you.

**Model** lists only what LM Studio currently has **loaded**. A catalogue entry
is not proof a model can run — offering one that is not loaded produces a
failure at inference time that looks like a network fault and wastes a great
deal of debugging. Press **Refresh** after loading a model in LM Studio.

The model's **context window** matters more here than its parameter count. LM
Studio loads models with a default context far below what the architecture
supports — commonly 4096 or 8192 — and that is the number that decides whether
your prompt fits. A 404-row EMG matrix needs roughly 18,000 tokens. See
[EMG input](#3--emg-input).

### 2 · Decoding parameters

These control **how the model picks each token**. They are the difference
between a measurement and an anecdote.

| Control | What it does | Why it is set this way |
|---|---|---|
| **Temperature** | Flattens or sharpens the probability distribution before sampling. `0` always takes the most likely token. | **Keep at 0.** This is a control task, not a writing task: there is one right answer and no value in variety. Above 0, repeating a run can give a different command, which makes any single result unrepeatable. The read-out turns amber above 0 as a warning. |
| **Top-P** | Nucleus sampling: consider only the smallest set of tokens whose probabilities sum to P. | At temperature 0 it has no effect — greedy decoding ignores it. Left at `1.00` so it cannot silently interact if you raise the temperature. |
| **Top-K** | Consider only the K most likely tokens. | Disabled unless the runtime declares support. Same reasoning as Top-P. |
| **Max tokens** | Hard ceiling on the reply length. | `320`. The response is a JSON object with up to six command entries; below about 200 it truncates mid-object. **A truncated reply is indistinguishable from a malformed one in the metrics**, so too small a value records a budget mistake as the model's failure. |
| **Seed** | Fixes the sampler's random number generator. | `42`. Together with temperature 0, this is what makes a run reproducible. Determinism is a property of the sampler — not something a model can be instructed into — which is why the prompt no longer asks for it. |
| **Freq. penalty** | Penalises tokens already used, by frequency. | `0`. Designed to stop prose repeating itself. A command may legitimately repeat a letter (`A320,B180`), so a penalty here actively distorts the output. |
| **Presence penalty** | Penalises tokens already used, at all. | `0`, same reason. |
| **Response format** | Asks the runtime to constrain decoding. | `json_schema`. The response schema is sent with the request so the runtime **cannot emit** malformed JSON. This removes the largest single failure mode — prose wrapped around the answer — before it happens rather than catching it afterwards. LM Studio rejects `json_object`; the platform upgrades that request automatically. |

### 3 · EMG input

The stimulus is a matrix: **N rows × 8 columns**, raw, unprocessed.

- **Rows** are time steps in ascending order.
- **Columns** are `CH1…CH8`, in that order.
- **Values** are raw converter output. No filtering, no rectification, no
  normalisation, no scaling.

The channel map is anatomical, and it is the reason a model can say anything at
all about intent:

| Channel | Muscle | Group |
|---|---|---|
| CH1 | Flexor digitorum superficialis | flexor |
| CH2 | Flexor carpi radialis | flexor |
| CH3 | Flexor carpi ulnaris | flexor |
| CH4 | Palmaris longus | flexor |
| CH5 | Extensor digitorum communis | extensor |
| CH6 | Extensor carpi radialis longus | extensor |
| CH7 | Extensor carpi ulnaris | extensor |
| CH8 | Brachioradialis | reference |

The decisive quantity is the **balance between groups**, never an absolute
number. Gain, electrode placement and subject all shift the absolute scale; the
ratio survives all three:

```
flexor_ratio = flexor RMS / (flexor RMS + extensor RMS)

  > 0.65   volar group dominates    → closing / grasping
  < 0.35   dorsal group dominates   → opening / extension
  ≈ 0.50   both strong              → co-contraction, normally a deliberate STOP
  all channels near the floor       → rest, no action
```

**Three ways to load a window:**

- **Import CSV** — your acquisition file. A header row (`CH0…CH7` or `CH1…CH8`)
  is detected and skipped; a UTF-8 BOM is stripped.
- **Paste matrix** — CSV, TSV, whitespace or JSON.
- **Load labelled synthetic window** — generated signals with a known correct
  answer, for testing the platform itself rather than the model.

**Rows sent** caps how much of the matrix reaches the prompt. Leave it blank to
send everything, which is the default and the honest choice. Two things to know:

- The cap **decimates with a uniform stride**, it does not truncate. A cap of 64
  on a 404-row window shows every 7th row, spanning the whole movement. Taking
  the first 64 rows would show the model the pre-movement baseline and nothing
  else.
- Because the stride is a whole number, a cap of 64 on 404 rows yields 58 rows,
  not 64. The panel and the record both report what was actually sent.

Press **Apply** to commit the number. A number field fires on every keystroke,
so typing "128" would briefly request 1 row, then 12; the button gives the value
one unambiguous moment to take effect.

### 4 · What the dynamic prompt carries

Three mutually exclusive options, and a genuine experimental variable — not a
display preference.

| Option | The model receives | The question it answers |
|---|---|---|
| **Matrix** | The raw N × 8 samples, nothing else | *Can an LLM read raw EMG?* The hardest condition, and the one this platform exists to measure. |
| **Features** | Per-channel RMS, MAV, ZC, SSC, WL, min, max and the flexor ratio | *Can an LLM act on extracted features?* A much easier task — the signal processing has been done for it. |
| **Both** | The matrix, then the descriptors | The most information the model can be given. |

The descriptors are always computed over the **complete** window, even when the
printed matrix is capped: a summary of the excerpt would describe something you
never chose to analyse.

**Features mode is also the escape hatch when a prompt will not fit.** The
descriptor table is a fixed size whatever the recording length — a 4,000-sample
window costs the same as a 32-sample one.

### 5 · Expected serial command

The command a domain expert says this window *should* produce. Optional.

This is what turns a run from a demonstration into a measurement. Passing
validation only means the command was well formed, in range and safe — a model
that answers `O` to every window scores **100% on validation and 0% on
control**. Without an answer key, nothing in the system can tell the difference.

- Typed loosely, stored tidily: `a320, b180` becomes `A320,B180`.
- Compared against the **normalised** command, so formatting never counts as a
  wrong answer.
- **Never placed in any prompt.** It is the answer key.
- Runs with no expected command are excluded from the accuracy denominator —
  "not compared" and "compared and wrong" are different facts.

### 6 · The three prompt blocks

| Block | Contains | Editable |
|---|---|---|
| **1 · System** | Role and output discipline. No numbers. | Yes, versioned |
| **2 · Technical Context** | The hand: commands, ranges, coupling, protocol, safety, EMG map, response schema. | Yes, versioned |
| **3 · Dynamic** | The EMG for this run. | Template only — the content is assembled |

Blocks 1 and 2 are **frozen**: identical bytes on every run. Editing either
creates a new immutable version, so past results stay attributable to the exact
wording that produced them.

Block 2 is **generated from the domain model**, not typed. Every number in it
comes from the same source the validators use, so the prompt can never promise
the model a range the pipeline then rejects. **Regenerate** restores it from the
domain if a hand-edited version has drifted.

**Preview · count tokens** assembles the exact prompt without spending anything.
Switch between the dynamic block alone and the **full prompt** — system, context
and dynamic joined as the model will see them. The four cards break the budget
down by block; when the total will not fit, the advice names a row count you can
act on rather than a token count you cannot.

---

## Live mode

The **Manual / Live** toggle switches the source of the EMG window from a file
you loaded to a WebSocket stream.

**How it works:** a device or script connects to `ws://localhost:8000/ws/emg`
and pushes frames. Each frame is a complete N × 8 window, not a single sample —
the model reasons over a window, so the stream must deliver one.

**Auto-run** decides what happens when a frame arrives:

- **Off** — the frame replaces the current window. You inspect it and press Run
  yourself. Use this while setting up.
- **On** — every frame triggers an execution automatically. This is the
  closed-loop condition: EMG in, command out, hand moves.

The chips beside the toggle show the connection state and two counters: frames
received and runs triggered. They diverge whenever the model is slower than the
stream, which is the number that tells you whether real-time control is
plausible on this hardware at all.

**Before enabling auto-run**, be aware that every frame costs a full inference.
On a local CPU model that is seconds, not milliseconds. Check the latency of a
manual run first.

---

## Connecting the physical prosthesis

The **Connect hand** button in the simulator header opens a link to the real
device. When it is open, every validated command goes to **both** the prosthesis
and the simulator. When it is closed, commands go to the simulator only — an
experiment is never blocked by the absence of hardware.

### Why Web Serial and not Web Bluetooth

The firmware speaks **Bluetooth SPP at 115200 baud**. SPP is Bluetooth
*Classic*, and the Web Bluetooth API only reaches BLE GATT services — it cannot
open an SPP socket at all. An implementation built on Web Bluetooth would fail
against this hardware no matter how carefully it was written.

What does work: **pair the prosthesis in your operating system first.** The OS
exposes the SPP link as a virtual serial port, and the Web Serial API opens that
port at the documented 115200 baud, 8N1 — matching the protocol specification
exactly.

A BLE path exists for firmware builds that expose a Nordic UART service instead.
It is a genuine alternative, not a fallback.

### Steps

1. Pair the HANDi EPN V3 in your operating system's Bluetooth settings.
2. Open the interface in **Chrome or Edge on desktop** — Web Serial is
   Chromium-only; Firefox and Safari do not implement it.
3. Press **Connect hand** and pick the port in the browser's chooser.
4. The button turns navy and counts the commands sent.

Pressing it again returns the hand to `OPEN` before disconnecting. The safety
specification requires this: left in a grip the tendons stay loaded, which is
bad for the printed linkage and worse for whatever is being held.

### What can and cannot reach the motors

Only frames that cleared **all seven validation stages** are ever transmitted.
There is no code path from a raw model response to the serial port. The browser
is the last place that should be deciding whether a pose is safe, so it does
not: the backend decides, and the browser relays only what the backend already
approved.

The 50 ms minimum interval between transmissions is enforced in the link itself.
A model cannot violate it — it does not control timing — but a repetition run or
a reconnect could, and the motor driver is what would pay for it.

---

## Reading the result

**The seven gates**, in the order they run. The first red one is where the model
actually broke down; the ones after it were never reached, not passed.

| Stage | Checks |
|---|---|
| **parse** | A JSON object could be recovered at all |
| **schema** | It has the declared shape and no invented fields |
| **protocol** | `serial_command` is a well-formed, existing command |
| **consistency** | The command agrees with `intent`, `gesture` and `commands` |
| **range** | Positions are inside the active limit profile |
| **kinematic** | The pose is physically reachable |
| **safety** | Exclusivity, actuator count, collision rules |

`consistency` exists only because the response states its decision twice. A
`serial_command` of `A320` beside `intent: "no_action"` is a model that has
contradicted itself, and executing either half would be executing something it
never coherently decided.

**Metrics worth understanding:**

- **Clean reply** — the response was bare JSON, with no fence or prose around
  it. The sharpest single measure of instruction adherence.
- **Confidence** and **calibration error** — what the model claimed about
  itself, and how far that claim was from the truth. A model that is wrong at
  0.9 and one that is wrong at 0.3 fail equally on accuracy and very differently
  here. For a device that moves a hand, the second is the one you can build a
  safety threshold on.
- **Match** — the produced command against your expected command. ✓, ✗, or – for
  a run that was never labelled.

---

## The dashboard

The full record, aggregated in the database rather than over whatever page the
browser happens to have loaded.

**Command accuracy** answers "was it right", as distinct from pass rate which
answers "was it well formed and safe". The denominator is shown with it: 100% of
three runs and 100% of three hundred are different claims.

The **Input** column shows which rendering each run saw (`matrix`, `features`,
`both`) and how many rows. Runs under different input conditions are different
experiments; the column exists so they are not read as one.

**Mixed conditions** appears when the loaded rows did not all share one frozen
prompt context. The per-model comparison is then not like-for-like, and
presenting it as a ranking would imply something the data cannot carry.

**Export CSV** streams from the API so the file is byte-identical to what the
API produces, with every run — including failures — and the conditions that
produced it.

---

<div align="center">

Escuela Politécnica Nacional · Facultad de Ingeniería de Sistemas

</div>
