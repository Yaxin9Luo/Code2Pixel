#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -x /opt/venv/bin/python ]]; then
  /opt/venv/bin/python src/draw.py
else
  python3 src/draw.py
fi
