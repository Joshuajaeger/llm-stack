#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

stop_port() {
    local name="$1"
    local port="$2"
    local pids
    pids=$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
    if [ -z "$pids" ]; then
        echo "$name not running"
        return
    fi
    # shellcheck disable=SC2086
    echo "Stopping $name (pids: $pids)..."
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    # Give them a moment, then escalate if still alive.
    sleep 1
    local stragglers
    stragglers=$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "$stragglers" ]; then
        # shellcheck disable=SC2086
        kill -9 $stragglers 2>/dev/null || true
    fi
}

stop_port "mlx"    8001
stop_port "router" 8000
stop_port "webui"  8080

rm -f .pids/*.pid .pids/*.port 2>/dev/null || true

echo "Stack stopped."
