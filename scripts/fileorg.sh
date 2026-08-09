#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# The classifier authenticates to the router with API_KEY from .env.
if [ -f .env ]; then
    # shellcheck disable=SC1091
    source .env
fi

if [ -d .venv ] && [ -z "${VIRTUAL_ENV:-}" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

exec python -m src.fileorg.cli "$@"
