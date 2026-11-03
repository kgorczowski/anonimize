"""
Wraps the Linux onedir build from release/build.py into a Debian package
in dist/.

    python release/build_deb.py

Linux only (needs dpkg-deb); release/build-linux-in-docker.sh runs it.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import build
import versioning

MAINTAINER = "kgorczowski <kgorczowski@users.noreply.github.com>"
SUMMARY = "Anonymize project folders before sharing them"
EXTENDED_DESCRIPTION = (
    "Writes an anonymized copy of a folder: replaces dictionary terms in",
    "file contents and in file and folder names, redacts common PII",
    "(e-mail, phone, PESEL, NIP, IBAN, card numbers, IP addresses),",
    "converts Office documents and PDFs to Markdown, extracts archives and",
    "blacks out logo images.",
)


def control_file(version: str, installed_size_kib: int) -> str:
    lines = [
        "Package: anonimize",
        f"Version: {versioning.deb_version(version)}",
        "Architecture: amd64",
        f"Maintainer: {MAINTAINER}",
        f"Installed-Size: {installed_size_kib}",
        # The build runs on Ubuntu 22.04; a PyInstaller build needs a glibc
        # at least as new as the one it was built against.
        "Depends: libc6 (>= 2.35)",
        # Optional tools for scanned PDFs and .rar archives; apt installs
        # recommended packages by default.
        "Recommends: tesseract-ocr, unar",
        "Section: utils",
        "Priority: optional",
        f"Homepage: {versioning.REPO_URL}",
        f"Description: {SUMMARY}",
        *(f" {line}" for line in EXTENDED_DESCRIPTION),
    ]
    return "\n".join(lines) + "\n"


def _normalize_modes(stage: Path) -> None:
    # dpkg-deb rejects a DEBIAN folder that is not 0755, and installed
    # files should be world-readable whatever the build's umask was.
    for path in [stage, *stage.rglob("*")]:
        if path.is_symlink():
            continue
        if path.is_dir() or path.stat().st_mode & 0o111:
            path.chmod(0o755)
        else:
            path.chmod(0o644)


def main() -> int:
    if not sys.platform.startswith("linux"):
        raise SystemExit("build_deb.py runs on Linux (it needs dpkg-deb)")
    onedir = build.program_path("linux-x64").parent
    if not onedir.is_dir():
        raise SystemExit(f"{onedir} not found: run release/build.py first")

    version = versioning.read_version()
    target = build.DIST / versioning.deb_name(version)

    with tempfile.TemporaryDirectory() as scratch:
        stage = Path(scratch) / "anonimize"
        shutil.copytree(onedir, stage / "usr" / "lib" / "anonimize", symlinks=True)

        (stage / "usr" / "bin").mkdir(parents=True)
        os.symlink("../lib/anonimize/anonimize", stage / "usr" / "bin" / "anonimize")

        docs = stage / "usr" / "share" / "doc" / "anonimize"
        docs.mkdir(parents=True)
        shutil.copyfile(versioning.ROOT / "LICENSE", docs / "copyright")

        size_kib = sum(
            path.stat().st_size
            for path in stage.rglob("*")
            if path.is_file() and not path.is_symlink()
        ) // 1024 + 1

        (stage / "DEBIAN").mkdir()
        (stage / "DEBIAN" / "control").write_text(
            control_file(version, size_kib), encoding="utf-8"
        )
        _normalize_modes(stage)

        build.DIST.mkdir(exist_ok=True)
        target.unlink(missing_ok=True)
        subprocess.run(
            ["dpkg-deb", "--build", "--root-owner-group", str(stage), str(target)],
            check=True,
        )

    print(f"deb: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
