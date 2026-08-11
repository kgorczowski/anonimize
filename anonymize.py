#!/usr/bin/env python3

import argparse
import json
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import NamedTuple

# ------------------------------------------------------------
# Supported file types
# ------------------------------------------------------------

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst",
    ".cs", ".csx",
    ".py", ".pyw",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".java", ".kt", ".kts", ".scala",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx",
    ".go", ".rs", ".rb", ".php", ".swift", ".dart",
    ".fs", ".fsx", ".vb",
    ".json", ".xml", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".conf", ".env",
    ".sql", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    ".dockerfile",
}

OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx"}


# ------------------------------------------------------------
# Replacement map
# ------------------------------------------------------------

def load_replacements(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        replacements = json.load(f)

    if not isinstance(replacements, dict):
        raise ValueError("replacements.json must contain a JSON object.")

    # Longer strings first. This prevents a shorter replacement
    # from being applied before a more specific one.
    return dict(
        sorted(
            replacements.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        )
    )


def anonymize_text(text: str, replacements: dict) -> str:
    if not replacements:
        return text

    pattern = re.compile(
        "|".join(re.escape(original) for original in replacements)
    )

    return pattern.sub(
        lambda match: replacements[match.group(0)],
        text,
    )


# ------------------------------------------------------------
# PII checksum validators
# ------------------------------------------------------------

def validate_pesel(number: str) -> bool:
    if not re.fullmatch(r"\d{11}", number):
        return False

    weights = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
    checksum = sum(
        int(digit) * weight
        for digit, weight in zip(number, weights)
    )
    check_digit = (10 - checksum % 10) % 10

    return check_digit == int(number[10])


def validate_nip(number: str) -> bool:
    if not re.fullmatch(r"\d{10}", number):
        return False

    weights = (6, 5, 7, 2, 3, 4, 5, 6, 7)
    checksum = sum(
        int(digit) * weight
        for digit, weight in zip(number, weights)
    )
    check_digit = checksum % 11

    if check_digit == 10:
        return False

    return check_digit == int(number[9])


def validate_iban(code: str) -> bool:
    code = code.replace(" ", "").upper()

    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", code):
        return False

    rearranged = code[4:] + code[:4]

    try:
        digits = "".join(str(int(char, 36)) for char in rearranged)
    except ValueError:
        return False

    return int(digits) % 97 == 1


def validate_luhn(number: str) -> bool:
    if not re.fullmatch(r"\d{13,19}", number):
        return False

    total = 0

    for index, digit in enumerate(reversed(number)):
        value = int(digit)

        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9

        total += value

    return total % 10 == 0


# ------------------------------------------------------------
# PII detection
# ------------------------------------------------------------

EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+48[\s-]?)?\d{3}[\s-]?\d{3}[\s-]?\d{3}(?!\d)"
)

IBAN_PATTERN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")

CARD_PATTERN = re.compile(
    r"(?<!\d)(?:\d{4}[ -]?){3}\d{4}(?!\d)|(?<!\d)\d{13,19}(?!\d)"
)

PESEL_PATTERN = re.compile(r"(?<!\d)\d{11}(?!\d)")

NIP_PATTERN = re.compile(r"(?<!\d)\d{10}(?!\d)")

IPV4_PATTERN = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)

PII_PATTERNS = (
    ("EMAIL", EMAIL_PATTERN, None),
    ("IP", IPV4_PATTERN, None),
    ("IBAN", IBAN_PATTERN, validate_iban),
    (
        "CARD",
        CARD_PATTERN,
        lambda raw: validate_luhn(re.sub(r"[ -]", "", raw)),
    ),
    ("PESEL", PESEL_PATTERN, validate_pesel),
    ("NIP", NIP_PATTERN, validate_nip),
    ("PHONE", PHONE_PATTERN, None),
)


def redact_pii(text: str) -> tuple:
    total = 0

    for label, pattern, validator in PII_PATTERNS:
        def replace(match, label=label, validator=validator):
            nonlocal total

            if validator is not None and not validator(match.group(0)):
                return match.group(0)

            total += 1
            return f"[{label}]"

        text = pattern.sub(replace, text)

    return text, total


# ------------------------------------------------------------
# Office -> Markdown
# ------------------------------------------------------------

def convert_docx_to_markdown(source: Path) -> str:
    try:
        from docx import Document
    except ImportError:
        raise RuntimeError(
            "Missing python-docx. Install it with: pip install python-docx"
        )

    document = Document(source)
    result = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()

        if not text:
            result.append("")
            continue

        style = paragraph.style.name.lower()

        if "heading 1" in style:
            result.append(f"# {text}")
        elif "heading 2" in style:
            result.append(f"## {text}")
        elif "heading 3" in style:
            result.append(f"### {text}")
        elif "heading 4" in style:
            result.append(f"#### {text}")
        elif "list bullet" in style:
            result.append(f"- {text}")
        elif "list number" in style:
            result.append(f"1. {text}")
        else:
            result.append(text)

    for table in document.tables:
        result.append("")
        rows = []

        for row in table.rows:
            rows.append([
                cell.text.replace("\n", " ").strip()
                for cell in row.cells
            ])

        if rows:
            result.append("| " + " | ".join(rows[0]) + " |")
            result.append("| " + " | ".join("---" for _ in rows[0]) + " |")

            for row in rows[1:]:
                result.append("| " + " | ".join(row) + " |")

    return "\n".join(result)


def convert_xlsx_to_markdown(source: Path) -> str:
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise RuntimeError(
            "Missing openpyxl. Install it with: pip install openpyxl"
        )

    workbook = load_workbook(source, data_only=True)
    result = []

    for worksheet in workbook.worksheets:
        result.append(f"# {worksheet.title}")
        result.append("")

        rows = list(worksheet.iter_rows(values_only=True))

        while rows and all(value is None for value in rows[-1]):
            rows.pop()

        if not rows:
            continue

        max_columns = max(len(row) for row in rows)

        while max_columns > 0:
            if any(
                len(row) >= max_columns
                and row[max_columns - 1] is not None
                for row in rows
            ):
                break
            max_columns -= 1

        rows = [list(row[:max_columns]) for row in rows]

        def value_to_string(value):
            if value is None:
                return ""
            return (
                str(value)
                .replace("\n", " ")
                .replace("|", r"\|")
            )

        rows = [
            [value_to_string(value) for value in row]
            for row in rows
        ]

        if rows:
            result.append("| " + " | ".join(rows[0]) + " |")
            result.append("| " + " | ".join("---" for _ in rows[0]) + " |")

            for row in rows[1:]:
                result.append("| " + " | ".join(row) + " |")

            result.append("")

    return "\n".join(result)


def convert_pptx_to_markdown(source: Path) -> str:
    try:
        from pptx import Presentation
    except ImportError:
        raise RuntimeError(
            "Missing python-pptx. Install it with: pip install python-pptx"
        )

    presentation = Presentation(source)
    result = []

    for slide_number, slide in enumerate(presentation.slides, start=1):
        result.append(f"# Slide {slide_number}")
        result.append("")

        for shape in slide.shapes:
            if not hasattr(shape, "text"):
                continue

            text = shape.text.strip()

            if text:
                result.append(text)
                result.append("")

    return "\n".join(result)


def extract_pdf_tables(page) -> list:
    if not hasattr(page, "find_tables"):
        return []

    def cell_to_string(value):
        if value is None:
            return ""
        return str(value).replace("\n", " ").replace("|", r"\|")

    tables = []

    for table in page.find_tables().tables:
        rows = table.extract()

        if not rows:
            continue

        header = [cell_to_string(cell) for cell in rows[0]]
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]

        for row in rows[1:]:
            lines.append(
                "| "
                + " | ".join(cell_to_string(cell) for cell in row)
                + " |"
            )

        tables.append(lines)

    return tables


def ocr_page(page) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise RuntimeError(
            "Missing OCR dependencies. Install them with: "
            "pip install pytesseract Pillow"
        )

    pixmap = page.get_pixmap(dpi=300)
    image = Image.frombytes(
        "RGB", (pixmap.width, pixmap.height), pixmap.samples
    )

    try:
        return pytesseract.image_to_string(image).strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract OCR engine not found. Install it and make sure "
            "it is on PATH. On Windows: "
            "winget install UB-Mannheim.TesseractOCR"
        ) from exc


def convert_pdf_to_markdown(source: Path) -> str:
    try:
        import pymupdf as fitz
    except ImportError:
        raise RuntimeError(
            "Missing pymupdf. Install it with: pip install pymupdf"
        )

    document = fitz.open(source)
    result = []

    try:
        for page_number, page in enumerate(document, start=1):
            result.append(f"# Page {page_number}")
            result.append("")

            text = page.get_text().strip()

            if len(text) < 10:
                text = ocr_page(page)

            if text:
                result.append(text)
                result.append("")

            for table_lines in extract_pdf_tables(page):
                result.extend(table_lines)
                result.append("")
    finally:
        document.close()

    return "\n".join(result)


# ------------------------------------------------------------
# File classification
# ------------------------------------------------------------

def is_supported_for_text_processing(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def is_office_file(path: Path) -> bool:
    return path.suffix.lower() in OFFICE_EXTENSIONS


# ------------------------------------------------------------
# Archive handling
# ------------------------------------------------------------

ARCHIVE_SUFFIXES = (
    (".tar.gz", "tar"),
    (".tar.bz2", "tar"),
    (".tar.xz", "tar"),
    (".tgz", "tar"),
    (".tbz2", "tar"),
    (".txz", "tar"),
    (".tar", "tar"),
    (".zip", "zip"),
    (".7z", "7z"),
    (".rar", "rar"),
)


def classify_archive(path: Path):
    name = path.name.lower()

    for suffix, kind in ARCHIVE_SUFFIXES:
        if name.endswith(suffix):
            return kind

    return None


def archive_stem(path: Path) -> str:
    name = path.name

    for suffix, _kind in ARCHIVE_SUFFIXES:
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]

    return path.stem


def is_archive_file(path: Path) -> bool:
    return classify_archive(path) is not None


def extract_archive(source: Path, dest_dir: Path) -> None:
    kind = classify_archive(source)

    if kind == "zip":
        import zipfile

        with zipfile.ZipFile(source) as archive:
            archive.extractall(dest_dir)
        return

    if kind == "tar":
        import tarfile

        with tarfile.open(source) as archive:
            try:
                archive.extractall(dest_dir, filter="data")
            except TypeError:
                # Python < 3.12 does not support the `filter` argument.
                archive.extractall(dest_dir)
        return

    if kind == "7z":
        try:
            import py7zr
        except ImportError:
            raise RuntimeError(
                "Missing py7zr. Install it with: pip install py7zr"
            )

        with py7zr.SevenZipFile(source, mode="r") as archive:
            archive.extractall(dest_dir)
        return

    if kind == "rar":
        try:
            import rarfile
        except ImportError:
            raise RuntimeError(
                "Missing rarfile. Install it with: pip install rarfile"
            )

        try:
            with rarfile.RarFile(source) as archive:
                archive.extractall(dest_dir)
        except rarfile.NeedFirstVolume:
            raise
        except rarfile.Error as exc:
            raise RuntimeError(
                "Cannot extract RAR archive. This usually means the "
                "'unrar' tool is not installed and on PATH, or the "
                f"archive is corrupt/password-protected: {exc}"
            ) from exc
        return

    raise ValueError(f"Not a supported archive: {source}")


# ------------------------------------------------------------
# Progress bar
# ------------------------------------------------------------

def format_duration(seconds: float) -> str:
    if seconds < 1:
        return "<1s"

    seconds = int(seconds)

    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"

    if minutes:
        return f"{minutes}m {seconds:02d}s"

    return f"{seconds}s"


class ProgressBar:
    def __init__(self, total: int, width: int = 40):
        self.total = total
        self.width = width
        self.current = 0
        self.start_time = time.monotonic()

    def update(self, current: int, current_file: Path):
        self.current = current

        elapsed = time.monotonic() - self.start_time

        if self.current > 0:
            rate = self.current / elapsed
            remaining = (self.total - self.current) / rate
        else:
            remaining = 0

        percent = (
            100.0
            if self.total == 0
            else self.current / self.total * 100
        )

        filled = (
            self.width
            if self.total == 0
            else int(self.width * self.current / self.total)
        )

        bar = "█" * filled + "░" * (self.width - filled)

        filename = str(current_file)

        # Keep the terminal line reasonably compact.
        terminal_width = shutil.get_terminal_size(
            fallback=(120, 20)
        ).columns

        prefix = (
            f"\r[{bar}] "
            f"{percent:6.2f}% "
            f"({self.current}/{self.total}) "
            f"ETA {format_duration(remaining)} "
        )

        available = max(20, terminal_width - len(prefix) - 1)
        filename = filename[-available:]

        print(
            prefix + filename,
            end="",
            flush=True,
        )

    def finish(self):
        print()


# ------------------------------------------------------------
# Scan
# ------------------------------------------------------------

MAX_ARCHIVE_DEPTH = 10


class ScanEntry(NamedTuple):
    source: Path
    relative_destination: Path


def scan_files(
    source_dir: Path,
    output_root: Path,
    temp_dirs: list,
    extraction_errors: list,
    relative_root: Path = None,
    depth: int = 0,
):
    """
    Recursively find all files under source_dir, excluding the output
    directory. Archives are extracted into fresh temp directories (added
    to temp_dirs for the caller to clean up) and their contents are
    folded into the result with a relative_destination that mirrors the
    archive's location, e.g. bundle.zip -> bundle/<path inside zip>.

    An archive that fails to extract, or that would exceed
    MAX_ARCHIVE_DEPTH, is returned as-is (to be copied unchanged by the
    normal file-processing path) instead of raising. Extraction failures
    (but not depth-limit fallbacks, which are not errors) are appended to
    extraction_errors so the caller can fold them into its own error
    count.
    """

    if relative_root is None:
        relative_root = Path(".")

    entries = []

    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue

        try:
            path.relative_to(output_root)
            continue
        except ValueError:
            pass

        relative_path = relative_root / path.relative_to(source_dir)

        if is_archive_file(path):
            if depth >= MAX_ARCHIVE_DEPTH:
                entries.append(ScanEntry(path, relative_path))
                continue

            extract_dir = Path(tempfile.mkdtemp(prefix="anonymize_"))

            try:
                extract_archive(path, extract_dir)
            except Exception as exc:
                shutil.rmtree(extract_dir, ignore_errors=True)
                print(
                    f"ERROR: cannot extract {path}: {exc}",
                    file=sys.stderr,
                )
                extraction_errors.append(path)
                entries.append(ScanEntry(path, relative_path))
                continue

            temp_dirs.append(extract_dir)
            nested_root = relative_path.with_name(archive_stem(path))

            entries.extend(
                scan_files(
                    extract_dir,
                    output_root,
                    temp_dirs,
                    extraction_errors,
                    relative_root=nested_root,
                    depth=depth + 1,
                )
            )
            continue

        entries.append(ScanEntry(path, relative_path))

    return entries


# ------------------------------------------------------------
# Process one file
# ------------------------------------------------------------

def process_file(
    source: Path,
    destination: Path,
    replacements: dict,
):
    suffix = source.suffix.lower()

    # Text/code files
    if suffix in TEXT_EXTENSIONS:
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Keep binary/non-UTF8 files untouched.
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            return "copied-non-utf8", 0

        text = anonymize_text(text, replacements)
        text, pii_count = redact_pii(text)

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")

        return "anonymized", pii_count

    # DOCX -> MD
    if suffix == ".docx":
        markdown = convert_docx_to_markdown(source)
        markdown = anonymize_text(markdown, replacements)
        markdown, pii_count = redact_pii(markdown)

        destination = destination.with_suffix(".md")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(markdown, encoding="utf-8")

        return "office", pii_count

    # XLSX -> MD
    if suffix == ".xlsx":
        markdown = convert_xlsx_to_markdown(source)
        markdown = anonymize_text(markdown, replacements)
        markdown, pii_count = redact_pii(markdown)

        destination = destination.with_suffix(".md")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(markdown, encoding="utf-8")

        return "office", pii_count

    # PPTX -> MD
    if suffix == ".pptx":
        markdown = convert_pptx_to_markdown(source)
        markdown = anonymize_text(markdown, replacements)
        markdown, pii_count = redact_pii(markdown)

        destination = destination.with_suffix(".md")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(markdown, encoding="utf-8")

        return "office", pii_count

    # PDF -> MD
    if suffix == ".pdf":
        markdown = convert_pdf_to_markdown(source)
        markdown = anonymize_text(markdown, replacements)
        markdown, pii_count = redact_pii(markdown)

        destination = destination.with_suffix(".md")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(markdown, encoding="utf-8")

        return "pdf", pii_count

    # Unknown/binary file:
    # Copy it unchanged.
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)

    return "copied", 0


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Recursively anonymize text/code files and convert "
            "DOCX/XLSX/PPTX files to Markdown."
        )
    )

    parser.add_argument(
        "source",
        help="Source directory",
    )

    parser.add_argument(
        "replacements",
        help="JSON file containing replacement mappings",
    )

    parser.add_argument(
        "--output",
        help=(
            "Optional output directory. "
            "Default: <source-parent>/anonimized/<source-name>"
        ),
    )

    args = parser.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    replacements_file = Path(args.replacements).expanduser().resolve()

    if not source_dir.exists():
        print(f"ERROR: source directory does not exist: {source_dir}")
        sys.exit(1)

    if not source_dir.is_dir():
        print(f"ERROR: source path is not a directory: {source_dir}")
        sys.exit(1)

    if not replacements_file.exists():
        print(f"ERROR: replacement file does not exist: {replacements_file}")
        sys.exit(1)

    try:
        replacements = load_replacements(replacements_file)
    except Exception as exc:
        print(f"ERROR: cannot load replacement map: {exc}")
        sys.exit(1)

    if args.output:
        output_root = Path(args.output).expanduser().resolve()
    else:
        output_root = (
            source_dir.parent
            / "anonimized"
            / source_dir.name
        )

    # --------------------------------------------------------
    # PASS 1 - scan
    # --------------------------------------------------------

    print()
    print("==============================================")
    print(" ANONYMIZATION")
    print("==============================================")
    print()
    print(f"Source       : {source_dir}")
    print(f"Output       : {output_root}")
    print(f"Replacements : {len(replacements)}")
    print()
    print("Scanning files...")

    scan_start = time.monotonic()

    temp_dirs = []
    extraction_errors = []

    try:
        files = scan_files(
            source_dir,
            output_root,
            temp_dirs,
            extraction_errors,
        )

        archives_extracted = len(temp_dirs)

        scan_duration = time.monotonic() - scan_start

        print(
            f"Found {len(files):,} files "
            f"in {format_duration(scan_duration)}."
        )
        print()

        if not files:
            print("Nothing to process.")
            return

        # --------------------------------------------------------
        # PASS 2 - processing
        # --------------------------------------------------------

        output_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        progress = ProgressBar(
            total=len(files)
        )

        processed = 0
        anonymized = 0
        office_converted = 0
        pdf_converted = 0
        copied = 0
        errors = 0
        pii_redacted = 0

        processing_start = time.monotonic()

        for entry in files:
            destination = output_root / entry.relative_destination

            try:
                result, pii_count = process_file(
                    entry.source,
                    destination,
                    replacements,
                )

                pii_redacted += pii_count

                if result == "anonymized":
                    anonymized += 1
                elif result == "office":
                    office_converted += 1
                elif result == "pdf":
                    pdf_converted += 1
                else:
                    copied += 1

            except Exception as exc:
                errors += 1

                print()
                print(
                    f"ERROR: {entry.source}: {exc}",
                    file=sys.stderr,
                )

            processed += 1

            progress.update(
                processed,
                entry.relative_destination,
            )

        progress.finish()

        duration = time.monotonic() - processing_start

        errors += len(extraction_errors)

        # --------------------------------------------------------
        # Summary
        # --------------------------------------------------------

        print()
        print("==============================================")
        print(" DONE")
        print("==============================================")
        print()
        print(f"Files found       : {len(files):,}")
        print(f"Files processed   : {processed:,}")
        print(f"Archives extracted: {archives_extracted:,}")
        print(f"Text/code         : {anonymized:,}")
        print(f"Office -> Markdown: {office_converted:,}")
        print(f"PDF -> Markdown   : {pdf_converted:,}")
        print(f"Copied unchanged  : {copied:,}")
        print(f"PII fragments     : {pii_redacted:,}")
        print(f"Errors            : {errors:,}")
        print(f"Processing time   : {format_duration(duration)}")
        print()
        print(f"Output directory:")
        print(output_root)
        print()
    finally:
        for temp_dir in temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
