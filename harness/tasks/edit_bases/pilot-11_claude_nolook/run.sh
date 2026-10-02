#!/bin/sh
set -e
cd "$(dirname "$0")"
PY=/opt/venv/bin/python
[ -x "$PY" ] || PY=python3
"$PY" src/draw.py
