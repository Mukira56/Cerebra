#!/usr/bin/env bash
# Stop Cerebra's own server on macOS or Linux (only the verified Cerebra process, never another one).
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then echo "Cerebra's virtual environment is missing; no process will be stopped." >&2; exit 1; fi
.venv/bin/python -m ai_hq.manage stop || { echo "Cerebra could not verify or stop its server. No other process was stopped." >&2; exit 1; }
