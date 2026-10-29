#!/usr/bin/env bash
# Start Cerebra on macOS or Linux and open the private dashboard in the browser.
set -euo pipefail
port="${1:-8765}"
case "$port" in ''|*[!0-9]*) echo "The port must be a number from 1024 to 65535." >&2; exit 1;; esac
if [ "$port" -lt 1024 ] || [ "$port" -gt 65535 ]; then echo "The port must be a number from 1024 to 65535." >&2; exit 1; fi
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then echo "Cerebra's virtual environment is missing. Run ./scripts/setup.sh first." >&2; exit 1; fi
.venv/bin/python -m ai_hq.manage start --port "$port" || { echo "Cerebra could not start. Review the error and data/server.log." >&2; exit 1; }
