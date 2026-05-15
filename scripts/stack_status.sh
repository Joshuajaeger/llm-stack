#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

check_port() {
    local name="$1"
    local port="$2"
    local pid
    pid=$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n1 || true)
    if [ -n "$pid" ]; then
        echo "$name: running on port $port (pid $pid)"
    else
        echo "$name: stopped"
    fi
}

check_port "mlx"    8001
check_port "router" 8000
check_port "webui"  8080
