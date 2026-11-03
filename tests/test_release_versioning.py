import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "release"))

import anonymize  # noqa: E402
import versioning  # noqa: E402


def test_read_version_matches_the_program():
    assert versioning.read_version() == anonymize.__version__


def test_read_version_rejects_a_file_without_a_version(tmp_path):
    source = tmp_path / "anonymize.py"
    source.write_text("print('no version here')\n", encoding="utf-8")

    with pytest.raises(ValueError):
        versioning.read_version(source)


def test_check_tag_accepts_the_matching_tag():
    versioning.check_tag("v1.0.0", "1.0.0")
    versioning.check_tag("v1.0.0-rc.1", "1.0.0-rc.1")


def test_check_tag_rejects_a_mismatch_naming_both_values():
    with pytest.raises(ValueError) as raised:
        versioning.check_tag("v1.0.1", "1.0.0")

    assert "v1.0.1" in str(raised.value)
    assert "1.0.0" in str(raised.value)


def test_deb_version_sorts_release_candidates_before_the_release():
    assert versioning.deb_version("1.0.0-rc.1") == "1.0.0~rc.1"
    assert versioning.deb_version("1.0.0") == "1.0.0"


def test_is_prerelease():
    assert versioning.is_prerelease("1.0.0-rc.1")
    assert not versioning.is_prerelease("1.0.0")


def test_archive_names():
    assert (
        versioning.archive_name("1.0.0", "windows-x64")
        == "anonimize-1.0.0-windows-x64.zip"
    )
    assert (
        versioning.archive_name("1.0.0", "macos-arm64")
        == "anonimize-1.0.0-macos-arm64.tar.gz"
    )
    assert (
        versioning.archive_name("1.0.0-rc.1", "linux-x64")
        == "anonimize-1.0.0-rc.1-linux-x64.tar.gz"
    )


def test_deb_name_keeps_the_tag_spelling():
    assert (
        versioning.deb_name("1.0.0-rc.1") == "anonimize_1.0.0-rc.1_amd64.deb"
    )


def test_download_url():
    assert versioning.download_url("1.0.0", "x.zip") == (
        "https://github.com/kgorczowski/anonimize/releases/download/"
        "v1.0.0/x.zip"
    )
