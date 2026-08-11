import json
import shutil
import sys
import zipfile

import pytest

import anonymize
from anonymize import load_replacements, process_file, scan_files


def test_process_file_applies_dictionary_and_pii_redaction(tmp_path):
    replacements_file = tmp_path / "replacements.json"
    replacements_file.write_text('{"VM": "Company1"}', encoding="utf-8")
    replacements = load_replacements(replacements_file)

    source = tmp_path / "notes.txt"
    source.write_text(
        "VM contact: jan@example.com", encoding="utf-8"
    )

    destination = tmp_path / "out" / "notes.txt"

    status, pii_count = process_file(source, destination, replacements)

    assert status == "anonymized"
    assert pii_count == 1
    assert destination.read_text(encoding="utf-8") == (
        "Company1 contact: [EMAIL]"
    )


def test_process_file_converts_pdf_to_markdown(tmp_path):
    fitz = pytest.importorskip("pymupdf")

    replacements_file = tmp_path / "replacements.json"
    replacements_file.write_text('{"VM": "Company1"}', encoding="utf-8")
    replacements = load_replacements(replacements_file)

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "VM contact jan@example.com")

    source = tmp_path / "report.pdf"
    document.save(source)
    document.close()

    destination = tmp_path / "out" / "report.pdf"

    status, pii_count = process_file(source, destination, replacements)

    md_path = destination.with_suffix(".md")

    assert status == "pdf"
    assert pii_count == 1
    assert md_path.exists()

    content = md_path.read_text(encoding="utf-8")
    assert "Company1 contact [EMAIL]" in content


def test_full_run_processes_mixed_source_tree(tmp_path, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    (source_dir / "plain.txt").write_text(
        "VM owner: jan@example.com", encoding="utf-8"
    )

    with zipfile.ZipFile(source_dir / "bundle.zip", "w") as archive:
        archive.writestr("nested.txt", "BDR ip 192.168.1.5")

    replacements_file = tmp_path / "replacements.json"
    replacements_file.write_text(
        json.dumps({"VM": "Company1", "BDR": "Company2"}),
        encoding="utf-8",
    )
    replacements = load_replacements(replacements_file)

    output_root = tmp_path / "out"
    temp_dirs = []
    extraction_errors = []

    try:
        entries = scan_files(source_dir, output_root, temp_dirs, extraction_errors)

        results = {}
        for entry in entries:
            destination = output_root / entry.relative_destination
            status, pii_count = process_file(
                entry.source, destination, replacements
            )
            results[entry.relative_destination.as_posix()] = (status, pii_count)
    finally:
        for temp_dir in temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)

    assert extraction_errors == []
    assert len(entries) == 2  # no stray or duplicated entries
    assert results["plain.txt"] == ("anonymized", 1)
    assert (output_root / "plain.txt").read_text(encoding="utf-8") == (
        "Company1 owner: [EMAIL]"
    )

    assert results["bundle/nested.txt"] == ("anonymized", 1)
    assert (output_root / "bundle" / "nested.txt").read_text(
        encoding="utf-8"
    ) == "Company2 ip [IP]"

    for temp_dir in temp_dirs:
        assert not temp_dir.exists()

    # Happy path: nothing should have been logged to stderr.
    stderr = capsys.readouterr().err
    assert "ERROR:" not in stderr
    assert "WARNING:" not in stderr


def _run_cli(monkeypatch, source_dir, replacements_file, output_root):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "anonymize.py",
            str(source_dir),
            str(replacements_file),
            "--output",
            str(output_root),
        ],
    )
    anonymize.main()


def test_failed_file_is_copied_unchanged_instead_of_disappearing(
    tmp_path, monkeypatch, capsys
):
    """
    A file that cannot be converted must still reach the output. The
    realistic trigger is a scanned PDF page on a machine without
    Tesseract: ocr_page raises and the PDF used to vanish silently.
    """
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    original_bytes = b"%PDF-1.4 pretend this is a scanned page"
    (source_dir / "scan.pdf").write_bytes(original_bytes)
    (source_dir / "plain.txt").write_text("VM ok", encoding="utf-8")

    replacements_file = tmp_path / "replacements.json"
    replacements_file.write_text('{"VM": "Company1"}', encoding="utf-8")

    def no_tesseract(source):
        raise RuntimeError("Tesseract OCR engine not found.")

    monkeypatch.setattr(anonymize, "convert_pdf_to_markdown", no_tesseract)

    output_root = tmp_path / "out"
    _run_cli(monkeypatch, source_dir, replacements_file, output_root)

    captured = capsys.readouterr()

    assert (output_root / "scan.pdf").read_bytes() == original_bytes
    assert not (output_root / "scan.md").exists()
    # The rest of the run still completes normally.
    assert (output_root / "plain.txt").read_text(encoding="utf-8") == (
        "Company1 ok"
    )
    assert "ERROR:" in captured.err
    assert "Errors            : 1" in captured.out


def test_full_run_keeps_both_sides_of_an_output_path_collision(
    tmp_path, monkeypatch, capsys
):
    """
    data.zip extracts to data/, which already exists as a plain
    directory. Both files must survive in the output.
    """
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    (source_dir / "data").mkdir()
    (source_dir / "data" / "notes.txt").write_text(
        "VM from the directory", encoding="utf-8"
    )

    with zipfile.ZipFile(source_dir / "data.zip", "w") as archive:
        archive.writestr("notes.txt", "VM from the archive")

    replacements_file = tmp_path / "replacements.json"
    replacements_file.write_text('{"VM": "Company1"}', encoding="utf-8")

    output_root = tmp_path / "out"
    _run_cli(monkeypatch, source_dir, replacements_file, output_root)

    captured = capsys.readouterr()

    written = sorted(
        path.read_text(encoding="utf-8")
        for path in (output_root / "data").iterdir()
    )

    assert written == [
        "Company1 from the archive",
        "Company1 from the directory",
    ]
    assert "WARNING:" in captured.err
    assert "collision" in captured.err
    assert "Errors            : 0" in captured.out
