#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -x /opt/venv/bin/python ]]; then
  exec /opt/venv/bin/python src/paint.py
else
  exec python3 src/paint.py
fi
