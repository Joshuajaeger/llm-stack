#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-Joshuajaeger/llm-stack}"
DIR="${2:-llm-stack}"
MODEL="${MODEL_ID:-mlx-community/Qwen2.5-1.5B-Instruct}"

echo "=== llm-stack installer ==="
echo ""

# Clone if not already in the repo
if [ ! -f "$DIR/requirements.txt" ]; then
    echo "1. Cloning $REPO..."
    git clone "https://github.com/$REPO.git" "$DIR"
    cd "$DIR"
else
    echo "1. Already in $DIR, skipping clone..."
    cd "$DIR"
fi

# Create venv
echo "2. Creating Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# Install
echo "3. Installing Python dependencies..."
pip install -q -r requirements.txt

# Download model
echo "4. Downloading MLX model ($MODEL)..."
python3 -c "
import mlx_lm
print('Downloading model (may take a while)...')
mlx_lm.load('$MODEL')
print('Model ready.')
"

echo ""
echo "=== Done! ==="
echo ""
echo "Quick start:"
echo "  cd $DIR && source .venv/bin/activate"
echo "  bash scripts/start_mlx.sh    # Layer 1: fast inference"
echo "  bash scripts/start_router.sh # Layer 3: orchestrator"
echo ""
echo "Or use: make help"