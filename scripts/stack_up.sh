#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

mkdir -p .pids logs

if [ -f .env ]; then
    source .env
fi

start_service() {
    local name="$1"
    local command="$2"
    local pid_file=".pids/$name.pid"
    local log_file="logs/$name.log"

    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo "$name already running (pid $(cat "$pid_file"))"
        return
    fi

    echo "Starting $name..."
    nohup bash -lc "$command" > "$log_file" 2>&1 &
    echo $! > "$pid_file"
    echo "$name started (pid $(cat "$pid_file"), log $log_file)"
}

start_service "mlx" "source .venv/bin/activate && bash scripts/start_mlx.sh"
start_service "router" "source .venv/bin/activate && bash scripts/start_router.sh"
start_service "webui" "source .venv/bin/activate && bash scripts/start_webui.sh"

echo ""
echo "Stack is starting. Check status with: make status"
echo "Open WebUI from this Mac: http://127.0.0.1:8080"
echo "Open WebUI from iPhone:   http://$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null):8080"
