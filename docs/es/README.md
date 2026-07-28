# Visión general

**Idiomas:** [Español](README.md) · [English](../en/README.md)

Plataforma de investigación para evaluar modelos de lenguaje en una tarea
concreta y crítica para la seguridad: **convertir una matriz EMG de superficie de
8 canales en un comando de control validado para la prótesis de mano HANDi EPN
V3.**

No es un chatbot. No hay conversaciones, ni memoria, ni preguntas de seguimiento.
Cada ejecución es un experimento independiente: un prompt congelado, una ventana
EMG, un modelo, una respuesta JSON, siete etapas de validación, un registro
permanente.

---

## Por qué el diseño es así

La afirmación que la plataforma debe sostener es *«el modelo A produce comandos
protésicos más exactos, más consistentes y más seguros que el modelo B»*. Eso
solo es defendible si todo lo demás se mantiene constante. La arquitectura lo
impone estructuralmente, no por convención:

| Mecanismo | Garantía |
|---|---|
| Prompt de tres bloques, los dos primeros congelados | Entre ejecuciones solo varía la carga EMG |
| `frozen_context_sha256` en cada ejecución | Dos corridas son comparables de forma demostrable, o demostrablemente no lo son |
| Versiones de prompt inmutables | Cualquier resultado publicado se reproduce byte a byte |
| Especificación del hardware compilada en código | Sin varianza de RAG, sin deriva de recuperación, sin PDF en tiempo de ejecución |
| Validación antes del simulador | Una pose insegura es irrepresentable, no meramente desaconsejada |
| Perfiles de límites mecánicos versionados | El manual se contradice; la plataforma registra qué lectura se aplicó |
| Traza de auditoría solo-anexado | Todo cambio tiene actor, fecha y diff |

---

## La prótesis

Compilada a partir de cuatro manuales técnicos durante el desarrollo. **Los PDF
nunca se leen en tiempo de ejecución**: sin RAG, sin embeddings, sin base
vectorial. Todo vive en `backend/app/domain/`.

**HANDi EPN V3** — Escuela Politécnica Nacional, Laboratorio «Alan Turing», sobre
la plataforma de código abierto HANDi Hand.

- ESP32 (Wemos D1 R32) + 2× Adafruit Motor Shield V3
- 5× motorreductores Pololu 380:1 con encoders de 12 CPR, más un servo MG90S
- 6 grados de libertad comandados, 15 articulaciones modeladas
- 11 potenciómetros rotativos, 5 sensores de fuerza en las yemas
- Bluetooth SPP, dispositivo `Handi EPN V3`

| Cmd | Dedo | Rango (Tabla 5) | Rango (Anexo A) |
|-----|------|-----------------|-----------------|
| `A` | meñique | 0–600 | 0–350 |
| `B` | anular | 0–550 | 0–350 |
| `C` | medio | 0–600 | 0–440 |
| `D` | índice | 0–550 | 0–350 |
| `E` | rotación del pulgar | 0–130 | 0–120 |
| `F` | flexión del pulgar | 0–400 | 0–100 |

Catorce gestos predefinidos: `O C P R W Y L M H U G S X I`.

> **La ambigüedad de `C`.** Una `C` sola cierra la mano; `C400` se dirige al dedo
> medio. Se resuelve por el sufijo numérico, está documentada en el contexto
> técnico y tiene test de regresión.

> **La discrepancia de rangos.** La Tabla 5 y el Anexo A publican máximos
> distintos. En lugar de elegir en silencio, la plataforma incluye tres perfiles
> versionados —`TABLE_5_V3` (por defecto), `ANNEX_A_V3`, `INTERSECTION`— y sella
> cada ejecución con el que se aplicó.

Detalle completo: [especificación del hardware](hardware.md).

---

## El prompt

```
┌────────────────────────┐
│ 1 · SYSTEM PROMPT      │  congelado · contrato de comportamiento
├────────────────────────┤
│ 2 · CONTEXTO TÉCNICO   │  congelado · generado desde el modelo de dominio
├────────────────────────┤
│ 3 · PROMPT DINÁMICO    │  variable · matriz EMG + características derivadas
└────────────────────────┘
            ↓  LiteLLM  ↓
        Respuesta JSON
```

El investigador nunca lo ensambla. `build_prompt()` lo hace antes de cada
inferencia y devuelve los digests SHA-256 de cada bloque.

El bloque 2 **se genera desde `app/domain/`**, no se transcribe, para que los
límites que se le cuentan al modelo no puedan desviarse de los que aplica el
validador.

---

## El estímulo

```
N filas (instantes de tiempo, ascendente) × 8 columnas (CH1…CH8)
amplitudes normalizadas a [-1.0, 1.0]
```

Las características (`rms`, `mav`, `zc`, `ssc`, `wl`, `min`, `max`, `variance`)
**las deriva el backend**, nunca se aportan. Lo que envíe un cliente se descarta
y se recalcula, de modo que no puede existir una ventana cuyo resumen contradiga
su forma de onda.

Una matriz transpuesta se detecta y se nombra explícitamente: es el error con más
probabilidad de corromper un experimento en silencio.

---

## Validación

```
parse → schema → protocol → consistency → range → kinematic → safety
```

Un fallo en cualquier etapa significa que **el simulador no se mueve**, la
ejecución se marca como fallida y cada incidencia se almacena con un código
consultable. La autoevaluación de seguridad del propio modelo es orientativa: el
backend re-deriva cada campo de forma independiente.

---

## Tecnologías

**Backend** — Python 3.13 · FastAPI · SQLAlchemy 2 (async) · PostgreSQL 17 ·
Alembic · LiteLLM · Pydantic v2

**Frontend** — Angular 22 (zoneless, signals) · Angular Material 3 · TailwindCSS
· RxJS · Three.js

---

## Puesta en marcha

```bash
cp .env.example .env
docker compose up --build
```

Interfaz en http://localhost:4200, API en http://localhost:8000/docs.

Instrucciones completas: [instalación y despliegue](instalacion.md).

---

## Por dónde seguir

| Si eres | Lee |
|---|---|
| Quien ejecuta experimentos | [Manual de usuario](manual-usuario.md) |
| Quien instala el sistema | [Instalación](instalacion.md) |
| Quien extiende la plataforma | [Arquitectura](arquitectura.md) · [Guía del desarrollador](guia-desarrollador.md) |
| Quien integra con la API | [Referencia de la API](api.md) |
| Quien consulta el registro | [Base de datos](base-de-datos.md) |
| Quien trabaja en el hardware | [Especificación del hardware](hardware.md) |
