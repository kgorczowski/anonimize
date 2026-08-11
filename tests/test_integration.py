from pathlib import Path

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
