#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d .pids ]; then
    echo "No services have been started."
    exit 0
fi

for service in mlx router webui; do
    pid_file=".pids/$service.pid"
    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo "$service: running (pid $(cat "$pid_file"))"
    else
        echo "$service: stopped"
    fi
done
