#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

MODEL_ID="${MODEL_ID:-mlx-community/Qwen2.5-1.5B-Instruct}"

echo "Starting MLX server (model: $MODEL_ID)..."
python src/mlx_server/server.py
