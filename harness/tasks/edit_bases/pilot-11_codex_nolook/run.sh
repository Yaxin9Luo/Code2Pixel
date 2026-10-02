#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x /opt/venv/bin/python ]]; then
    PYTHON_BIN=/opt/venv/bin/python
else
    PYTHON_BIN=python3
fi
mkdir -p "$TASK_ROOT/out"
exec "$PYTHON_BIN" "$TASK_ROOT/src/draw.py"
