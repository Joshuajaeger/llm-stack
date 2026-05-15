#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

service="${1:-}"

if [ -n "$service" ]; then
    log_file="logs/$service.log"
    if [ ! -f "$log_file" ]; then
        echo "No log file for service: $service"
        exit 1
    fi
    tail -f "$log_file"
else
    tail -f logs/*.log
fi
