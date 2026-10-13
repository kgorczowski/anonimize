#!/usr/bin/env bash
# Runs the test suite and fails if ANY test was skipped. Tests that need
# an optional system tool (Tesseract, a .rar extractor) skip themselves when
# it is missing; CI installs every such tool, so a skip there means a tool
# is missing or was not detected, and a green run would otherwise be
# claiming coverage it did not get.
#
#   PYTHON=py bash scripts/run-tests.sh          # pick the interpreter
#   bash scripts/run-tests.sh tests/test_pdf.py  # extra args go to pytest
set -eo pipefail

PYTHON="${PYTHON:-python}"
LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT

"$PYTHON" -m pytest -q -rs "$@" | tee "$LOG"

if grep -Eq '[0-9]+ skipped' "$LOG"; then
    echo >&2
    echo "ERROR: tests were skipped. Every optional dependency should be installed here, so a skip means one is missing or not detected." >&2
    exit 1
fi
