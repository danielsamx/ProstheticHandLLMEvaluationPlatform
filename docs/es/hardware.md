# HANDi EPN V3 — especificación del hardware

**Idiomas:** [Español](hardware.md) · [English](../en/hardware.md)

Consolidada durante el desarrollo a partir de cuatro manuales técnicos. **Este
documento es material de referencia para personas. El sistema nunca lo lee: la
copia autoritativa vive en `backend/app/domain/hand_spec.py`.**

Documentos de origen:

| Archivo | Aporta |
|---|---|
| `Manual Handi_EPN_V3_ES.pdf` | Glosario de comandos, rangos de posición, gestos, protocolo Bluetooth, calibración, mapa de sensores |
| `Assembly Manual.pdf` | Nomenclatura de dedos y articulaciones HANDi Hand, nombres de falanges, construcción mecánica |
| `CONEXIONES.PDF` | Esquema eléctrico: canales del multiplexor, acondicionamiento con amplificadores operacionales, pinout de los shields |
| `DIAGRAMA DE BLOQUES.pdf` | Diagrama de bloques: ESP32 ↔ shields ↔ actuadores ↔ sensores |

---

## 1. Nomenclatura

Según el manual de ensamblaje de HANDi Hand:

- **Dedos** — `D1` pulgar, `D2` índice, `D3` medio, `D4` anular, `D5` meñique
- **Articulaciones** — `P` proximal (MCF), `I` intermedia (IFP), `D` distal
  (IFD/IF)
- **`D0`** — rotación del pulgar (oposición carpometacarpiana)
- **`D1A`** — aducción del pulgar, solo en la variante opcional Add.able (no
  modelada)
- **Piezas** — prefijo `PP`/`IP`/`DP`/`MC`, posición `P`/`D`, lateralidad `R`/`L`

## 2. Cadena cinemática

15 articulaciones rotacionales modeladas. 11 llevan potenciómetro, lo que casa
con los 11 sensores rotativos cableados a los canales C5..C15 del multiplexor.

| Articulación | Dedo | Tipo | Accionada por | Flexión máx. | Acoplamiento | Pot. |
|---|---|---|---|---|---|---|
| `D0`   | D1 | rotación | `E` | 60° | 1.00 | sí |
| `D1_P` | D1 | proximal | `F` | 55° | 1.00 | sí |
| `D1_D` | D1 | distal | `F` | 80° | 0.85 | sí |
| `D2_P` | D2 | proximal | `D` | 90° | 1.00 | sí |
| `D2_I` | D2 | intermedia | `D` | 100° | 0.95 | sí |
| `D2_D` | D2 | distal | `D` | 70° | 0.70 | no |
| `D3_P` | D3 | proximal | `C` | 90° | 1.00 | sí |
| `D3_I` | D3 | intermedia | `C` | 100° | 0.95 | sí |
| `D3_D` | D3 | distal | `C` | 70° | 0.70 | no |
| `D4_P` | D4 | proximal | `B` | 90° | 1.00 | sí |
| `D4_I` | D4 | intermedia | `B` | 100° | 0.95 | sí |
| `D4_D` | D4 | distal | `B` | 70° | 0.70 | no |
| `D5_P` | D5 | proximal | `A` | 90° | 1.00 | sí |
| `D5_I` | D5 | intermedia | `A` | 100° | 0.95 | sí |
| `D5_D` | D5 | distal | `A` | 70° | 0.70 | no |

**Acoplamiento.** Cada dedo lo acciona un único motorreductor mediante tendón, de
modo que los ángulos articulares son función fija del recorrido normalizado del
actuador:

```
ángulo(articulación) = flexión_mín + clamp(recorrido × acoplamiento, 0, 1) × (flexión_máx − flexión_mín)
```

Las falanges **no** son direccionables de forma independiente. El system prompt
lo dice explícitamente, porque un modelo que asuma lo contrario emitirá comandos
verosímiles pero inejecutables.

## 3. Mapeo actuador → shield

| Cmd | Dedo | Hardware | Bornera |
|---|---|---|---|
| `A` | D5 meñique | Pololu 380:1 HPCB 6 V + encoder | Shield 1 / M1 |
| `B` | D4 anular | Pololu 380:1 HPCB 6 V + encoder | Shield 2 / M3 |
| `C` | D3 medio | Pololu 380:1 HPCB 6 V + encoder | Shield 2 / M2 |
| `D` | D2 índice | Pololu 380:1 HPCB 6 V + encoder | Shield 1 / M2 |
| `E` | D1 rotación del pulgar | Servo MG90S de engranajes metálicos | Cabecera de servo SV1 |
| `F` | D1 flexión del pulgar | Pololu 380:1 HPCB 6 V + encoder | Shield 2 / M1 |

## 4. Electrónica

- **Microcontrolador** — ESP32 (formato Wemos D1 R32), alimentación 12 V regulada
- **Drivers de motor** — 2× Adafruit Motor Shield V3 (#2448), 6 V desde un
  reductor XL4015
- **Multiplexor** — CD74HC4067 16:1. Líneas de selección `S0→IO33`, `S1→IO15`,
  `S2→A0`, `S3→A1`; señal `SIG→A2`. Potenciómetros en C5..C15
- **Acondicionamiento** — LM324 (cuádruple) + LM358 (doble), 5× 15 kΩ
- **Encoders** — 5 pares magnéticos, 12 CPR, cableados a los pines 2–7 y 10–13
  del shield 2
- **Sensores** — 11 potenciómetros rotativos 3382G-1-103G, 5 FSR RP-5S-ST

## 5. Protocolo de comunicación

- Bluetooth SPP, dispositivo `Handi EPN V3`, 115 200 baudios
- ASCII, solo mayúsculas, tokens separados por comas, terminados en salto de
  línea
- Longitud máxima de línea: 128 caracteres
- Intervalo mínimo entre transmisiones: 50 ms

**Válido**

```
A320,B180,C400,D200      cuatro dedos a posiciones explícitas
E120,F350                rotación y flexión del pulgar
P                        preset de pinza del firmware
S                        parada de emergencia
```

**Inválido**

```
A700                     supera el máximo documentado
P,A320                   gesto predefinido combinado con posiciones
a320                     minúsculas
A320;B180                separador incorrecto
Z100                     la letra de comando no existe
A320,A100                actuador direccionado dos veces
```

## 6. Rangos de posición — la contradicción documentada

| Cmd | Tabla 5 (cuerpo) | Anexo A (glosario) | Intersección |
|---|---|---|---|
| `A` | 0–600 | 0–350 | 0–350 |
| `B` | 0–550 | 0–350 | 0–350 |
| `C` | 0–600 | 0–440 | 0–440 |
| `D` | 0–550 | 0–350 | 0–350 |
| `E` | 0–130 | 0–120 | 0–120 |
| `F` | 0–400 | 0–100 | 0–100 |

Ambas lecturas se incluyen como perfiles versionados. El valor por defecto es
`TABLE_5_V3`, que coincide con las constantes del firmware descritas en el cuerpo
del manual. Cada ejecución guarda el perfil bajo el que corrió, y el bloque de
contexto técnico se regenera por perfil para que al modelo nunca se le muestren
límites que el validador no vaya a aplicar.

## 7. Gestos predefinidos

| Cmd | Nombre | Clase | Descripción |
|---|---|---|---|
| `O` | OPEN | gesture | Todos los dedos abiertos (reposo / neutro) |
| `C` | CLOSE | gesture | Puño completo |
| `P` | PINCH | gesture | Dedo medio y pulgar flexionados hasta encontrarse |
| `R` | SPIDERMAN | gesture | Índice y meñique extendidos |
| `W` | PARTIAL_CLAW | gesture | Índice y anular cerrados |
| `Y` | OK | gesture | Pulgar e índice formando un anillo |
| `L` | THUMBS_UP | gesture | Dedos cerrados, pulgar extendido |
| `M` | CALL_ME | gesture | Pulgar y meñique extendidos |
| `H` | NUMBER_THREE | gesture | Índice, medio y anular extendidos |
| `U` | NUMBER_FOUR | gesture | Cuatro dedos extendidos, pulgar cerrado |
| `G` | POINT | gesture | Índice extendido, pulgar abierto |
| `S` | STOP | emergency | Desenergiza todos los motores |
| `X` | CALIBRATE | system | Fija la pose actual como cero de los encoders |
| `I` | INIT_SHIELDS | system | Reinicializa ambos motor shields |

`S`, `X` e `I` deben transmitirse solos.

## 8. Envolvente de seguridad

| Restricción | Valor |
|---|---|
| Máximo de actuadores simultáneos | 6 |
| Rango de velocidad | 5–100 % (por defecto 60 %) |
| Tasa máxima de encoder al 100 % | 900 cuentas/s |
| Duración del movimiento | 120–5000 ms |
| Intervalo mínimo entre transmisiones | 50 ms |
| Umbral de saturación de FSR | 0.92 |
| Pose al terminar la sesión | OPEN (según *Recomendaciones* del manual) |

**Regla de colisión.** Un pulgar completamente opuesto *y* completamente
flexionado, combinado con un índice o medio completamente flexionado, empuja los
dedos unos contra otros. El validador lo marca como aviso y no como rechazo
duro, porque la gravedad depende de si hay un objeto en el agarre; queda
registrado en cada ejecución para que la frecuencia sea medible por modelo.

## 9. Adquisición EMG

Ocho canales, montaje en anillo transradial:

| Canal | Sitio | Grupo |
|---|---|---|
| CH1 | Flexor superficial de los dedos | volar / flexor |
| CH2 | Flexor radial del carpo | volar / flexor |
| CH3 | Flexor cubital del carpo | volar / flexor |
| CH4 | Palmar largo | volar / flexor |
| CH5 | Extensor común de los dedos | dorsal / extensor |
| CH6 | Extensor radial largo del carpo | dorsal / extensor |
| CH7 | Extensor cubital del carpo | dorsal / extensor |
| CH8 | Braquiorradial | proximal |

La entrada es una **matriz cruda** de N filas (instantes) × 8 columnas
(electrodos), con amplitudes normalizadas a [-1.0, 1.0]. Las características
—`rms`, `mav`, `zc`, `ssc`, `wl`, `min`, `max`, `variance`— las deriva el backend
de la matriz, nunca las aporta el cliente. Ventana típica: 200 filas a 1000 Hz.
