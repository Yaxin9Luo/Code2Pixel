#!/bin/sh
set -e
cd "$(dirname "$0")"
mkdir -p out
PY=/opt/venv/bin/python; [ -x "$PY" ] || PY=python3
"$PY" src/draw.py
