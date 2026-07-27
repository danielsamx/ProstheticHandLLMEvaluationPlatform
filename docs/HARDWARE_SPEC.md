# HANDi EPN V3 — hardware specification

Consolidated during development from four technical manuals. **This document is
reference material for humans. The runtime never reads it — the authoritative
copy lives in `backend/app/domain/hand_spec.py`.**

Source documents:

| File | Contributes |
|---|---|
| `Manual Handi_EPN_V3_ES.pdf` | Command glossary, position ranges, gestures, Bluetooth protocol, calibration, sensor map |
| `Assembly Manual.pdf` | HANDi Hand digit/joint naming, phalanx nomenclature, mechanical construction |
| `CONEXIONES.PDF` | Electrical schematic: multiplexer channels, op-amp conditioning, shield pinout |
| `DIAGRAMA DE BLOQUES.pdf` | System block diagram: ESP32 ↔ shields ↔ actuators ↔ sensors |

---

## 1. Naming

Per the HANDi assembly manual:

- **Digits** — `D1` thumb, `D2` index, `D3` middle, `D4` ring, `D5` pinky
- **Joints** — `P` proximal (MCP), `I` intermediate (PIP), `D` distal (DIP/IP)
- **`D0`** — thumb rotation (carpometacarpal opposition)
- **`D1A`** — thumb adduction, only on the optional Add.able thumb (not modelled)
- **Parts** — `PP`/`IP`/`DP`/`MC` prefix, `P`/`D` position, `R`/`L` handedness

## 2. Kinematic chain

15 modelled rotational joints. 11 carry a potentiometer, matching the 11 rotary
sensors wired to multiplexer channels C5..C15.

| Joint | Digit | Type | Driven by | Max flexion | Coupling | Pot |
|---|---|---|---|---|---|---|
| `D0`   | D1 | rotation | `E` | 60° | 1.00 | yes |
| `D1_P` | D1 | proximal | `F` | 55° | 1.00 | yes |
| `D1_D` | D1 | distal | `F` | 80° | 0.85 | yes |
| `D2_P` | D2 | proximal | `D` | 90° | 1.00 | yes |
| `D2_I` | D2 | intermediate | `D` | 100° | 0.95 | yes |
| `D2_D` | D2 | distal | `D` | 70° | 0.70 | no |
| `D3_P` | D3 | proximal | `C` | 90° | 1.00 | yes |
| `D3_I` | D3 | intermediate | `C` | 100° | 0.95 | yes |
| `D3_D` | D3 | distal | `C` | 70° | 0.70 | no |
| `D4_P` | D4 | proximal | `B` | 90° | 1.00 | yes |
| `D4_I` | D4 | intermediate | `B` | 100° | 0.95 | yes |
| `D4_D` | D4 | distal | `B` | 70° | 0.70 | no |
| `D5_P` | D5 | proximal | `A` | 90° | 1.00 | yes |
| `D5_I` | D5 | intermediate | `A` | 100° | 0.95 | yes |
| `D5_D` | D5 | distal | `A` | 70° | 0.70 | no |

**Coupling.** Each finger is tendon-driven by a single gearmotor, so joint
angles are a fixed function of the actuator's normalised travel:

```
angle(joint) = min_flexion + clamp(travel × coupling, 0, 1) × (max_flexion − min_flexion)
```

Individual phalanges are **not** independently addressable. The system prompt
states this explicitly, because a model that assumes otherwise will emit
plausible-looking but unexecutable commands.

## 3. Actuator → shield mapping

| Cmd | Digit | Hardware | Terminal |
|---|---|---|---|
| `A` | D5 pinky | Pololu 380:1 HPCB 6 V + encoder | Shield 1 / M1 |
| `B` | D4 ring | Pololu 380:1 HPCB 6 V + encoder | Shield 2 / M3 |
| `C` | D3 middle | Pololu 380:1 HPCB 6 V + encoder | Shield 2 / M2 |
| `D` | D2 index | Pololu 380:1 HPCB 6 V + encoder | Shield 1 / M2 |
| `E` | D1 thumb rotation | MG90S metal-gear servo | Servo header SV1 |
| `F` | D1 thumb flexion | Pololu 380:1 HPCB 6 V + encoder | Shield 2 / M1 |

## 4. Electronics

- **MCU** — ESP32 (Wemos D1 R32 form factor), 12 V regulated supply
- **Motor drivers** — 2× Adafruit Motor Shield V3 (#2448), 6 V from an XL4015 buck
- **Multiplexer** — CD74HC4067 16:1. Select lines `S0→IO33`, `S1→IO15`,
  `S2→A0`, `S3→A1`; signal `SIG→A2`. Potentiometers on C5..C15
- **Conditioning** — LM324 (quad op-amp) + LM358 (dual op-amp), 5× 15 kΩ
- **Encoders** — 5× magnetic pairs, 12 CPR, wired to shield 2 pins 2–7 and 10–13
- **Sensors** — 11× 3382G-1-103G rotary potentiometers, 5× RP-5S-ST FSRs

## 5. Communication protocol

- Bluetooth SPP, device name `Handi EPN V3`, 115 200 baud
- ASCII, uppercase only, comma-separated tokens, newline terminated
- Maximum line length 128 characters
- Minimum interval between transmissions 50 ms

**Valid**

```
A320,B180,C400,D200      four fingers to explicit positions
E120,F350                thumb rotation and flexion
P                        firmware pinch preset
S                        emergency stop
```

**Invalid**

```
A700                     exceeds the documented maximum
P,A320                   preset gesture combined with positions
a320                     lowercase
A320;B180                wrong separator
Z100                     command letter does not exist
A320,A100                actuator addressed twice
```

## 6. Position ranges — the documented contradiction

| Cmd | Tabla 5 (body) | Anexo A (glossary) | Intersection |
|---|---|---|---|
| `A` | 0–600 | 0–350 | 0–350 |
| `B` | 0–550 | 0–350 | 0–350 |
| `C` | 0–600 | 0–440 | 0–440 |
| `D` | 0–550 | 0–350 | 0–350 |
| `E` | 0–130 | 0–120 | 0–120 |
| `F` | 0–400 | 0–100 | 0–100 |

Both readings are shipped as versioned profiles. The default is `TABLE_5_V3`,
which matches the firmware constants described in the manual body. Every
execution stores the profile it ran under, and the technical context block is
regenerated per profile so the model is never shown limits the validator will
not enforce.

## 7. Preset gestures

| Cmd | Name | Class | Description |
|---|---|---|---|
| `O` | OPEN | gesture | All fingers open (rest / neutral) |
| `C` | CLOSE | gesture | Full fist |
| `P` | PINCH | gesture | Middle finger and thumb flexed to meet |
| `R` | SPIDERMAN | gesture | Index and pinky extended |
| `W` | PARTIAL_CLAW | gesture | Index and ring closed |
| `Y` | OK | gesture | Thumb and index form a ring |
| `L` | THUMBS_UP | gesture | Fingers closed, thumb extended |
| `M` | CALL_ME | gesture | Thumb and pinky extended |
| `H` | NUMBER_THREE | gesture | Index, middle, ring extended |
| `U` | NUMBER_FOUR | gesture | Four fingers extended, thumb closed |
| `G` | POINT | gesture | Index extended, thumb open |
| `S` | STOP | emergency | De-energises all motors |
| `X` | CALIBRATE | system | Latches the current pose as encoder zero |
| `I` | INIT_SHIELDS | system | Re-initialises both motor shields |

`S`, `X` and `I` must be transmitted alone.

## 8. Safety envelope

| Constraint | Value |
|---|---|
| Max simultaneous actuators | 6 |
| Speed range | 5–100 % (default 60 %) |
| Max encoder rate at 100 % duty | 900 counts/s |
| Movement duration | 120–5000 ms |
| Min transmission interval | 50 ms |
| FSR saturation threshold | 0.92 |
| Session end pose | OPEN (per the manual's *Recomendaciones*) |

**Collision rule** — a fully opposed *and* fully flexed thumb combined with a
fully flexed index or middle finger drives the digits into each other. The
validator raises this as a warning rather than a hard rejection, because the
severity depends on whether an object is in the grasp; it is recorded on every
execution so the frequency is measurable per model.

## 9. EMG acquisition

Eight channels, transradial ring montage:

| Channel | Site | Group |
|---|---|---|
| CH1 | Flexor digitorum superficialis | volar / flexor |
| CH2 | Flexor carpi radialis | volar / flexor |
| CH3 | Flexor carpi ulnaris | volar / flexor |
| CH4 | Palmaris longus | volar / flexor |
| CH5 | Extensor digitorum communis | dorsal / extensor |
| CH6 | Extensor carpi radialis longus | dorsal / extensor |
| CH7 | Extensor carpi ulnaris | dorsal / extensor |
| CH8 | Brachioradialis | proximal |

Features per channel: `rms`, `mav`, `zc`, `ssc`, `wl`. Default window 200 ms at
1000 Hz. Amplitudes are normalised 0.0–1.0 against maximum voluntary
contraction, so a window is comparable across subjects and sessions.
