#!/usr/bin/env bash
# Aethelburg — quick launcher (Linux / macOS): starts the local server and opens the browser.
# Usage: ./start.sh [--port 8050]
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=".venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "No .venv found: create one first with" >&2
    echo "  python3 -m venv .venv && .venv/bin/python -m pip install -e ." >&2
    exit 1
fi

PORT=8050
prev=""
for arg in "$@"; do
    [ "$prev" = "--port" ] && PORT="$arg"
    prev="$arg"
done

echo "Starting Aethelburg on http://127.0.0.1:${PORT} ..."
echo "First time? Open the '6. Data & Updates' tab to download and import the data."
exec "$PYTHON" -m src.main desktop "$@"
