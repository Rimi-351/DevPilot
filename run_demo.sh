#!/usr/bin/env bash
# ==============================================================================
# DevPilot One-Click Local Fallback Demo Runner (Linux / macOS)
# ==============================================================================
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "[DevPilot] Starting Local Fallback Demo Setup..."

if [ -f ".venv/bin/python" ]; then
    PYTHON_EXE=".venv/bin/python"
elif [ -f "venv/bin/python" ]; then
    PYTHON_EXE="venv/bin/python"
else
    PYTHON_EXE="python3"
fi

exec "$PYTHON_EXE" scripts/run_local_demo.py "$@"
