#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/backend"
export CYBERVISUAL_HOST="${CYBERVISUAL_HOST:-0.0.0.0}"
export CYBERVISUAL_PORT="${CYBERVISUAL_PORT:-8000}"
export CYBERVISUAL_CONFIG="${CYBERVISUAL_CONFIG:-$ROOT_DIR/backend/config.example.json}"
export CYBERVISUAL_FRONTEND_DIST="${CYBERVISUAL_FRONTEND_DIST:-$ROOT_DIR/frontend/dist}"

if [ -z "${PYTHON:-}" ]; then
  if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON="$ROOT_DIR/.venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

exec "$PYTHON" -m cybervisual.app
