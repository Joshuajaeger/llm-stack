#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

mkdir -p .pids logs

if [ -f .env ]; then
    # shellcheck disable=SC1091
    source .env
fi

start_service() {
    local name="$1"
    local port="$2"
    local command="$3"
    local log_file="logs/$name.log"

    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
        local existing
        existing=$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN | head -n1)
        echo "$name already running on port $port (pid $existing)"
        return
    fi

    nohup bash -lc "$command" > "$log_file" 2>&1 &
    disown
    echo "$port" > ".pids/$name.port"
    echo "$name starting on port $port (log $log_file)"
}

start_service "mlx"    8001 "source .venv/bin/activate && bash scripts/start_mlx.sh"
start_service "router" 8000 "source .venv/bin/activate && bash scripts/start_router.sh"
start_service "webui"  8080 "source .venv/bin/activate && bash scripts/start_webui.sh"

echo ""
echo "Stack is starting. Check status with: make status"
echo "Open WebUI from this Mac: http://127.0.0.1:8080"
