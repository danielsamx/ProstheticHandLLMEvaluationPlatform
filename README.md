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
  - [2 · Thinking, and why it must be suppressed](#2--thinking-and-why-it-must-be-suppressed)
  - [3 · Decoding parameters](#3--decoding-parameters)
  - [4 · EMG input](#4--emg-input)
  - [5 · What the dynamic prompt carries](#5--what-the-dynamic-prompt-carries)
  - [6 · Expected serial command](#6--expected-serial-command)
  - [7 · The four prompt blocks](#7--the-four-prompt-blocks)
- [Why the same model answers differently in LM Studio's chat](#why-the-same-model-answers-differently-in-lm-studios-chat)
- [Live mode](#live-mode)
- [Connecting the physical prosthesis](#connecting-the-physical-prosthesis)
- [Testing a command by hand](#testing-a-command-by-hand)
- [The movement log](#the-movement-log)
- [Reading the result](#reading-the-result)
- [The dashboard](#the-dashboard)
- [Prompt configurations](#prompt-configurations)

---

## How one run works

```
EMG window (N × 8 raw)
        │
        ▼
  Prompt assembly ─── block 1 System        ─┐
                      block 2 Technical     ─┤ frozen: identical on every run
                      block 3 EMG knowledge ─┘
                      block 4 Dynamic ──────── variable: the only thing that changes
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
Blocks 1, 2 and 3 are byte-identical across runs, so when two models disagree
the difference is attributable to the model rather than to the prompt. Block 4
is the stimulus.

There are three frozen blocks rather than one because they answer different
kinds of question and get revised on different schedules: how to behave, what
the hand can do, and how to read EMG. Each can be varied while the other two
stay identical — which is the only way an effect can be attributed to one of
them.

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
[EMG input](#4--emg-input).

### 2 · Thinking, and why it must be suppressed

The button beside **Refresh** controls the model's thinking channel. **Filled
navy = suppressed** (the default). **Amber outline = thinking allowed.** Amber is
the state that produces confusing results, so it is the one drawn to catch your
eye.

A reasoning model — anything Qwen3-class — splits its reply in two: the
working-out goes to a `reasoning_content` field, the answer to `content`. On this
task that arrangement fails in a specific way. The model is given a hard
classification and a token ceiling; it spends the ceiling deliberating, and
`content` arrives **empty**. The platform records a parse failure for a model
that was, in a sense, still thinking.

When suppressed, two switches are sent with the request, because two conventions
exist and runtimes disagree about which they read:

| Sent | Convention | Read by |
|---|---|---|
| `chat_template_kwargs: {"enable_thinking": false}` | Qwen3 | The chat template, before the model sees anything |
| `reasoning_effort: "none"` | OpenAI | The runtime's own inference layer |

Either alone leaves a gap. Both together cover both families, and a runtime that
does not recognise one simply ignores it.

The platform also **reads the reasoning channel as a fallback**: if `content` is
blank and `reasoning_content` is not, the answer is taken from there and the
execution records which channel it arrived on. That is a rescue, not a fix — a
run whose answer came off the reasoning channel is telling you the suppression
did not take.

What was actually requested is stored per execution in `reasoning_mode`, so a
result can never be silently reattributed to the wrong condition.

### 3 · Decoding parameters

These control **how the model picks each token**. They are the difference
between a measurement and an anecdote.

| Control | What it does | Why it is set this way |
|---|---|---|
| **Temperature** | Flattens or sharpens the probability distribution before sampling. `0` always takes the most likely token. | **Keep at 0.** This is a control task, not a writing task: there is one right answer and no value in variety. Above 0, repeating a run can give a different command, which makes any single result unrepeatable. The read-out turns amber above 0 as a warning. |
| **Top-P** | Nucleus sampling: consider only the smallest set of tokens whose probabilities sum to P. | At temperature 0 it has no effect — greedy decoding ignores it. Left at `1.00` so it cannot silently interact if you raise the temperature. |
| **Top-K** | Consider only the K most likely tokens. | Disabled unless the runtime declares support. Same reasoning as Top-P. |
| **Max tokens** | Hard ceiling on the reply length. | `1024`. The response is a JSON object with up to six command entries; below about 200 it truncates mid-object. **A truncated reply is indistinguishable from a malformed one in the metrics**, so too small a value records a budget mistake as the model's failure. The ceiling is generous on purpose: it costs nothing when the model is brief, and a value chosen tightly is the first thing that breaks when thinking is left on. |
| **Seed** | Fixes the sampler's random number generator. | `42`. Together with temperature 0, this is what makes a run reproducible. Determinism is a property of the sampler — not something a model can be instructed into — which is why the prompt no longer asks for it. |
| **Freq. penalty** | Penalises tokens already used, by frequency. | `0`. Designed to stop prose repeating itself. A command may legitimately repeat a letter (`A320,B180`), so a penalty here actively distorts the output. |
| **Presence penalty** | Penalises tokens already used, at all. | `0`, same reason. |
| **Response format** | Asks the runtime to constrain decoding. | `json_object`, **upgraded to `json_schema`** for LM Studio, which rejects the plain `json_object` spelling. With a schema attached the runtime **cannot emit** malformed JSON, which removes the largest single failure mode — prose wrapped around the answer — before it happens rather than catching it afterwards. The upgrade is deliberate: downgrading to free text would have silently traded away that guarantee. |

### 4 · EMG input

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

**Four actions, each a quarter of the row:**

- **Paste matrix** — rows pasted directly: CSV, TSV, whitespace or JSON.
- **Import CSV** — your acquisition file. A header row (`CH0…CH7` or `CH1…CH8`)
  is detected and skipped; a UTF-8 BOM is stripped.
- **Copy CSV** — the loaded window back out, for a lab notebook or a second tool.
- **Clear** — discard the window.

The synthetic-window picker used to sit first in this row. It loaded generated
signals with a known answer, which is useful for testing the platform but is not
acquisition — and sitting first it read as the primary way in. **A run against
synthesised EMG is not evidence about a model.** The generator is still available
at `GET /api/v1/emg/synthetic` for anyone checking the pipeline itself.

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

### 5 · What the dynamic prompt carries

Three mutually exclusive options, and a genuine experimental variable — not a
display preference.

| Option | The model receives | The question it answers |
|---|---|---|
| **Matrix** | The raw N × 8 samples, nothing else | *Can an LLM read raw EMG?* The hardest condition, and the one this platform exists to measure. |
| **Features** | Per-channel RMS, MAV, ZC, SSC, WL, min, max and the flexor ratio | *Can an LLM act on extracted features?* A much easier task — the signal processing has been done for it. |
| **Both** | The matrix, then the descriptors | The most information the model can be given. |

The three buttons apply **immediately** — the dynamic block and the token budget
re-render as you press them, so you can see what each condition actually costs
before committing a run to it.

The descriptors are always computed over the **complete** window, even when the
printed matrix is capped: a summary of the excerpt would describe something you
never chose to analyse.

**Features mode is also the escape hatch when a prompt will not fit.** The
descriptor table is a fixed size whatever the recording length — a 4,000-sample
window costs the same as a 32-sample one.

### 6 · Expected serial command

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

### 7 · The four prompt blocks

| Block | Contains | Editable |
|---|---|---|
| **1 · System** | Role and output discipline. No numbers, no EMG. | Yes, versioned |
| **2 · Technical Context** | The hand: actuators and ranges, preset gestures, command syntax, safety envelope. | Yes, versioned |
| **3 · EMG Knowledge** | The electrode map and how to reason about it. | Yes, versioned |
| **4 · Dynamic** | The EMG for this run. | Template only — the content is assembled |

**Block 2 says nothing about Bluetooth.** It used to open its format section with
"Bluetooth protocol / ASCII", which described a link the model has no part in: it
does not open the socket, choose the baud rate, or see the wire. What it needs is
the command *syntax* — uppercase letters, comma-separated — and that is what
remains. The transport lives in `app.domain.protocol` and in the browser's serial
link, where something can actually act on it.

Blocks 1, 2 and 3 are **frozen**: identical bytes on every run. Editing any of
them creates a new immutable version, so past results stay attributable to the
exact wording that produced them.

Block 3 is separate from block 2 on purpose. "What can this hand do?" is a fact
about hardware that changes only when the hardware does; "is co-contraction a
stop, or physiological coactivation?" is a methodological position a researcher
will revise repeatedly. Sharing one artefact would mean every experiment on the
second question also reversioned the first.

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

## Why the same model answers differently in LM Studio's chat

A recurring and reasonable suspicion: paste the prompt into LM Studio's chat and
the model closes the hand; send the identical prompt through this platform and it
returns `no_action`. Same model, same weights, different answer.

There are **four** independent causes, and they compound:

| Cause | In the chat | Through the API |
|---|---|---|
| **Thinking** | You may have turned it off in the chat UI | Must be suppressed explicitly — see [§2](#2--thinking-and-why-it-must-be-suppressed) |
| **Decoding defaults** | temperature 0.8, top-p 0.95, top-k 40 — a *creative* preset | temperature 0, top-p 1, greedy |
| **Conversation history** | Every earlier turn is still in context | Nothing. Each execution is alone |
| **`response_format`** | Not applied | A schema constrains decoding token by token |

None of these is a bug, and none of them is the platform being wrong. The chat is
a *different experimental condition* — a warmer sampler with a conversation
behind it. If you want the chat's answer, the honest move is to reproduce the
chat's conditions here and record that you did.

**Load settings are a separate axis and cannot explain a different answer.**
LM Studio's *load* panel — GPU offload, context length, KV cache — decides how
fast the model runs and how much prompt fits. GPU Offload at 0 will take four
minutes for 765 tokens. That is a latency problem, not an answer problem: the
same weights on CPU and GPU produce the same tokens.

**Context length, though, changes what the model reads.** If the load context is
8192 and your prompt is 17,608 tokens, something has to give — and a silently
truncated matrix is a different stimulus from the one you chose. The prompt-budget
cards exist to catch exactly this before you spend a run on it.

### Timeouts and retries

`LLM_REQUEST_TIMEOUT_S` defaults to **1800** (30 minutes). That is not caution
about the network; it is the observed cost of a large model with no GPU offload,
where a few hundred tokens can take minutes. A timeout tuned for a hosted API
turns a slow local run into a recorded failure.

**Both retry counters are zero** — LiteLLM's `num_retries` and the OpenAI client's
`max_retries`, which defaults to 2 and is easy to miss. A retried experiment is
not the experiment you asked for: it silently spends three times the wall clock
and records one result. If a run fails, that is the finding.

Note that `.env` wins twice over: Docker Compose reads it for `${VAR}`
interpolation *and* passes it into the container. A stale value there beats the
application default in both directions, which is worth remembering when a setting
appears not to take.

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

## Testing a command by hand

The **Actuator state** row in the simulator has a text field and a **Test**
button. Type `C`, press Test, watch the hand close.

This exists to separate two failures that look identical from the outside. When a
run produces no movement, the cause is either **the model's answer** or **the
plumbing** — validator, WebSocket, serial link, firmware. Every diagnostic step
that starts with an inference has the model's judgement in the way; typing a
command settles the question in one action without it.

It is **not** a shortcut around validation. A typed command goes through the same
seven stages a model's answer does. Two definitions of "safe" would drift, and
the guarantee would become whichever one happened to run — and the mechanical
stops do not care who chose the number. A typo in a text field can strip a
gearmotor exactly as well as a bad model can.

Accepted forms are the protocol's own: a bare gesture (`C`, `P`, `S`), or
positions (`A320,B240`). Lower case is accepted and normalised.

One line of feedback distinguishes three outcomes a single "sent" would flatten:

| Feedback | Means |
|---|---|
| A pink message | Rejected by validation, with the validator's own wording — it names the actuator, the value and the profile that refused it |
| `· no client` | Accepted and published, but no simulator was listening |
| `· sim` / `· sim + hand` | Delivered, and to which destinations |

---

## The movement log

`/logs` — every command that moved the hand.

Deliberately **not** the same list as the execution history. That one records what
models *answered*; this one records what was *transmitted*, and the two diverge in
both directions:

- A pose that resolved is not a pose that was delivered. The prosthesis link can
  be closed, or drop mid-session.
- Commands no model produced — manual tests and replays — move the hand exactly
  as a model's answer does, and would otherwise be movements with no record
  explaining them.

**Two destination columns, not one "delivered" flag.** The simulator renders from
the backend; the hardware is driven from the browser. Either can arrive while the
other does not, and that asymmetry is precisely what someone reading this log is
trying to diagnose. Delivery to the prosthesis is confirmed by the browser in a
follow-up call rather than assumed at write time — a log written up front would
claim delivery for a command the link dropped.

Filter by origin, because the three kinds answer different questions:

| Origin | What it is |
|---|---|
| **Model** | A model's answer, after all seven stages. This is evidence. |
| **Manual** | Typed to test the link or the mechanics. Not evidence about a model. |
| **Replay** | A stored movement re-sent. It moved the hand again, so it is logged again. |

The headline counts are over the loaded page and labelled as such. Calling a
page's count a total is how a dashboard starts lying.

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

### `no_action` means the hand does not move

Worth stating separately, because it was a real failure. Models were answering
`{"intent": "no_action", "serial_command": "S"}` — and `S` is STOP, a command that
*does* something.

The cause was in the contract, not the model. `serial_command` was required for
every intent, so a model choosing `no_action` had to put *something* there, and
STOP was the most-mentioned gesture in the prompt. It filled the field the way the
schema told it to.

The fix was on both sides:

- **The schema** makes `serial_command` optional, but only for `no_action`. Any
  other intent still requires it.
- **The pipeline** short-circuits: a declared inaction with an empty command skips
  protocol, range, kinematic and safety — there is nothing to check — records the
  stages as completed, resolves no pose, and passes.
- **Block 3** states it in words: *"no_action means the hand does not move. It is
  never S, and never O."* A model given a rule will follow it; a rule merely
  omitted is not a rule.

`no_action` with a command attached is still an error, and still fails at
`consistency`, with a message that says what to do instead.

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

## Prompt configurations

Every execution points at the **distinct combination of frozen blocks** that
produced it. Deduplicated at write time on
`frozen_context_sha256 = SHA256(system ‖ technical ‖ EMG knowledge)`:

- Three hundred runs under one setup leave **one** configuration row.
- Change one word in one block and the next run files a **second** row.
- Change it back and the **first** row is reused, with its `last_used_at` touched.

A configuration carries the label you see in the interface (`S1.0 · T1.0 · E1.0`),
the three block versions, and the full frozen text as it stood — so a result stays
readable after the blocks have moved on.

The results are broken down **per model**, because a configuration is only
comparable within one. Two models under the same configuration is a comparison;
the same model under two configurations is a comparison. Pooling across both at
once answers neither question.

This is what makes the archive interrogable rather than merely large: *which
wording produced this number* has an answer that does not depend on anyone
remembering.

All four blocks ship at version **1.0** and move only when someone changes the
text deliberately. The numbers previously carried the platform's own development
history — a system prompt at 6.0.0 before a single experiment had been run — which
made the artefact table read as though five earlier studies had happened. That
history belongs in git.

---

<div align="center">

Escuela Politécnica Nacional · Facultad de Ingeniería de Sistemas

</div>
