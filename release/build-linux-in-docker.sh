#!/usr/bin/env bash
# Builds the Linux release assets -- anonimize-<version>-linux-x64.tar.gz
# and anonimize_<version>_amd64.deb -- in a throwaway ubuntu:22.04
# container, and smoke-tests the built program there. The release
# workflow runs exactly this script, so it also reproduces that job
# locally (needs Docker and bash; on Windows run it from Git Bash or WSL).
#
# Why Ubuntu 22.04: a PyInstaller build only runs on systems whose glibc is
# at least as new as the build system's, so the build happens on the oldest
# system we support (glibc 2.35: Ubuntu 22.04+, Debian 12+). Its own Python
# is 3.10, so Python 3.12 comes from the deadsnakes PPA.
#
# Output on the host: dist/ (the two assets) and
# build/fixtures/smoke-fixtures/ (reused by release/test-deb-in-docker.sh).
# The container copies the WORKING TREE, including uncommitted files.
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$REPO_ROOT/dist" "$REPO_ROOT/build/fixtures"

# Git Bash on Windows: hand Docker a Windows-style path and stop MSYS from
# rewriting the container-side paths. Both are no-ops elsewhere.
if WIN_ROOT="$(cd "$REPO_ROOT" && pwd -W 2>/dev/null)"; then
    REPO_ROOT="$WIN_ROOT"
fi
export MSYS_NO_PATHCONV=1

docker run --rm \
    -v "$REPO_ROOT:/src:ro" \
    -v "$REPO_ROOT/dist:/out/dist" \
    -v "$REPO_ROOT/build/fixtures:/out/fixtures" \
    ubuntu:22.04 bash -c '
    set -e
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq software-properties-common >/dev/null
    add-apt-repository -y ppa:deadsnakes/ppa >/dev/null
    # binutils: PyInstaller inspects shared libraries with objdump.
    # tesseract-ocr, unar: the smoke test exercises OCR and .rar.
    apt-get install -y -qq python3.12 python3.12-venv python3.12-dev \
        binutils tesseract-ocr unar >/dev/null

    mkdir /work
    (cd /src && tar --exclude=./build --exclude=./dist --exclude=./.git \
        --exclude=./.venv --exclude=./.superpowers --exclude=./.worktrees \
        --exclude=__pycache__ -cf - .) | tar -C /work -xf -
    cd /work

    python3.12 -m venv /venv
    /venv/bin/pip install -q -r requirements.txt -r release/requirements-build.txt
    /venv/bin/python release/build.py
    /venv/bin/python release/build_deb.py

    rm -rf /out/fixtures/smoke-fixtures
    /venv/bin/python release/smoke_test.py fixtures /out/fixtures/smoke-fixtures
    /venv/bin/python release/smoke_test.py check \
        --fixtures /out/fixtures/smoke-fixtures \
        --version "$(/venv/bin/python release/render.py version)" \
        -- build/pyinstaller/dist/anonimize/anonimize

    cp dist/* /out/dist/
'
