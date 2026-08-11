from pathlib import Path

import pytest

from anonymize import process_file, load_replacements


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
