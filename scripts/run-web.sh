#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/web"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt
bash "$ROOT/scripts/hermes/install-skill.sh"

echo "Starting AccountingAgent on http://127.0.0.1:8080"
exec uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload
