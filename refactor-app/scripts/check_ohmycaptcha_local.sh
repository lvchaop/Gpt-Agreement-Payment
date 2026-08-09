#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "${ROOT_DIR}/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.ohmycaptcha"
APP_ENV_FILE="${ROOT_DIR}/.env"

if [ -f "${ENV_FILE}" ]; then
  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a
fi

if [ -f "${APP_ENV_FILE}" ]; then
  # shellcheck disable=SC1090
  set -a
  source "${APP_ENV_FILE}"
  set +a
fi

HOST="${OHMYCAPTCHA_HOST:-127.0.0.1}"
PORT="${OHMYCAPTCHA_PORT:-18000}"
BASE_URL="${OHMYCAPTCHA_BASE_URL:-http://${HOST}:${PORT}}"
CLIENT_KEY_VALUE="${CLIENT_KEY:-${PERSONAL_PLUS_CHECKOUT_CAPTCHA_CLIENT_KEY:-}}"
PYTHON_BIN="${OHMYCAPTCHA_PYTHON_BIN:-${PROJECT_ROOT}/.venv/bin/python}"

if [ -z "${CLIENT_KEY_VALUE}" ]; then
  echo "missing CLIENT_KEY / PERSONAL_PLUS_CHECKOUT_CAPTCHA_CLIENT_KEY" >&2
  exit 1
fi

echo "[1/2] health"
curl -fsS "${BASE_URL}/api/v1/health"
echo
echo

echo "[2/2] sample createTask (hCaptcha)"
create_resp="$(
curl -fsS "${BASE_URL}/createTask" \
  -H 'content-type: application/json' \
  -d "$(cat <<JSON
{
  "clientKey": "${CLIENT_KEY_VALUE}",
  "task": {
    "type": "HCaptchaTaskProxyless",
    "websiteURL": "https://accounts.hcaptcha.com/demo",
    "websiteKey": "10000000-ffff-ffff-ffff-000000000001",
    "isInvisible": false
  }
}
JSON
)"
)"
printf '%s\n' "${create_resp}"
task_id="$("${PYTHON_BIN}" - "${create_resp}" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
print(data.get("taskId", ""))
PY
)"
if [ -n "${task_id}" ]; then
  echo
  echo "[3/3] sample getTaskResult"
  curl -fsS "${BASE_URL}/getTaskResult" \
    -H 'content-type: application/json' \
    -d "$(cat <<JSON
{
  "clientKey": "${CLIENT_KEY_VALUE}",
  "taskId": "${task_id}"
}
JSON
)"
  echo
fi
