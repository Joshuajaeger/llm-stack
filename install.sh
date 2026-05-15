#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-Joshuajaeger/llm-stack}"
DIR="${2:-llm-stack}"

echo "=== llm-stack installer ==="
echo ""

if [ -f "requirements.txt" ] && [ -d "src" ]; then
    echo "1. Using current repository..."
elif [ ! -f "$DIR/requirements.txt" ]; then
    echo "1. Cloning $REPO..."
    git clone "https://github.com/$REPO.git" "$DIR"
    cd "$DIR"
else
    echo "1. Already in $DIR, skipping clone..."
    cd "$DIR"
fi

echo "2. Creating Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "3. Installing Python dependencies..."
pip install -q -r requirements.txt

MODEL="${MODEL_ID:-$(bash scripts/select_model.sh)}"
echo "Selected model: $MODEL"

echo "4. Downloading MLX model ($MODEL)..."
python3 -c "
from mlx_lm.utils import _download
_download('$MODEL')
print('Model downloaded.')
"

echo "5. Saving model choice..."
echo "export MODEL_ID=$MODEL" > .env

echo ""
echo "=== Done! ==="
echo ""
echo "Quick start:"
echo "  cd $DIR && source .venv/bin/activate"
echo "  source .env"
echo "  make up"
echo ""
echo "Or use: make help"
