#!/bin/bash
# Double-click to open the drama ads page in your browser. Keep this window open while you use it.
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
python -m drama
