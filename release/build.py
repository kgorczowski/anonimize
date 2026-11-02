"""
Freezes anonymize.py with PyInstaller for the current platform and packs
the result as this platform's release archive in dist/.

    python release/build.py

Needs requirements.txt and release/requirements-build.txt installed in the
running Python.

Windows gets one anonimize.exe (onefile): winget starts portable apps
through a symlink, and a symlinked onedir executable cannot find its DLLs
(pyinstaller/pyinstaller#5575). macOS and Linux get the onedir folder
anonimize/, which starts faster because nothing is unpacked per run.
"""

import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Iterable, List

import versioning

BUILD = versioning.ROOT / "build" / "pyinstaller"
DIST = versioning.ROOT / "dist"

_PLATFORMS = {
    ("win32", "amd64"): "windows-x64",
    ("darwin", "arm64"): "macos-arm64",
    ("darwin", "x86_64"): "macos-x64",
    ("linux", "x86_64"): "linux-x64",
}


def current_platform() -> str:
    machine = platform.machine()
    try:
        return _PLATFORMS[(sys.platform, machine.lower())]
    except KeyError:
        raise SystemExit(
            f"unsupported build platform: {sys.platform} {machine}"
        ) from None


def program_path(platform_name: str) -> Path:
    if platform_name.startswith("windows"):
        return BUILD / "dist" / "anonimize.exe"
    return BUILD / "dist" / "anonimize" / "anonimize"


def is_forbidden_name(name: str) -> bool:
    # A dictionary of real client names must never ship inside a package.
    lowered = name.lower()
    return lowered.startswith("replacement") and lowered.endswith(".json")


def forbidden_files(bundle: Path) -> List[Path]:
    return [
        path
        for path in bundle.rglob("*")
        if path.is_file() and is_forbidden_name(path.name)
    ]


def _forbidden_entries(names: Iterable[str]) -> List[str]:
    return [
        name
        for name in names
        if is_forbidden_name(name.replace("\\", "/").rsplit("/", 1)[-1])
    ]


def _onefile_entries(executable: Path) -> List[str]:
    """Names of the files bundled inside a onefile executable."""
    # Imported here: PyInstaller is only installed where builds run.
    from PyInstaller.archive.readers import CArchiveReader

    return list(CArchiveReader(str(executable)).toc)


def freeze(platform_name: str) -> Path:
    onefile = platform_name.startswith("windows")
    shutil.rmtree(BUILD / "dist", ignore_errors=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(versioning.ROOT / "anonymize.py"),
            "--name",
            "anonimize",
            "--console",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(BUILD / "dist"),
            "--workpath",
            str(BUILD / "work"),
            "--specpath",
            str(BUILD),
            "--onefile" if onefile else "--onedir",
            # PyMuPDF 2's find_tables() loads layout models (.onnx/.yaml)
            # from this subpackage; the stock hook leaves them out, and
            # every PDF then fails in the frozen program. Only this
            # subpackage: the rest of PyMuPDF's data is C++ headers.
            "--collect-data",
            "pymupdf.layout",
        ],
        check=True,
        cwd=versioning.ROOT,
    )
    return program_path(platform_name)


def check_bundle(platform_name: str, program: Path) -> None:
    if platform_name.startswith("windows"):
        found = _forbidden_entries(_onefile_entries(program))
    else:
        found = [str(path) for path in forbidden_files(program.parent)]
    if found:
        raise SystemExit(
            "refusing to package a build that contains a replacements "
            f"file: {found}"
        )


def pack(platform_name: str, version: str, program: Path) -> Path:
    DIST.mkdir(exist_ok=True)
    target = DIST / versioning.archive_name(version, platform_name)
    target.unlink(missing_ok=True)
    if platform_name.startswith("windows"):
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(program, program.name)
    else:
        # tarfile keeps file modes and symlinks.
        with tarfile.open(target, "w:gz") as archive:
            archive.add(program.parent, arcname="anonimize")
    return target


def main() -> int:
    platform_name = current_platform()
    version = versioning.read_version()
    program = freeze(platform_name)
    check_bundle(platform_name, program)
    archive = pack(platform_name, version, program)
    print(f"program: {program}")
    print(f"archive: {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
