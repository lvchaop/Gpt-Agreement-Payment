#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE_BIN="${NODE_BIN:-node}"

cd "$ROOT"
export NODE_PATH="${NODE_PATH:-}:$ROOT/webui/frontend/node_modules:/usr/local/lib/node_modules"
exec "$NODE_BIN" "$ROOT/CTF-pay/scripts/open_paypal_chromium.js" "$@"
