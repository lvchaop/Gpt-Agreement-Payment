#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8080}"
WORKER_CAPACITY="${REFACTOR_APP_WORKER_CAPACITY:-2000}"
RUN_MIGRATIONS="${REFACTOR_APP_RUN_MIGRATIONS:-1}"

cd "$APP_DIR"
export PYTHONPATH="$APP_DIR/src"

if [ "$RUN_MIGRATIONS" = "1" ]; then
  python -m refactor_app.cli.main db migrate
fi

python -m refactor_app.cli.main worker run --no-once --capacity "$WORKER_CAPACITY" &
WORKER_PID="$!"

cleanup() {
  kill "$WORKER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

exec uvicorn refactor_app.main:app --host 0.0.0.0 --port "$PORT"
