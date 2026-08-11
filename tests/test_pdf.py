from pathlib import Path

import pytest

fitz = pytest.importorskip("pymupdf")

from anonymize import convert_pdf_to_markdown


def _make_text_pdf(path: Path, lines: list) -> None:
    document = fitz.open()
    page = document.new_page()

    y = 72
    for line in lines:
        page.insert_text((72, y), line)
        y += 20

    document.save(path)
    document.close()


def test_convert_pdf_to_markdown_extracts_text(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    _make_text_pdf(pdf_path, ["Hello from PDF", "Second line"])

    markdown = convert_pdf_to_markdown(pdf_path)

    assert "# Page 1" in markdown
    assert "Hello from PDF" in markdown
    assert "Second line" in markdown


def test_convert_pdf_to_markdown_labels_multiple_pages(tmp_path):
    document = fitz.open()

    page1 = document.new_page()
    page1.insert_text((72, 72), "Page one text")

    page2 = document.new_page()
    page2.insert_text((72, 72), "Page two text")

    pdf_path = tmp_path / "multi.pdf"
    document.save(pdf_path)
    document.close()

    markdown = convert_pdf_to_markdown(pdf_path)

    assert "# Page 1" in markdown
    assert "Page one text" in markdown
    assert "# Page 2" in markdown
    assert "Page two text" in markdown
