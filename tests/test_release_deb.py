import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "release"))

import build_deb  # noqa: E402


def _fields(control: str) -> dict:
    fields = {}
    for line in control.splitlines():
        if line and not line.startswith(" "):
            name, value = line.split(":", 1)
            fields[name] = value.strip()
    return fields


def test_control_file_fields():
    fields = _fields(build_deb.control_file("1.0.0", 123456))

    assert fields == {
        "Package": "anonimize",
        "Version": "1.0.0",
        "Architecture": "amd64",
        "Maintainer": "kgorczowski <kgorczowski@users.noreply.github.com>",
        "Installed-Size": "123456",
        "Depends": "libc6 (>= 2.35)",
        "Recommends": "tesseract-ocr, unar",
        "Section": "utils",
        "Priority": "optional",
        "Homepage": "https://github.com/kgorczowski/anonimize",
        "Description": "Anonymize project folders before sharing them",
    }


def test_control_file_sorts_release_candidates_before_the_release():
    fields = _fields(build_deb.control_file("1.0.0-rc.1", 1))

    assert fields["Version"] == "1.0.0~rc.1"


def test_control_file_extended_description_is_indented():
    control = build_deb.control_file("1.0.0", 1)
    lines = control.splitlines()
    extended = lines[lines.index(
        "Description: Anonymize project folders before sharing them"
    ) + 1:]

    assert extended
    assert all(line.startswith(" ") for line in extended)
    assert control.endswith("\n")
