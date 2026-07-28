<div align="center">

<img src="frontend/src/assets/logo.jpg" alt="Escuela Politécnica Nacional · Facultad de Ingeniería de Sistemas" width="250" height="96">

# Prosthetic Hand LLM Evaluation Platform

**HANDi EPN V3 · EMG → validated control commands**

[English](docs/en/README.md) · [Español](docs/es/README.md) · [All documentation](docs/README.md)

</div>

---

## English

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

## Español

Plataforma de investigación para evaluar modelos de lenguaje en una tarea
concreta y crítica para la seguridad: **convertir una matriz EMG de superficie de
8 canales en un comando de control validado para la prótesis de mano HANDi EPN
V3.**

No es un chatbot. Sin conversaciones, sin memoria. Cada ejecución es un
experimento independiente: un prompt congelado, una ventana EMG, un modelo, una
respuesta JSON, siete etapas de validación, un registro permanente.

```bash
cp .env.example .env
docker compose up --build
```

Interfaz en http://localhost:4200 · API en http://localhost:8000/docs

| Quiero… | Leer |
|---|---|
| Ejecutar experimentos | [Manual de usuario](docs/es/manual-usuario.md) |
| Instalar el sistema | [Instalación y despliegue](docs/es/instalacion.md) |
| Entender el diseño | [Arquitectura](docs/es/arquitectura.md) |
| Integrar con la API | [Referencia de la API](docs/es/api.md) |
| Consultar el registro | [Base de datos](docs/es/base-de-datos.md) |
| Contribuir código | [Guía del desarrollador](docs/es/guia-desarrollador.md) |
| Conocer el hardware | [Especificación del hardware](docs/es/hardware.md) |

---

## Design in one table · El diseño en una tabla

The claim this platform has to support is *"model A produces more accurate, more
consistent and safer prosthetic commands than model B"*. That is only defensible
if everything except the model is held constant.

La afirmación que esta plataforma debe sostener es *«el modelo A produce comandos
protésicos más exactos, más consistentes y más seguros que el modelo B»*. Eso
solo es defendible si todo lo demás se mantiene constante.

| Mechanism · Mecanismo | Guarantee · Garantía |
|---|---|
| Three-block prompt, first two frozen | Only the EMG payload varies between runs |
| `frozen_context_sha256` per execution | Two runs are provably comparable, or provably not |
| Immutable prompt versions | Any published result reproduces byte for byte |
| Hardware spec compiled into code | No RAG variance, no PDF at runtime |
| Validation before the simulator | An unsafe pose is unrenderable, not merely discouraged |
| Versioned limit profiles | The manual contradicts itself; the platform records which reading applied |
| Append-only audit trail | Every change has an actor, a time and a diff |

---

## Stack

**Backend** — Python 3.13 · FastAPI · SQLAlchemy 2 · PostgreSQL 17 · Alembic ·
LiteLLM · Pydantic v2
**Frontend** — Angular 22 (zoneless, signals) · Angular Material 3 · TailwindCSS
· RxJS · Three.js

## Verification · Verificación

```bash
cd backend && python -m pytest tests -q     # 189 tests
python scripts/check_frontend.py            # static checks, no node_modules
./scripts/check.sh                          # everything
```

---

<div align="center">

Escuela Politécnica Nacional · Facultad de Ingeniería de Sistemas
Laboratorio de Investigación en Inteligencia y Visión Artificial "Alan Turing"

</div>
