#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-Joshuajaeger/llm-stack}"
DIR="${2:-llm-stack}"

echo "=== llm-stack installer ==="
echo ""

# 0. Find a Python compatible with all dependencies.
#    Open WebUI currently supports Python >=3.11,<3.13.
find_python() {
    for cmd in python3.12 python3.11; do
        if command -v "$cmd" >/dev/null 2>&1; then
            command -v "$cmd"
            return 0
        fi
    done
    for path in \
        /opt/homebrew/opt/python@3.12/bin/python3.12 \
        /opt/homebrew/opt/python@3.11/bin/python3.11 \
        /usr/local/opt/python@3.12/bin/python3.12 \
        /usr/local/opt/python@3.11/bin/python3.11
    do
        if [ -x "$path" ]; then
            echo "$path"
            return 0
        fi
    done
    return 1
}

PY="$(find_python || true)"
if [ -z "$PY" ]; then
    cat >&2 <<'EOF'
ERROR: Need Python 3.11 or 3.12 (Open WebUI does not support Python 3.13+ yet).

Install one with Homebrew:

    brew install python@3.12

Then re-run this installer.
EOF
    exit 1
fi
PY_VERSION="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "Using Python: $PY ($PY_VERSION)"

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
# If an existing venv was built with the wrong Python, recreate it.
if [ -d .venv ]; then
    EXISTING_VERSION="$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "")"
    case "$EXISTING_VERSION" in
        3.11|3.12)
            echo "Reusing existing .venv (Python $EXISTING_VERSION)"
            ;;
        *)
            echo "Existing .venv uses Python ${EXISTING_VERSION:-unknown}, recreating with $PY_VERSION..."
            rm -rf .venv
            ;;
    esac
fi
if [ ! -d .venv ]; then
    "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "3. Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

MODEL="${MODEL_ID:-$(bash scripts/select_model.sh)}"
echo "Selected model: $MODEL"

echo "4. Downloading MLX model..."
MODEL="$MODEL" python -c "
import os
from mlx_lm.utils import _download
_download(os.environ['MODEL'])
print('Model downloaded.')
"

echo "5. Generating .env (API key + WebUI secret + model)..."
if [ -f .env ] && grep -q '^export API_KEY=' .env && grep -q '^export WEBUI_SECRET_KEY=' .env; then
    echo "Existing .env detected, keeping current secrets."
else
    API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
    WEBUI_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
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
