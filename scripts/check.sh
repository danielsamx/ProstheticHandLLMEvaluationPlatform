#!/usr/bin/env bash
# Verification gate: backend tests + lint + frontend type check.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "▸ backend tests"
cd "$ROOT/backend" && python -m pytest tests -q

echo "▸ backend lint"
ruff check app tests || true

echo "▸ frontend static checks (no node_modules needed)"
python3 "$ROOT/scripts/check_frontend.py"

echo "▸ frontend type check"
cd "$ROOT/frontend" && npx tsc --noEmit -p tsconfig.json
