#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$APP_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$REPO_DIR/.venv/bin/python}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
WORKER_CAPACITY="${WORKER_CAPACITY:-2000}"
WORKER_MAX_OPEN_FILES="${WORKER_MAX_OPEN_FILES:-4096}"
WORKER_LAUNCHD_LABEL="${WORKER_LAUNCHD_LABEL:-com.gpt-agreement-payment.refactor-worker}"
WORKER_LAUNCHD_SERVICE="gui/$(id -u)/$WORKER_LAUNCHD_LABEL"
DEV_LAUNCHD_LABEL="${DEV_LAUNCHD_LABEL:-com.gpt-agreement-payment.refactor-dev}"
DEV_LAUNCHD_SERVICE="gui/$(id -u)/$DEV_LAUNCHD_LABEL"
LOG_DIR="${LOG_DIR:-$APP_DIR/runtime/logs}"
START_PID_FILE="$APP_DIR/runtime/start-dev.pid"
START_LOG="$LOG_DIR/restart-dev.log"
WORKER_LOG="$LOG_DIR/worker.log"

mkdir -p "$LOG_DIR" "$APP_DIR/runtime"

resolve_trojan_executable() {
  local configured="${CLIPROXY_TROJAN_EXECUTABLE:-sing-box}"
  local candidate

  if [[ "$configured" == */* ]] && [ -x "$configured" ]; then
    printf '%s\n' "$configured"
    return
  fi

  if [[ "$configured" != */* ]]; then
    candidate="$(command -v "$configured" 2>/dev/null || true)"
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return
    fi
  fi

  for candidate in /opt/homebrew/bin/sing-box /usr/local/bin/sing-box; do
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return
    fi
  done

  echo "Trojan bridge executable not found: $configured" >&2
  return 1
}

CLIPROXY_TROJAN_EXECUTABLE="$(resolve_trojan_executable)"
LAUNCHD_PATH="$(dirname "$CLIPROXY_TROJAN_EXECUTABLE"):${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}"

process_cwd() {
  local pid="$1"
  lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | awk '/^n/ { sub(/^n/, ""); print; exit }'
}

project_pids_for_pattern() {
  local pattern="$1"
  local pid
  for pid in $(pgrep -f "$pattern" 2>/dev/null || true); do
    if [ "$(process_cwd "$pid")" = "$APP_DIR" ]; then
      echo "$pid"
    fi
  done
}

port_pids() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
}

terminate_pids() {
  local label="$1"
  local pids="$2"
  local pid
  local alive
  if [ -z "$pids" ]; then
    return
  fi

  echo "stop $label: $(echo "$pids" | tr '\n' ' ')"
  kill $pids 2>/dev/null || true
  for _ in $(seq 1 20); do
    alive=""
    for pid in $pids; do
      if kill -0 "$pid" 2>/dev/null; then
        alive="$alive $pid"
      fi
    done
    if [ -z "$alive" ]; then
      return
    fi
    sleep 0.1
  done

  echo "force stop $label:$alive"
  kill -KILL $alive 2>/dev/null || true
}

launchd_pid() {
  local service="$1"
  launchctl print "$service" 2>/dev/null \
    | awk '/^[[:space:]]*pid = [0-9]+/ { print $3; exit }'
}

wait_for_launchd_gone() {
  local service="$1"
  local label="$2"
  for _ in $(seq 1 60); do
    if ! launchctl print "$service" >/dev/null 2>&1; then
      return
    fi
    sleep 0.1
  done
  echo "$label did not stop completely: $service" >&2
  return 1
}

wait_for_url() {
  local label="$1"
  local url="$2"
  for _ in $(seq 1 60); do
    if curl -fsS -o /dev/null "$url" 2>/dev/null; then
      return
    fi
    sleep 0.25
  done
  echo "$label did not become ready: $url" >&2
  return 1
}

echo "restart refactor-app..."
echo "trojan bridge executable: $CLIPROXY_TROJAN_EXECUTABLE"

if ! launchctl print "gui/$(id -u)" >/dev/null 2>&1; then
  echo "current user launchd domain is unavailable: gui/$(id -u)" >&2
  exit 1
fi

if launchctl print "$DEV_LAUNCHD_SERVICE" >/dev/null 2>&1; then
  echo "stop launchd dev service: $DEV_LAUNCHD_LABEL"
  launchctl bootout "$DEV_LAUNCHD_SERVICE"
  wait_for_launchd_gone "$DEV_LAUNCHD_SERVICE" "$DEV_LAUNCHD_LABEL"
fi

old_start_pids="$(project_pids_for_pattern "scripts/start-dev.sh")"
terminate_pids "start-dev" "$old_start_pids"
terminate_pids "backend port $BACKEND_PORT" "$(port_pids "$BACKEND_PORT")"

if launchctl print "$WORKER_LAUNCHD_SERVICE" >/dev/null 2>&1; then
  echo "stop launchd worker: $WORKER_LAUNCHD_LABEL"
  launchctl bootout "$WORKER_LAUNCHD_SERVICE"
  wait_for_launchd_gone "$WORKER_LAUNCHD_SERVICE" "$WORKER_LAUNCHD_LABEL"
fi
terminate_pids \
  "workers" \
  "$(project_pids_for_pattern "refactor_app.cli.main worker run")"

echo "start launchd worker: $WORKER_LAUNCHD_LABEL capacity=$WORKER_CAPACITY max_open_files=$WORKER_MAX_OPEN_FILES"
launchctl submit \
  -l "$WORKER_LAUNCHD_LABEL" \
  -o "$WORKER_LOG" \
  -e "$WORKER_LOG" \
  -- \
  /bin/zsh \
  -lc \
  "cd '$APP_DIR' && ulimit -n '$WORKER_MAX_OPEN_FILES' && echo \"worker max open files: \$(ulimit -n)\" && exec env PATH='$LAUNCHD_PATH' CLIPROXY_TROJAN_EXECUTABLE='$CLIPROXY_TROJAN_EXECUTABLE' PYTHONPATH=\"\$PWD/src\" '$PYTHON_BIN' -m refactor_app.cli.main worker run --no-once --capacity '$WORKER_CAPACITY'"

echo "start backend via launchd (START_WORKER=0)"
launchctl submit \
  -l "$DEV_LAUNCHD_LABEL" \
  -o "$START_LOG" \
  -e "$START_LOG" \
  -- \
  /usr/bin/env \
  PATH="$LAUNCHD_PATH" \
  CLIPROXY_TROJAN_EXECUTABLE="$CLIPROXY_TROJAN_EXECUTABLE" \
  BACKEND_HOST="$BACKEND_HOST" \
  BACKEND_PORT="$BACKEND_PORT" \
  START_FRONTEND=0 \
  WORKER_CAPACITY="$WORKER_CAPACITY" \
  START_WORKER=0 \
  KILL_EXISTING=0 \
  "$APP_DIR/scripts/start-dev.sh"

start_pid=""
for _ in $(seq 1 60); do
  start_pid="$(launchd_pid "$DEV_LAUNCHD_SERVICE" || true)"
  if [ -n "$start_pid" ]; then
    break
  fi
  sleep 0.25
done
if [ -z "$start_pid" ]; then
  echo "launchd dev service did not start: $DEV_LAUNCHD_LABEL" >&2
  exit 1
fi
printf '%s\n' "$start_pid" >"$START_PID_FILE"

wait_for_url "backend" "http://$BACKEND_HOST:$BACKEND_PORT/health"
wait_for_url "ops" "http://$BACKEND_HOST:$BACKEND_PORT/ops/"

worker_pids=""
for _ in $(seq 1 60); do
  worker_pids="$(project_pids_for_pattern "refactor_app.cli.main worker run")"
  if [ "$(echo "$worker_pids" | awk 'NF { count++ } END { print count + 0 }')" -eq 1 ]; then
    break
  fi
  sleep 0.25
done

worker_count="$(echo "$worker_pids" | awk 'NF { count++ } END { print count + 0 }')"
if [ "$worker_count" -ne 1 ]; then
  echo "expected exactly one worker, found $worker_count: $worker_pids" >&2
  exit 1
fi

echo "restart complete"
echo "backend: http://$BACKEND_HOST:$BACKEND_PORT"
echo "ops: http://$BACKEND_HOST:$BACKEND_PORT/ops/"
echo "worker: $worker_pids"
echo "start-dev: $start_pid ($DEV_LAUNCHD_LABEL)"
echo "log: $START_LOG"
