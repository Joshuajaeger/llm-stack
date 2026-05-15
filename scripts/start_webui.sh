#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

if [ -f .env ]; then
    # shellcheck disable=SC1091
    source .env
fi

if [ -z "${API_KEY:-}" ]; then
    echo "ERROR: API_KEY is not set. Run 'bash install.sh' or set API_KEY manually." >&2
    exit 1
fi

export HOST="${WEBUI_HOST:-0.0.0.0}"
export PORT="${WEBUI_PORT:-8080}"
export OPENAI_API_BASE_URLS="${OPENAI_API_BASE_URLS:-http://127.0.0.1:8000/v1}"
export OPENAI_API_KEYS="${OPENAI_API_KEYS:-$API_KEY}"

echo "Starting Open WebUI on http://$HOST:$PORT ..."
echo "Open from another device on the same Wi-Fi: http://<your-mac-ip>:$PORT"
echo "Set a strong password on first login. Open WebUI is reachable from your local network."
open-webui serve
