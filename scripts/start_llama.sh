#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

MODEL="${LLAMA_MODEL:-models/model.gguf}"
PORT=8002

echo "Starting llama.cpp server (model: $MODEL, port: $PORT)..."
llama-server \
  -m "$MODEL" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --grammar-file "$SCRIPT_DIR/grammar/json.gbnf" \
  -ngl 99
