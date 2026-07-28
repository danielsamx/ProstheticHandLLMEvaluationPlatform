# Installation and deployment

**Languages:** [English](installation.md) · [Español](../es/instalacion.md)

---

## Requirements

| Component | Version | Notes |
|---|---|---|
| Docker Engine | 24+ | With Compose v2 |
| PostgreSQL | 17 | Provided by Compose |
| Python | 3.13 | Native installation only |
| Node.js | 22 | Native installation only |
| LM Studio | current | Optional but the primary runtime |

Roughly 4 GB RAM for the platform itself. Local models need considerably more —
budget for the model, not for this.

---

## Quick start with Docker

```bash
git clone <repository> TIC-LLM && cd TIC-LLM
cp .env.example .env          # then edit SECRET_KEY and any API keys
docker compose up --build
```

| Service | URL |
|---|---|
| Interface | http://localhost:4200 |
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |

Migrations and the seed run automatically on backend start.

---

## Configuration

`.env` is read by both Compose and the backend. That double role matters and is
the source of the most common misconfiguration — see the warning below.

### Database

```bash
POSTGRES_USER=phlab
POSTGRES_PASSWORD=phlab          # change for anything shared
POSTGRES_DB=prosthetic_lab
DATABASE_URL=postgresql+asyncpg://phlab:phlab@localhost:5432/prosthetic_lab
DATABASE_URL_SYNC=postgresql+psycopg://phlab:phlab@localhost:5432/prosthetic_lab
```

Two URLs because the application runs async (`asyncpg`) and Alembic runs sync
(`psycopg`).

### Application

```bash
APP_ENV=development              # development | staging | production
LOG_LEVEL=INFO
SECRET_KEY=<long random string>  # change before any shared deployment
CORS_ORIGINS=["http://localhost:4200","http://127.0.0.1:4200"]
```

In development the backend additionally accepts loopback and private-network
origins on any port. A browser treats `localhost`, `127.0.0.1` and a LAN address
as three distinct origins, and an exact-match list turns a harmless URL choice
into every request failing with no usable error. Set
`CORS_ALLOW_LOCAL_ORIGINS=false` to disable. In production only the explicit list
applies.

### Local model runtimes

> **Leave these commented out.**
>
> Compose reads `.env` when resolving `${VAR:-default}`, so a value here
> **overrides** the correct default in `docker-compose.yml`. Setting
> `LM_STUDIO_API_BASE=http://localhost:1234/v1` is the classic cause of
> "LM Studio is not reachable": inside the container, `localhost` is the
> container.
>
> The backend also rewrites loopback addresses to `host.docker.internal` when it
> detects it is containerised, so the correct action is simply to leave the
> variable unset.

```bash
# LM_STUDIO_API_BASE=http://localhost:1234/v1
# OLLAMA_API_BASE=http://localhost:11434
```

| Backend runs | Correct address |
|---|---|
| Natively | `http://localhost:1234/v1` |
| In Docker | `http://host.docker.internal:1234/v1` |

`host.docker.internal` is provided by Docker Desktop; `docker-compose.yml` adds
the `host-gateway` mapping so the same name works on native Linux.

### Hosted providers

```bash
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
```

Only set the ones you use. LiteLLM reads them from the environment.

---

## Setting up LM Studio

1. Install LM Studio and download a model. Good starting points for this task:
   Qwen2.5 7B Instruct, Llama 3.1 8B Instruct, Mistral 7B Instruct.
2. **Developer → Start Server**, port 1234.
3. Confirm the log lists the OpenAI-compatible endpoints, in particular
   `GET http://localhost:1234/v1/models`.
4. In the interface, the **LM Studio** chip turns amber.
5. Press **Import loaded models**.

`litellm.drop_params` is enabled, so a runtime that ignores `top_k` or `seed`
degrades to "not applied" rather than erroring — and the ignored parameter is
recorded on the execution as `dropped_parameters`, because otherwise a run looks
reproducible when it is not.

---

## Native installation

### Backend

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

docker compose up -d db            # or point at your own PostgreSQL
alembic upgrade head
python -m app.seeds.seed

uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm start
```

Angular 22 requires TypeScript 6.0.x. If `npm install` reports a peer dependency
conflict on `typescript`, check that `package.json` pins `~6.0.0`.

---

## Verification

```bash
# Backend: 189 tests, no database required
cd backend && python -m pytest tests -q

# Frontend static checks: no node_modules required
python scripts/check_frontend.py

# Everything
./scripts/check.sh
```

`scripts/check_frontend.py` catches two build-time failures that unit tests
cannot: a stray backtick closing a component template early (Angular NG1002), and
an unresolvable path-alias import.

---

## Production deployment

### Before exposing it

1. **`SECRET_KEY`** — long and random.
2. **`APP_ENV=production`** — disables the permissive local CORS regex.
3. **`CORS_ORIGINS`** — the exact origins, nothing more.
4. **Database password** — not the default.
5. **TLS** — terminate at a reverse proxy.
6. **Backups** — see below.

### Reverse proxy

```nginx
server {
    listen 443 ssl http2;
    server_name lab.example.edu;

    location / {
        proxy_pass http://localhost:4200;
    }

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
```

`X-Forwarded-For` is honoured for provenance only — it is spoofable and is never
used for authorisation.

The long WebSocket timeout matters: a live acquisition session can stay open for
hours.

### Frontend build

```bash
cd frontend && npm run build      # -> dist/prosthetic-lab
```

The production configuration swaps in `environment.prod.ts`, which resolves the
API relative to the serving origin — so a reverse proxy needs no extra
configuration.

---

## Backups

The database *is* the scientific record. Losing it loses every experiment.

```bash
# Dump
docker compose exec -T db pg_dump -U phlab prosthetic_lab | gzip > backup-$(date +%F).sql.gz

# Restore
gunzip -c backup-2026-07-28.sql.gz | docker compose exec -T db psql -U phlab prosthetic_lab
```

`executions.raw_response` and `emg_windows.samples` dominate the size. If pruning
becomes necessary, drop those columns and keep the rows: metrics, digests and
audit entries are small and are what the analysis actually reads.

---

## Upgrading

```bash
git pull
docker compose down
docker compose up --build         # migrations run on start
```

`docker compose restart` is not enough when `.env`, `docker-compose.yml` or
`angular.json` changed — those are read at container creation and at build time,
not at process restart. Use `up -d --force-recreate` for environment changes.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| "LM Studio is not reachable" | `LM_STUDIO_API_BASE` set to `localhost` in `.env` | Comment it out; `up -d --force-recreate backend` |
| Every request fails, no message | CORS: the UI was opened on a different origin | Use `localhost:4200`, or check `CORS_ORIGINS` |
| Model catalogue empty | Backend restarted after the page loaded | Reload; then **Import loaded models** |
| Backend restart loop on seed | A generated prompt drifted without a version bump | Fixed in `0003`; the seed now files drift under a content-addressed version |
| `port is already allocated` | 4200, 8000 or 5432 in use | Stop the other process or remap in `docker-compose.yml` |
| Migration fails on `0002` | Expected: it deletes pre-matrix EMG windows | A feature vector cannot be back-filled into a waveform without fabricating data |
