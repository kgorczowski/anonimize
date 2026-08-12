import zipfile
import tarfile
from pathlib import Path

import pytest

from anonymize import (
    classify_archive,
    archive_stem,
    deduplicate_destinations,
    is_archive_file,
    extract_archive,
    scan_files,
    ScanEntry,
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


@pytest.mark.parametrize(
    "filename",
    [
        ".zip",
        ".rar",
        ".7z",
        ".tar",
        ".tar.gz",
        "..zip",
        "...zip",
        "..tar.gz",
        "...tar.gz",
    ],
)
def test_archive_stem_of_suffix_only_name_is_usable(tmp_path, filename):
    """
    A file (or archive member) named exactly ".zip" strips down to an
    empty stem. Path.with_name("") raises ValueError, which used to
    escape scan_files and abort the whole run. "..zip" and "...zip"
    strip down to "." and "..": with_name(".") raises the same way, and
    with_name("..") quietly builds a path that climbs out of the output
    directory.
    """
    stem = archive_stem(tmp_path / filename)

    assert stem
    assert stem not in (".", "..")
    # Must be usable as a path component - this is what scan_files does.
    assert Path("a/b.zip").with_name(stem).name == stem


@pytest.mark.parametrize(
    "filename,expected_stem",
    [
        (".zip", ".zip"),
        ("..zip", "..zip"),
        ("...zip", "...zip"),
        (".tar.gz", ".tar.gz"),
        ("..tar.gz", "..tar.gz"),
        ("...tar.gz", "...tar.gz"),
    ],
)
def test_archive_stem_of_dot_only_name_falls_back_to_the_name(
    tmp_path, filename, expected_stem
):
    """
    Exact output, not just "does not crash": the fallback must be the
    on-disk name, which is a valid path component by construction.

    It used to fall back to Path.stem, whose result for these names is
    version-dependent - before Python 3.14, Path("..zip").stem is "."
    and Path("...zip").stem is ".." - so the crash and the directory
    escape survived on every pre-3.14 interpreter.
    """
    assert archive_stem(tmp_path / filename) == expected_stem


@pytest.mark.parametrize(
    "filename,legacy_stem",
    [
        ("..zip", "."),
        ("...zip", ".."),
        ("..tar.gz", ".tar"),
        ("...tar.gz", "..tar"),
    ],
)
def test_archive_stem_ignores_path_stem(tmp_path, filename, legacy_stem):
    """
    Version-independence, pinned: archive_stem must not consult .stem
    for these names at all. Feeding it the values CPython 3.9-3.13
    actually returns must not change the result.
    """
    class LegacyPath:
        # archive_stem only ever reads .name and .stem.
        name = filename
        stem = legacy_stem

    assert archive_stem(LegacyPath()) == filename
    assert archive_stem(LegacyPath()) == archive_stem(tmp_path / filename)


@pytest.mark.parametrize("arcname", [".zip", "..zip", "...zip"])
def test_scan_files_handles_dot_only_archive_member_names(tmp_path, arcname):
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    inner_zip = tmp_path / "payload.zip"
    with zipfile.ZipFile(inner_zip, "w") as inner:
        inner.writestr("note.txt", "inner note")

    with zipfile.ZipFile(source_dir / "outer.zip", "w") as outer:
        outer.write(inner_zip, arcname=arcname)

    output_root = tmp_path / "out"
    temp_dirs = []
    extraction_errors = []

    entries = scan_files(source_dir, output_root, temp_dirs, extraction_errors)

    assert len(entries) == 1

    destination = entries[0].relative_destination

    assert destination.parts[0] == "outer"
    assert destination.name == "note.txt"
    # No component may let the output escape the output directory.
    assert ".." not in destination.parts
    assert "." not in destination.parts
    assert extraction_errors == []


def test_scan_files_handles_member_named_exactly_dot_zip(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    inner_zip = tmp_path / "payload.zip"
    with zipfile.ZipFile(inner_zip, "w") as inner:
        inner.writestr("note.txt", "inner note")

    with zipfile.ZipFile(source_dir / "outer.zip", "w") as outer:
        outer.write(inner_zip, arcname=".zip")

    output_root = tmp_path / "out"
    temp_dirs = []
    extraction_errors = []

    entries = scan_files(source_dir, output_root, temp_dirs, extraction_errors)

    assert len(entries) == 1
    assert entries[0].relative_destination.parts[0] == "outer"
    assert entries[0].relative_destination.name == "note.txt"
    assert extraction_errors == []


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


def _make_traversal_tar(tmp_path: Path) -> Path:
    payload = tmp_path / "evil.txt"
    payload.write_text("pwned")

    source = tmp_path / "evil.tar"

    with tarfile.open(source, "w") as archive:
        archive.add(payload, arcname="../escaped.txt")

    return source


def test_extract_archive_tar_rejects_path_traversal(tmp_path):
    """
    Whatever Python version is running: a member pointing outside the
    destination must raise rather than be written.
    """
    source = _make_traversal_tar(tmp_path)
    dest = tmp_path / "extracted"

    with pytest.raises(Exception):
        extract_archive(source, dest)

    assert not (tmp_path / "escaped.txt").exists()


def test_extract_archive_tar_rejects_path_traversal_without_filter_support(
    tmp_path, monkeypatch
):
    """
    Python < 3.12 has no extractall(filter=...). Force that branch so the
    manual safety check is exercised on any interpreter - it used to
    extract completely unfiltered, writing outside the temp tree that
    main() cleans up.
    """
    source = _make_traversal_tar(tmp_path)
    dest = tmp_path / "extracted"

    original_extractall = tarfile.TarFile.extractall

    def extractall_without_filter(self, path=".", members=None, **kwargs):
        if "filter" in kwargs:
            raise TypeError(
                "extractall() got an unexpected keyword argument 'filter'"
            )
        return original_extractall(self, path, members, **kwargs)

    monkeypatch.setattr(
        tarfile.TarFile, "extractall", extractall_without_filter
    )

    with pytest.raises(ValueError, match="Unsafe path in tar archive"):
        extract_archive(source, dest)

    assert not (tmp_path / "escaped.txt").exists()


def test_extract_archive_tar_still_extracts_safe_members_without_filter(
    tmp_path, monkeypatch
):
    payload = tmp_path / "hello.txt"
    payload.write_text("hello tar")

    source = tmp_path / "safe.tar"
    with tarfile.open(source, "w") as archive:
        archive.add(payload, arcname="inner/hello.txt")

    original_extractall = tarfile.TarFile.extractall

    def extractall_without_filter(self, path=".", members=None, **kwargs):
        if "filter" in kwargs:
            raise TypeError(
                "extractall() got an unexpected keyword argument 'filter'"
            )
        return original_extractall(self, path, members, **kwargs)

    monkeypatch.setattr(
        tarfile.TarFile, "extractall", extractall_without_filter
    )

    dest = tmp_path / "extracted"
    extract_archive(source, dest)

    assert (dest / "inner" / "hello.txt").read_text() == "hello tar"


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
    extraction_errors = []

    entries = scan_files(source_dir, output_root, temp_dirs, extraction_errors)

    assert len(entries) == 1
    assert entries[0].source == source_dir / "a.txt"
    assert entries[0].relative_destination == Path("a.txt")
    assert temp_dirs == []
    assert extraction_errors == []


def test_scan_files_extracts_zip_and_maps_relative_destination(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    with zipfile.ZipFile(source_dir / "bundle.zip", "w") as archive:
        archive.writestr("inner.txt", "from zip")

    output_root = tmp_path / "out"
    temp_dirs = []
    extraction_errors = []

    entries = scan_files(source_dir, output_root, temp_dirs, extraction_errors)

    assert len(entries) == 1
    assert entries[0].relative_destination == Path("bundle/inner.txt")
    assert entries[0].source.read_text() == "from zip"
    assert len(temp_dirs) == 1
    assert extraction_errors == []


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
    extraction_errors = []

    entries = scan_files(source_dir, output_root, temp_dirs, extraction_errors)

    assert len(entries) == 1
    assert entries[0].relative_destination == Path("outer/inner/deep.txt")
    assert len(temp_dirs) == 2  # outer.zip's extraction + inner.zip's
    assert extraction_errors == []


def test_scan_files_falls_back_to_copy_at_max_depth(tmp_path, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    with zipfile.ZipFile(source_dir / "bundle.zip", "w") as archive:
        archive.writestr("inner.txt", "from zip")

    output_root = tmp_path / "out"
    temp_dirs = []
    extraction_errors = []

    entries = scan_files(
        source_dir,
        output_root,
        temp_dirs,
        extraction_errors,
        depth=MAX_ARCHIVE_DEPTH,
    )

    assert len(entries) == 1
    assert entries[0].source == source_dir / "bundle.zip"
    assert entries[0].relative_destination == Path("bundle.zip")
    assert temp_dirs == []
    # Hitting the depth limit is a deliberate policy fallback, not a
    # failure - it must not be counted as an extraction error.
    assert extraction_errors == []

    # ...but it must not be silent either: the archive is copied out
    # verbatim, with dictionary terms and PII still inside it.
    stderr = capsys.readouterr().err
    assert "WARNING:" in stderr
    assert "depth limit" in stderr
    assert str(MAX_ARCHIVE_DEPTH) in stderr
    assert "bundle.zip" in stderr
    assert "ERROR:" not in stderr


def test_scan_files_falls_back_to_copy_on_corrupt_archive(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "broken.zip").write_bytes(b"not a real zip")

    output_root = tmp_path / "out"
    temp_dirs = []
    extraction_errors = []

    entries = scan_files(source_dir, output_root, temp_dirs, extraction_errors)

    assert len(entries) == 1
    assert entries[0].source == source_dir / "broken.zip"
    assert entries[0].relative_destination == Path("broken.zip")
    assert temp_dirs == []
    assert extraction_errors == [source_dir / "broken.zip"]


def test_scan_files_corrupt_archive_error_counts_toward_errors_total(tmp_path):
    """
    Mirrors how main() folds extraction_errors into its errors summary
    counter (errors += len(extraction_errors)), without needing to drive
    the full CLI. A corrupt archive must be counted as an error even
    though it still produces a ScanEntry (copied unchanged).
    """
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "broken.zip").write_bytes(b"not a real zip")

    output_root = tmp_path / "out"
    temp_dirs = []
    extraction_errors = []

    entries = scan_files(source_dir, output_root, temp_dirs, extraction_errors)

    errors = 0
    errors += len(extraction_errors)

    assert len(entries) == 1  # still falls back to a copy of the archive
    assert errors == 1


def test_deduplicate_destinations_leaves_unique_entries_untouched(tmp_path):
    entries = [
        ScanEntry(tmp_path / "a.txt", Path("a.txt")),
        ScanEntry(tmp_path / "sub" / "b.txt", Path("sub/b.txt")),
    ]

    assert deduplicate_destinations(entries) == entries


def test_deduplicate_destinations_renames_archive_over_plain_directory(
    tmp_path, capsys
):
    """
    data.zip extracts to data/, so its members collide with an existing
    data/ directory in the source tree. Pass 2 used to silently
    overwrite, and one of the two files vanished from the output.
    """
    entries = [
        ScanEntry(tmp_path / "data" / "notes.txt", Path("data/notes.txt")),
        ScanEntry(tmp_path / "extracted" / "notes.txt", Path("data/notes.txt")),
    ]

    result = deduplicate_destinations(entries)

    destinations = [entry.relative_destination for entry in result]

    assert len(result) == 2
    assert len(set(destinations)) == 2
    assert destinations[0] == Path("data/notes.txt")
    assert destinations[1] == Path("data/notes__2.txt")
    # Sources are preserved: nothing is dropped.
    assert [entry.source for entry in result] == [
        entry.source for entry in entries
    ]

    stderr = capsys.readouterr().err
    assert "WARNING:" in stderr
    assert "collision" in stderr


def test_deduplicate_destinations_renames_archives_sharing_a_stem(
    tmp_path, capsys
):
    """data.zip and data.tar.gz both stem to "data"."""
    entries = [
        ScanEntry(tmp_path / "one" / "inner.txt", Path("data/inner.txt")),
        ScanEntry(tmp_path / "two" / "inner.txt", Path("data/inner.txt")),
        ScanEntry(tmp_path / "three" / "inner.txt", Path("data/inner.txt")),
    ]

    result = deduplicate_destinations(entries)

    destinations = [entry.relative_destination for entry in result]

    assert destinations == [
        Path("data/inner.txt"),
        Path("data/inner__2.txt"),
        Path("data/inner__3.txt"),
    ]
    assert capsys.readouterr().err.count("WARNING:") == 2


def test_deduplicate_destinations_skips_names_already_taken(tmp_path):
    entries = [
        ScanEntry(tmp_path / "one" / "inner.txt", Path("inner.txt")),
        ScanEntry(tmp_path / "two" / "inner__2.txt", Path("inner__2.txt")),
        ScanEntry(tmp_path / "three" / "inner.txt", Path("inner.txt")),
    ]

    destinations = [
        entry.relative_destination
        for entry in deduplicate_destinations(entries)
    ]

    assert len(set(destinations)) == 3
    assert destinations[2] == Path("inner__3.txt")


def test_scan_files_nested_corrupt_archive_is_counted_as_extraction_error(
    tmp_path,
):
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    with zipfile.ZipFile(source_dir / "outer.zip", "w") as outer:
        # A member named *.zip whose bytes are not actually a valid zip:
        # is_archive_file() will try to recurse into it and fail.
        outer.writestr("broken.zip", "not a real zip")

    output_root = tmp_path / "out"
    temp_dirs = []
    extraction_errors = []

    entries = scan_files(source_dir, output_root, temp_dirs, extraction_errors)

    assert len(entries) == 1
    assert entries[0].relative_destination == Path("outer/broken.zip")
    assert len(extraction_errors) == 1
