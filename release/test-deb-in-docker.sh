#!/usr/bin/env bash
# Installs dist/anonimize_<version>_amd64.deb into a fresh container of the
# given image the way a user would -- apt also pulls in the recommended
# tesseract-ocr and unar -- and runs the smoke test through
# /usr/bin/anonimize, i.e. through the package's symlink.
#
#   bash release/test-deb-in-docker.sh ubuntu:22.04
#   bash release/test-deb-in-docker.sh ubuntu:24.04
#   bash release/test-deb-in-docker.sh debian:12
#
# Run release/build-linux-in-docker.sh first (it writes the .deb and the
# smoke-test fixtures). python3 is installed only to run the checker; the
# package itself does not need it.
set -e

IMAGE="${1:?usage: test-deb-in-docker.sh <image>}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if WIN_ROOT="$(cd "$REPO_ROOT" && pwd -W 2>/dev/null)"; then
    REPO_ROOT="$WIN_ROOT"
fi
export MSYS_NO_PATHCONV=1

docker run --rm -v "$REPO_ROOT:/src:ro" "$IMAGE" bash -c '
    set -e
    export DEBIAN_FRONTEND=noninteractive
    # Text between the quotes; works with CRLF files from a Windows checkout.
    version="$(grep -m1 "^__version__ = " /src/anonymize.py | cut -d\" -f2)"
    if [ -z "$version" ]; then
        echo "could not read __version__ from anonymize.py" >&2
        exit 1
    fi
    apt-get update -qq
    apt-get install -y -qq "/src/dist/anonimize_${version}_amd64.deb" python3 >/dev/null

    target="$(readlink -f /usr/bin/anonimize)"
    if [ "$target" != /usr/lib/anonimize/anonimize ]; then
        echo "/usr/bin/anonimize resolves to $target" >&2
        exit 1
    fi

    cd /tmp
    python3 /src/release/smoke_test.py check \
        --fixtures /src/build/fixtures/smoke-fixtures \
        --version "$version" \
        -- /usr/bin/anonimize
'
