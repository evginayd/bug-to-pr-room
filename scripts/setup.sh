#!/usr/bin/env bash
# Sets up the demo app on macOS or Linux and runs its tests.
# Usage, from the repository root:  ./scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/../demo-app"

[ -d .venv ] || python3 -m venv .venv
./.venv/bin/python -m pip install --quiet -r requirements.txt
./.venv/bin/python -m pytest -q

echo
echo "Demo app is ready. To run it:"
echo "  cd demo-app && ./.venv/bin/python -m uvicorn app.main:app --reload"
echo "Then open http://127.0.0.1:8000/docs"
