#!/usr/bin/env bash
# Installs anonymize.py's Python dependencies with whichever interpreter
# actually works. Tries `py` (Windows Python Launcher) first, then
# `python3`, then `python` -- and actually invokes each candidate rather
# than just checking it's on PATH, because on Windows `python`/`python3`
# are often Microsoft Store redirect stubs that exist on PATH but fail
# the moment you run them (see CONTRIBUTING.md).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

find_python() {
    for candidate in py python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" --version >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

PYTHON="$(find_python)" || {
    echo "No working Python interpreter found (tried py, python3, python)." >&2
    echo "Install Python 3.9+ first." >&2
    exit 1
}

echo "Using $("$PYTHON" --version) ($PYTHON)"
"$PYTHON" -m pip install -r "$SCRIPT_DIR/../requirements.txt"
