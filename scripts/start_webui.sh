#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

if [ -f .env ]; then
    source .env
fi

export HOST="${WEBUI_HOST:-0.0.0.0}"
export PORT="${WEBUI_PORT:-8080}"
export OPENAI_API_BASE_URLS="${OPENAI_API_BASE_URLS:-http://127.0.0.1:8000/v1}"
export OPENAI_API_KEYS="${OPENAI_API_KEYS:-${API_KEY:-secret123}}"

echo "Starting Open WebUI on http://$HOST:$PORT ..."
echo "Open from another device on the same Wi-Fi: http://<your-mac-ip>:$PORT"
open-webui serve
