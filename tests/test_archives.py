import zipfile
import tarfile
from pathlib import Path

import pytest

from anonymize import (
    classify_archive,
    archive_stem,
    is_archive_file,
    extract_archive,
    scan_files,
    MAX_ARCHIVE_DEPTH,
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


def test_scan_files_returns_plain_files_with_matching_relative_path(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("hello")

    output_root = tmp_path / "out"
    temp_dirs = []

    entries = scan_files(source_dir, output_root, temp_dirs)

    assert len(entries) == 1
    assert entries[0].source == source_dir / "a.txt"
    assert entries[0].relative_destination == Path("a.txt")
    assert temp_dirs == []


def test_scan_files_extracts_zip_and_maps_relative_destination(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    with zipfile.ZipFile(source_dir / "bundle.zip", "w") as archive:
        archive.writestr("inner.txt", "from zip")

    output_root = tmp_path / "out"
    temp_dirs = []

    entries = scan_files(source_dir, output_root, temp_dirs)

    assert len(entries) == 1
    assert entries[0].relative_destination == Path("bundle/inner.txt")
    assert entries[0].source.read_text() == "from zip"
    assert len(temp_dirs) == 1


def test_scan_files_extracts_nested_zip(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    inner_zip_bytes_path = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner_zip_bytes_path, "w") as inner:
        inner.writestr("deep.txt", "deep content")

    with zipfile.ZipFile(source_dir / "outer.zip", "w") as outer:
        outer.write(inner_zip_bytes_path, arcname="inner.zip")

    output_root = tmp_path / "out"
    temp_dirs = []

    entries = scan_files(source_dir, output_root, temp_dirs)

    assert len(entries) == 1
    assert entries[0].relative_destination == Path("outer/inner/deep.txt")
    assert len(temp_dirs) == 2  # outer.zip's extraction + inner.zip's


def test_scan_files_falls_back_to_copy_at_max_depth(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    with zipfile.ZipFile(source_dir / "bundle.zip", "w") as archive:
        archive.writestr("inner.txt", "from zip")

    output_root = tmp_path / "out"
    temp_dirs = []

    entries = scan_files(
        source_dir, output_root, temp_dirs, depth=MAX_ARCHIVE_DEPTH
    )

    assert len(entries) == 1
    assert entries[0].source == source_dir / "bundle.zip"
    assert entries[0].relative_destination == Path("bundle.zip")
    assert temp_dirs == []


def test_scan_files_falls_back_to_copy_on_corrupt_archive(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "broken.zip").write_bytes(b"not a real zip")

    output_root = tmp_path / "out"
    temp_dirs = []

    entries = scan_files(source_dir, output_root, temp_dirs)

    assert len(entries) == 1
    assert entries[0].source == source_dir / "broken.zip"
    assert entries[0].relative_destination == Path("broken.zip")
    assert temp_dirs == []
