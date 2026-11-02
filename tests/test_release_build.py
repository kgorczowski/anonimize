import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "release"))

import build  # noqa: E402


def test_forbidden_files_finds_every_replacements_file(tmp_path):
    for name in (
        "x/replacements.json",
        "replacement.json",
        "deep/er/REPLACEMENTS.JSON",
        "notes.json",
        "x/replacements.txt",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    found = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in build.forbidden_files(tmp_path)
    )

    assert found == [
        "deep/er/REPLACEMENTS.JSON",
        "replacement.json",
        "x/replacements.json",
    ]


def test_forbidden_entries_reads_onefile_archive_names():
    # Names as PyInstaller's CArchiveReader lists them on Windows.
    names = [
        "docx\\templates\\default-comments.xml",
        "some\\dir\\replacements.json",
        "Replacement.JSON",
        "pymupdf\\layout\\resources\\onnx\\layout_imf1.yaml",
    ]

    assert build._forbidden_entries(names) == [
        "some\\dir\\replacements.json",
        "Replacement.JSON",
    ]


@pytest.mark.parametrize(
    "system, machine, expected",
    [
        ("win32", "AMD64", "windows-x64"),
        ("darwin", "arm64", "macos-arm64"),
        ("darwin", "x86_64", "macos-x64"),
        ("linux", "x86_64", "linux-x64"),
    ],
)
def test_current_platform(monkeypatch, system, machine, expected):
    monkeypatch.setattr(build.sys, "platform", system)
    monkeypatch.setattr(build.platform, "machine", lambda: machine)

    assert build.current_platform() == expected


def test_current_platform_rejects_an_unsupported_one(monkeypatch):
    monkeypatch.setattr(build.sys, "platform", "linux")
    monkeypatch.setattr(build.platform, "machine", lambda: "aarch64")

    with pytest.raises(SystemExit) as exited:
        build.current_platform()

    assert "aarch64" in str(exited.value)


def test_program_path():
    assert build.program_path("windows-x64").as_posix().endswith(
        "build/pyinstaller/dist/anonimize.exe"
    )
    assert build.program_path("linux-x64").as_posix().endswith(
        "build/pyinstaller/dist/anonimize/anonimize"
    )
