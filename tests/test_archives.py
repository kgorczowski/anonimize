import zipfile
import tarfile

import pytest

from anonymize import (
    classify_archive,
    archive_stem,
    is_archive_file,
    extract_archive,
)


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("a.zip", "zip"),
        ("a.tar", "tar"),
        ("a.tar.gz", "tar"),
        ("a.tgz", "tar"),
        ("a.tar.bz2", "tar"),
        ("a.tbz2", "tar"),
        ("a.tar.xz", "tar"),
        ("a.txz", "tar"),
        ("a.7z", "7z"),
        ("a.rar", "rar"),
        ("a.txt", None),
    ],
)
def test_classify_archive(tmp_path, filename, expected):
    assert classify_archive(tmp_path / filename) == expected


@pytest.mark.parametrize(
    "filename,expected_stem",
    [
        ("report.zip", "report"),
        ("report.tar.gz", "report"),
        ("report.tgz", "report"),
        ("report.7z", "report"),
    ],
)
def test_archive_stem(tmp_path, filename, expected_stem):
    assert archive_stem(tmp_path / filename) == expected_stem


def test_is_archive_file(tmp_path):
    assert is_archive_file(tmp_path / "a.zip") is True
    assert is_archive_file(tmp_path / "a.txt") is False


def test_extract_archive_zip(tmp_path):
    source = tmp_path / "source.zip"

    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("inner/hello.txt", "hello world")

    dest = tmp_path / "extracted"
    extract_archive(source, dest)

    assert (dest / "inner" / "hello.txt").read_text() == "hello world"


def test_extract_archive_tar_gz(tmp_path):
    payload = tmp_path / "hello.txt"
    payload.write_text("hello tar")

    source = tmp_path / "source.tar.gz"

    with tarfile.open(source, "w:gz") as archive:
        archive.add(payload, arcname="hello.txt")

    dest = tmp_path / "extracted"
    extract_archive(source, dest)

    assert (dest / "hello.txt").read_text() == "hello tar"


def test_extract_archive_7z(tmp_path):
    py7zr = pytest.importorskip("py7zr")

    payload = tmp_path / "hello.txt"
    payload.write_text("hello 7z")

    source = tmp_path / "source.7z"

    with py7zr.SevenZipFile(source, "w") as archive:
        archive.write(payload, arcname="hello.txt")

    dest = tmp_path / "extracted"
    extract_archive(source, dest)

    assert (dest / "hello.txt").read_text() == "hello 7z"


def test_extract_archive_raises_on_corrupt_rar(tmp_path):
    pytest.importorskip("rarfile")

    source = tmp_path / "broken.rar"
    source.write_bytes(b"not a real rar file")

    with pytest.raises(Exception):
        extract_archive(source, tmp_path / "extracted")
