#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "Starting router..."
HOST="${HOST:-127.0.0.1}" PORT="${PORT:-8000}" python -m src.router.main
