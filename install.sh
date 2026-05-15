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
# shellcheck disable=SC1091
source .venv/bin/activate

echo "3. Installing Python dependencies..."
pip install -q -r requirements.txt

MODEL="${MODEL_ID:-$(bash scripts/select_model.sh)}"
echo "Selected model: $MODEL"

echo "4. Downloading MLX model..."
MODEL="$MODEL" python3 -c "
import os
from mlx_lm.utils import _download
_download(os.environ['MODEL'])
print('Model downloaded.')
"

echo "5. Generating .env (API key + WebUI secret + model)..."
if [ -f .env ] && grep -q '^export API_KEY=' .env && grep -q '^export WEBUI_SECRET_KEY=' .env; then
    echo "Existing .env detected, keeping current secrets."
else
    API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    WEBUI_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
    {
        printf 'export MODEL_ID=%q\n' "$MODEL"
        printf 'export API_KEY=%q\n' "$API_KEY"
        printf 'export WEBUI_SECRET_KEY=%q\n' "$WEBUI_SECRET_KEY"
        printf 'export DEPLOY_MODE=%q\n' "${DEPLOY_MODE:-local}"
    } > .env
    chmod 600 .env
    echo "Generated API_KEY and WEBUI_SECRET_KEY in .env (permissions 600)."
fi

echo ""
echo "=== Done! ==="
echo ""
echo "Quick start:"
echo "  cd $DIR && source .venv/bin/activate"
echo "  source .env"
echo "  make up"
echo ""
echo "Your API key is in .env (do not commit this file)."
echo "Or use: make help"
