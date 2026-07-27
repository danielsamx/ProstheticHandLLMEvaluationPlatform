#!/usr/bin/env bash
# Local development launcher: Postgres in Docker, backend and frontend native.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "▸ starting PostgreSQL"
docker compose up -d db
until docker compose exec -T db pg_isready -U "${POSTGRES_USER:-phlab}" >/dev/null 2>&1; do
  sleep 1
done

echo "▸ migrating and seeding"
cd "$ROOT/backend"
alembic upgrade head
python -m app.seeds.seed

echo "▸ backend on :8000"
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

echo "▸ frontend on :4200"
cd "$ROOT/frontend"
npm start &
FRONTEND_PID=$!

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT
wait
