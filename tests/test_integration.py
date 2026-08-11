import json
import shutil
import zipfile
from pathlib import Path

import pytest

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
    fitz = pytest.importorskip("fitz")

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
