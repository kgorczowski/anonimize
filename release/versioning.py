"""
Version and release-asset naming shared by every release script.

Standard library only: this runs on the bare Python of a fresh Debian or
Ubuntu container as well as on the build machines.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/kgorczowski/anonimize"

# Platforms we publish a frozen program for, as they appear in asset names.
PLATFORMS = ("windows-x64", "macos-arm64", "macos-x64", "linux-x64")

_VERSION_LINE = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)


def read_version(source: Path = ROOT / "anonymize.py") -> str:
    """Reads __version__ from anonymize.py without importing it."""
    match = _VERSION_LINE.search(source.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"no __version__ line in {source}")
    return match.group(1)


def check_tag(tag: str, version: str) -> None:
    if tag != f"v{version}":
        raise ValueError(
            f"tag {tag} does not match __version__ {version} in anonymize.py "
            f"(expected tag v{version})"
        )


def is_prerelease(version: str) -> bool:
    return "-" in version


def deb_version(version: str) -> str:
    # dpkg sorts "~" before anything, so 1.0.0~rc.1 < 1.0.0, while
    # "1.0.0-rc.1" would read as upstream 1.0.0, Debian revision rc.1.
    return version.replace("-", "~")


def archive_name(version: str, platform: str) -> str:
    extension = "zip" if platform.startswith("windows") else "tar.gz"
    return f"anonimize-{version}-{platform}.{extension}"


def deb_name(version: str) -> str:
    # The file name keeps the tag's spelling; only the control file's
    # Version field uses deb_version().
    return f"anonimize_{version}_amd64.deb"


def download_url(version: str, asset: str) -> str:
    return f"{REPO_URL}/releases/download/v{version}/{asset}"
