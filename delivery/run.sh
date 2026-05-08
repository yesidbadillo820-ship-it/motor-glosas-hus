#!/usr/bin/env bash
# Arranque rápido del Panel de Domicilios
set -e
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
exec uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
