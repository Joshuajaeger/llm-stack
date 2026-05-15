#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

export MODEL_ID="${MODEL_ID:-$(bash scripts/select_model.sh)}"

echo "Starting MLX server (model: $MODEL_ID)..."
python -m src.mlx_server.server
