#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[fingerprint-browser] missing Python venv: $PYTHON_BIN" >&2
  exit 1
fi

exec "$PYTHON_BIN" "$ROOT/scripts/open_fingerprint_browser.py" "$@"
