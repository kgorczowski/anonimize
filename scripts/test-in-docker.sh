#!/usr/bin/env bash
# Runs the strict test suite the way the Linux CI job does, in a throwaway
# Ubuntu container, so Linux-only failures can be reproduced locally (for
# example from Windows with Docker Desktop). Requires Docker.
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Git Bash on Windows: hand Docker a Windows-style path and stop MSYS from
# rewriting the container-side paths. Both are no-ops elsewhere.
if WIN_ROOT="$(cd "$REPO_ROOT" && pwd -W 2>/dev/null)"; then
    REPO_ROOT="$WIN_ROOT"
fi
export MSYS_NO_PATHCONV=1

docker run --rm -v "$REPO_ROOT:/src:ro" ubuntu:24.04 bash -c '
    set -e
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv tesseract-ocr unar >/dev/null
    cp -r /src /work
    cd /work
    find . -name __pycache__ -prune -exec rm -rf {} +
    python3 -m venv /venv
    /venv/bin/pip install -q -r requirements.txt
    PYTHON=/venv/bin/python bash scripts/run-tests.sh
'
