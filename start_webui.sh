#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

HOST="${WEBUI_HOST:-127.0.0.1}"
PORT="${WEBUI_PORT:-8765}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
FRONTEND_DIR="$ROOT/webui/frontend"
FRONTEND_DIST="$FRONTEND_DIR/dist/index.html"

echo "[webui] project: $ROOT"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[webui] missing Python venv: $PYTHON_BIN"
  echo "[webui] run the dependency install first, then retry."
  exit 1
fi

if command -v lsof >/dev/null 2>&1; then
  EXISTING_PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN || true)"
  if [[ -n "$EXISTING_PID" ]]; then
    echo "[webui] already running on http://$HOST:$PORT/webui"
    echo "[webui] pid: $EXISTING_PID"
    exit 0
  fi
fi

if [[ ! -f "$FRONTEND_DIST" ]]; then
  echo "[webui] frontend dist missing; building..."
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    echo "[webui] frontend dependencies missing; running npm install..."
    (cd "$FRONTEND_DIR" && npm install --no-package-lock)
  fi
  (cd "$FRONTEND_DIR" && npm run build)
fi

export PATH="$ROOT/.venv/bin:$PATH"
export WEBUI_INTERNAL_BASE_URL="http://$HOST:$PORT"

echo "[webui] starting..."
echo "[webui] open: http://$HOST:$PORT/webui"
exec "$PYTHON_BIN" -m webui.server
