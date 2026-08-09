#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "${ROOT_DIR}/.." && pwd)"
VENDOR_DIR="${ROOT_DIR}/.vendor/ohmycaptcha"
ENV_FILE="${ROOT_DIR}/.env.ohmycaptcha"
CLIENT_KEY_DEFAULT="a31b658c0323af809779608a8e2e651f"
PYTHON_BIN_DEFAULT="${PROJECT_ROOT}/.venv/bin/python"

if ! command -v git >/dev/null 2>&1; then
  echo "git not found" >&2
  exit 1
fi

mkdir -p "${ROOT_DIR}/.vendor"

if [ -f "${ENV_FILE}" ]; then
  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a
fi

HOST="${OHMYCAPTCHA_HOST:-127.0.0.1}"
PORT="${OHMYCAPTCHA_PORT:-18000}"
CLIENT_KEY_VALUE="${CLIENT_KEY:-${PERSONAL_PLUS_CHECKOUT_CAPTCHA_CLIENT_KEY:-$CLIENT_KEY_DEFAULT}}"
PYTHON_BIN="${OHMYCAPTCHA_PYTHON_BIN:-$PYTHON_BIN_DEFAULT}"

if [ ! -x "${PYTHON_BIN}" ]; then
  echo "python interpreter not found: ${PYTHON_BIN}" >&2
  exit 1
fi

python_version="$("${PYTHON_BIN}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
python_major="$("${PYTHON_BIN}" -c 'import sys; print(sys.version_info.major)')"
python_minor="$("${PYTHON_BIN}" -c 'import sys; print(sys.version_info.minor)')"
if [ "${python_major}" -lt 3 ] || { [ "${python_major}" -eq 3 ] && [ "${python_minor}" -lt 10 ]; }; then
  echo "python >= 3.10 required, got ${python_version} from ${PYTHON_BIN}" >&2
  exit 1
fi

if [ ! -d "${VENDOR_DIR}/.git" ]; then
  git clone https://github.com/shenhao-stu/ohmycaptcha.git "${VENDOR_DIR}"
fi

cd "${VENDOR_DIR}"

recreate_venv=0
if [ ! -x "${VENDOR_DIR}/.venv/bin/python" ]; then
  recreate_venv=1
else
  venv_major="$("${VENDOR_DIR}/.venv/bin/python" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo 0)"
  venv_minor="$("${VENDOR_DIR}/.venv/bin/python" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo 0)"
  if [ "${venv_major}" -lt 3 ] || { [ "${venv_major}" -eq 3 ] && [ "${venv_minor}" -lt 10 ]; }; then
    recreate_venv=1
  fi
fi

if [ "${recreate_venv}" -eq 1 ]; then
  rm -rf "${VENDOR_DIR}/.venv"
  "${PYTHON_BIN}" -m venv .venv
fi

"${VENDOR_DIR}/.venv/bin/python" -m pip install -U pip
"${VENDOR_DIR}/.venv/bin/python" -m pip install -r requirements.txt
"${VENDOR_DIR}/.venv/bin/python" -m playwright install --with-deps chromium

export CLIENT_KEY="${CLIENT_KEY_VALUE}"
export SERVER_HOST="${HOST}"
export SERVER_PORT="${PORT}"

cat <<EOF
[OhMyCaptcha]
repo=${VENDOR_DIR}
python=${PYTHON_BIN}
python_version=${python_version}
listen=http://${HOST}:${PORT}
client_key=${CLIENT_KEY}
health=http://${HOST}:${PORT}/api/v1/health
env_file=${ENV_FILE}

需要你自己额外提供模型环境变量（按 OhMyCaptcha README）：
- CLOUD_BASE_URL / CLOUD_API_KEY / CLOUD_MODEL
或
- LOCAL_BASE_URL / LOCAL_API_KEY / LOCAL_MODEL

验证命令：
curl http://${HOST}:${PORT}/api/v1/health
EOF

exec "${VENDOR_DIR}/.venv/bin/python" main.py
