#!/usr/bin/env bash
# Cerebra setup for macOS and Linux: a private .venv with Cerebra's dependencies, then a health check.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
    python=""
    for candidate in python3.13 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 13))' 2>/dev/null; then
            python="$candidate"; break
        fi
    done
    if [ -z "$python" ]; then
        echo "Python 3.13+ is required. Install it (python.org, Homebrew, or your package manager) only after reviewing and approving the installation." >&2
        exit 1
    fi
    "$python" -m venv .venv
fi
arguments=(-m pip install --no-cache-dir -e '.[dev]')
if [ -f requirements.lock ]; then arguments+=(--constraint requirements.lock); fi
.venv/bin/python "${arguments[@]}"
echo "Project dependencies installed in the local .venv. Preparing and checking Cerebra..."
.venv/bin/python -m ai_hq.manage doctor
echo "Setup complete. Run ./scripts/start.sh to open your private local dashboard."
