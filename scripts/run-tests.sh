#!/usr/bin/env bash
# Runs the test suite and fails if ANY test was skipped. Tests that need
# an optional system tool (Tesseract, a .rar extractor) skip themselves when
# it is missing; CI installs every such tool, so a skip there means a tool
# is missing or was not detected, and a green run would otherwise be
# claiming coverage it did not get.
#
#   PYTHON=py bash scripts/run-tests.sh          # pick the interpreter
#   bash scripts/run-tests.sh tests/test_pdf.py  # extra args go to pytest
#
# -q, --color=no and -rfEs come AFTER the caller's arguments on purpose, so
# a caller (or PYTEST_ADDOPTS, or an ini file) cannot switch off the
# evidence the guard reads: -rs prints a "SKIPPED [n]" line per skip even
# when a quiet setting drops pytest's closing "N skipped" line, --color=no
# keeps escape codes out of those lines, and -rfE keeps FAILED and ERROR
# lines in the short summary.
set -eo pipefail

PYTHON="${PYTHON:-python}"
LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT

status=0
"$PYTHON" -m pytest "$@" -q --color=no -rfEs | tee "$LOG" || status=$?

# On GitHub Actions, repeat the failing and skipped lines as annotations:
# they can be read without signing in to GitHub, the raw log cannot.
if [ -n "${GITHUB_ACTIONS:-}" ]; then
    grep -E '^(FAILED|ERROR|SKIPPED)' "$LOG" | head -n 10 | while IFS= read -r line; do
        echo "::error::${line}"
    done || true
fi

if [ "$status" -ne 0 ]; then
    exit "$status"
fi

if grep -Eq 'SKIPPED \[[0-9]+\]|[0-9]+ skipped' "$LOG"; then
    echo >&2
    echo "ERROR: tests were skipped. Every optional dependency should be installed here, so a skip means one is missing or not detected." >&2
    exit 1
fi
