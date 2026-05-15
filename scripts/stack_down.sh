#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d .pids ]; then
    echo "No running stack found."
    exit 0
fi

for pid_file in .pids/*.pid; do
    [ -e "$pid_file" ] || continue
    name="$(basename "$pid_file" .pid)"
    pid="$(cat "$pid_file")"

    if kill -0 "$pid" 2>/dev/null; then
        echo "Stopping $name (pid $pid)..."
        kill "$pid" 2>/dev/null || true
    else
        echo "$name is not running."
    fi

    rm -f "$pid_file"
done

echo "Stack stopped."
