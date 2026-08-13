import time
from pathlib import Path

import pytest

fitz = pytest.importorskip("pymupdf")

import anonymize
from anonymize import convert_pdf_to_markdown, extract_pdf_tables, PdfTableTimeoutError


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


class _SlowFindTablesPage:
    """Stands in for a fitz.Page whose find_tables() call never returns
    in reasonable time, without needing a real pathological PDF."""

    def find_tables(self):
        time.sleep(5)

        class _Result:
            tables = []

        return _Result()


def test_extract_pdf_tables_raises_on_timeout_instead_of_hanging():
    start = time.monotonic()

    with pytest.raises(PdfTableTimeoutError):
        extract_pdf_tables(_SlowFindTablesPage(), timeout=0.2)

    elapsed = time.monotonic() - start

    assert elapsed < 2, (
        f"took {elapsed}s - extract_pdf_tables must give up after the "
        "timeout, not wait for the slow call to finish"
    )


def test_convert_pdf_to_markdown_raises_when_table_detection_times_out(
    tmp_path, monkeypatch
):
    pdf_path = tmp_path / "sample.pdf"
    _make_text_pdf(pdf_path, ["Hello from PDF"])

    def always_times_out(page, timeout=anonymize.PDF_TABLE_TIMEOUT_SECONDS):
        raise PdfTableTimeoutError("table detection timed out after 0.2s")

    monkeypatch.setattr(anonymize, "extract_pdf_tables", always_times_out)

    with pytest.raises(PdfTableTimeoutError):
        convert_pdf_to_markdown(pdf_path)


def _tesseract_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _tesseract_available(), reason="Tesseract OCR not installed"
)
def test_convert_pdf_to_markdown_ocrs_scanned_page(tmp_path):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (600, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 80), "SCANNED TEXT", fill="black")

    image_path = tmp_path / "scan.png"
    image.save(image_path)

    document = fitz.open()
    page = document.new_page()
    page.insert_image(fitz.Rect(0, 0, 600, 200), filename=str(image_path))

    pdf_path = tmp_path / "scan.pdf"
    document.save(pdf_path)
    document.close()

    markdown = convert_pdf_to_markdown(pdf_path)

    assert "SCANNED" in markdown.upper()
