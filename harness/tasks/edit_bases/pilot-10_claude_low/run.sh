#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PY=/opt/venv/bin/python
[ -x "$PY" ] || PY=python3
mkdir -p out
"$PY" src/paint.py
