#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

if [ -f .env ]; then
    # shellcheck disable=SC1091
    source .env
fi

if [ -z "${API_KEY:-}" ]; then
    echo "ERROR: API_KEY is not set. Run 'bash install.sh' first or set API_KEY in .env." >&2
    exit 1
fi

if [ -z "${WEBUI_SECRET_KEY:-}" ]; then
    echo "ERROR: WEBUI_SECRET_KEY is not set. Run 'bash install.sh' first or set it in .env." >&2
    exit 1
fi

# Deployment mode controls which interface Open WebUI binds to.
#   local      -> 127.0.0.1 only (default, no remote access)
#   tailscale  -> bind to the Tailscale IP only (remote via your tailnet)
#   lan        -> 0.0.0.0 (anyone on your Wi-Fi/Ethernet)
#   public     -> 0.0.0.0 (use only behind TLS reverse proxy)
DEPLOY_MODE="${DEPLOY_MODE:-local}"

case "$DEPLOY_MODE" in
    local)
        BIND_HOST="127.0.0.1"
        ;;
    tailscale)
        if ! command -v tailscale >/dev/null 2>&1; then
            echo "ERROR: tailscale command not found. Install Tailscale first: https://tailscale.com/download" >&2
            exit 1
        fi
        BIND_HOST="$(tailscale ip -4 | head -n1)"
        if [ -z "$BIND_HOST" ]; then
            echo "ERROR: could not determine Tailscale IP. Run 'tailscale up' first." >&2
            exit 1
        fi
        ;;
    lan)
        BIND_HOST="0.0.0.0"
        ;;
    public)
        BIND_HOST="0.0.0.0"
        echo "WARNING: DEPLOY_MODE=public binds 0.0.0.0 with no TLS. Put Caddy/nginx with HTTPS in front." >&2
        ;;
    *)
        echo "ERROR: unknown DEPLOY_MODE '$DEPLOY_MODE' (expected: local|tailscale|lan|public)" >&2
        exit 1
        ;;
esac

export HOST="${WEBUI_HOST:-$BIND_HOST}"
export PORT="${WEBUI_PORT:-8080}"

# Auth + signup workflow:
# - WEBUI_AUTH=True       : require login.
# - ENABLE_SIGNUP=True    : let strangers create accounts.
# - DEFAULT_USER_ROLE=pending : new users are inactive until you approve them.
# The very first account created becomes admin automatically.
export WEBUI_AUTH="${WEBUI_AUTH:-True}"
export ENABLE_SIGNUP="${ENABLE_SIGNUP:-True}"
export DEFAULT_USER_ROLE="${DEFAULT_USER_ROLE:-pending}"
export WEBUI_SECRET_KEY

# Backend wiring (router stays on loopback, WebUI talks to it locally).
export OPENAI_API_BASE_URLS="${OPENAI_API_BASE_URLS:-http://127.0.0.1:8000/v1}"
export OPENAI_API_KEYS="${OPENAI_API_KEYS:-$API_KEY}"

echo "Starting Open WebUI"
echo "  mode:    $DEPLOY_MODE"
echo "  bind:    http://$HOST:$PORT"
echo "  signup:  $ENABLE_SIGNUP (new users land in role: $DEFAULT_USER_ROLE)"
if [ "$DEPLOY_MODE" = "tailscale" ]; then
    echo "  share:   http://$BIND_HOST:$PORT  (only reachable from your tailnet)"
fi
open-webui serve
