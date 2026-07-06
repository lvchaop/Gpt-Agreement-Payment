#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$APP_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$REPO_DIR/.venv/bin/python}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
WORKER_CONCURRENCY="${WORKER_CONCURRENCY:-50}"
START_WORKER="${START_WORKER:-1}"
KILL_EXISTING="${KILL_EXISTING:-0}"
LOG_DIR="${LOG_DIR:-$APP_DIR/runtime/logs}"

mkdir -p "$LOG_DIR"

port_pids() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
}

ensure_port_free() {
  local name="$1"
  local port="$2"
  local pids
  pids="$(port_pids "$port")"
  if [ -z "$pids" ]; then
    return
  fi
  if [ "$KILL_EXISTING" = "1" ]; then
    echo "kill existing $name on port $port: $pids"
    kill $pids
    sleep 0.5
    return
  fi
  echo "$name port $port is already in use: $pids" >&2
  echo "set KILL_EXISTING=1 to kill existing listeners before start" >&2
  exit 1
}

kill_existing_workers() {
  if [ "$KILL_EXISTING" != "1" ]; then
    return
  fi
  local pids
  pids="$(pgrep -f "refactor_app.cli.main worker run" 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    return
  fi
  echo "kill existing workers: $pids"
  kill $pids 2>/dev/null || true
  sleep 0.5
}

cleanup() {
  if [ "${BACKEND_PID:-}" ]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [ "${WORKER_PID:-}" ]; then kill "$WORKER_PID" 2>/dev/null || true; fi
  if [ "${FRONTEND_PID:-}" ]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

if [ ! -x "$PYTHON_BIN" ]; then
  echo "python not found: $PYTHON_BIN" >&2
  exit 1
fi

ensure_port_free "backend" "$BACKEND_PORT"
ensure_port_free "frontend" "$FRONTEND_PORT"
kill_existing_workers

cd "$APP_DIR"
export PYTHONPATH="$APP_DIR/src"

echo "check db..."
"$PYTHON_BIN" -m refactor_app.cli.main db check

if [ ! -d "$APP_DIR/frontend/node_modules" ]; then
  echo "frontend dependencies missing, running npm install..."
  (cd "$APP_DIR/frontend" && npm install)
fi

echo "start backend: http://$BACKEND_HOST:$BACKEND_PORT"
"$PYTHON_BIN" -m uvicorn refactor_app.main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  --reload \
  >"$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID="$!"

if [ "$START_WORKER" = "1" ]; then
  echo "start worker: concurrency=$WORKER_CONCURRENCY"
  "$PYTHON_BIN" -m refactor_app.cli.main worker run \
    --no-once \
    --concurrency "$WORKER_CONCURRENCY" \
    >"$LOG_DIR/worker.log" 2>&1 &
  WORKER_PID="$!"
fi

echo "start frontend: http://$FRONTEND_HOST:$FRONTEND_PORT/ops/"
(cd "$APP_DIR/frontend" && npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT") \
  >"$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID="$!"

echo "open: http://$FRONTEND_HOST:$FRONTEND_PORT/ops/"
echo "press Ctrl+C to stop all started processes"

wait
