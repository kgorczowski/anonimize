# Anonymize: Archives, PDF-to-Markdown, PII Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `anonymize.py` to extract and process archive files (zip/tar/7z/rar), convert PDFs to Markdown (with OCR fallback for scans), and automatically redact common PII (email, phone, PESEL, NIP, IBAN, card numbers, IPv4) in addition to the existing dictionary-based anonymization.

**Architecture:** Everything stays in the single `anonymize.py` file (explicit user decision — no module split). The existing two-pass scan/process pipeline is preserved: the scan pass is extended to recursively extract archives into temp directories and fold their contents into the file list (with corrected destination paths); the process pass gains a `.pdf` branch and a PII-redaction step applied after the existing dictionary anonymization for every text/code/office/pdf file.

**Tech Stack:** Python 3, stdlib `zipfile`/`tarfile`, `py7zr`, `rarfile` (+ system `unrar`), `pymupdf` (fitz), `pytesseract` + `Pillow` (+ system Tesseract OCR), `pytest` for tests.

## Global Constraints

- All new code lives in `anonymize.py` — no new source modules (spec: single-file decision).
- Archives are extracted and left as a folder in the output; never re-packed (spec: "poza zakresem: ponowne pakowanie").
- Archive recursion depth is capped at 10, hardcoded — no new CLI flag (spec: "poza zakresem: nowe flagi CLI dla głębokości rekursji").
- PII detection is always on — no CLI flag to disable it (spec: "poza zakresem: flaga CLI do włączania/wyłączania detekcji PII").
- PII placeholders are generic per-category tags (`[EMAIL]`, `[PHONE]`, `[PESEL]`, `[NIP]`, `[IBAN]`, `[CARD]`, `[IP]`), never numbered/instance-specific (spec: "poza zakresem: numerowane placeholdery").
- PESEL, NIP, IBAN, and CARD matches must pass their checksum (PESEL algorithm, NIP algorithm, mod-97, Luhn) before being redacted, to avoid flagging arbitrary digit runs.
- PII redaction runs after dictionary-based `anonymize_text`, on the same file set that already gets dictionary anonymization (text/code files, and the Markdown output of docx/xlsx/pptx/pdf conversion) — never on binary/copied-unchanged files.
- A missing system-level dependency (`unrar` for RAR, Tesseract for OCR) degrades gracefully: the archive/PDF operation fails with a clear message and the run continues (archive copied unchanged; PDF conversion error is caught like any other per-file error) — it must never crash the whole run.
- Any per-file or per-archive error is caught, logged to stderr, counted in the `errors` summary counter, and the run continues — this existing behavior must not regress.

---

## File Structure

- **Modify:** `anonymize.py` — all new functions and the scan/process pipeline changes.
- **Create:** `requirements.txt` — pip dependencies (grows incrementally across tasks).
- **Create:** `tests/conftest.py` — makes `anonymize.py` importable from the `tests/` package.
- **Create:** `tests/test_smoke.py` — one trivial test proving the harness works.
- **Create:** `tests/test_pii.py` — checksum validators + `redact_pii`.
- **Create:** `tests/test_archives.py` — `extract_archive`, `classify_archive`, `archive_stem`, `scan_files`.
- **Create:** `tests/test_pdf.py` — `convert_pdf_to_markdown`, OCR fallback.
- **Create:** `tests/test_integration.py` — end-to-end run through a mixed source tree.

**A note on line references below:** every "Find" instruction is followed by the exact code block to search for — that block is the real anchor. Parenthetical `anonymize.py:NNN` references are line numbers from the original, pre-Task-1 file, given only for quick orientation. They drift as earlier tasks insert code (e.g. by the time Task 4 touches `process_file`, Tasks 2-3 have already added ~120 lines above it) — always locate code by matching the shown text, never by jumping to a stale line number.

---

## Task 1: Test infrastructure

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`
- Create: `requirements.txt`

**Interfaces:**
- Produces: a working `pytest` setup where `tests/*.py` can do `from anonymize import <name>`.

- [ ] **Step 1: Create `requirements.txt`**

```
python-docx
openpyxl
python-pptx
pytest
```

- [ ] **Step 2: Create `tests/conftest.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 3: Write the smoke test**

```python
from anonymize import format_duration


def test_format_duration_seconds():
    assert format_duration(30) == "30s"
```

- [ ] **Step 4: Install dependencies and run the test**

Run: `pip install -r requirements.txt`
Then run: `pytest tests/test_smoke.py -v`
Expected: PASS. If it fails with `ModuleNotFoundError: No module named 'anonymize'`, check that `tests/conftest.py` was picked up (run `pytest` from the project root, not from inside `tests/`).

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/conftest.py tests/test_smoke.py
git commit -m "test: add pytest infrastructure"
```

---

## Task 2: PII checksum validators

**Files:**
- Modify: `anonymize.py` (new section after `anonymize_text`, before the "Office -> Markdown" section)
- Test: `tests/test_pii.py`

**Interfaces:**
- Produces: `validate_pesel(number: str) -> bool`, `validate_nip(number: str) -> bool`, `validate_iban(code: str) -> bool`, `validate_luhn(number: str) -> bool`. All four take a string of the raw matched characters (digits only for PESEL/NIP/Luhn; may contain letters for IBAN) and return whether the checksum is valid. Non-matching length/shape input returns `False` rather than raising.

- [ ] **Step 1: Write the failing tests**

```python
from anonymize import validate_pesel, validate_nip, validate_iban, validate_luhn


def test_validate_pesel_accepts_valid_number():
    assert validate_pesel("02031554796") is True


def test_validate_pesel_rejects_bad_checksum():
    assert validate_pesel("02031554797") is False


def test_validate_pesel_rejects_wrong_length():
    assert validate_pesel("123") is False


def test_validate_nip_accepts_valid_number():
    assert validate_nip("2134567890") is True


def test_validate_nip_rejects_bad_checksum():
    assert validate_nip("2134567891") is False


def test_validate_iban_accepts_valid_polish_iban():
    assert validate_iban("PL61109010140000071219812874") is True


def test_validate_iban_rejects_bad_checksum():
    assert validate_iban("PL61109010140000071219812875") is False


def test_validate_luhn_accepts_valid_card_number():
    assert validate_luhn("4111111111111111") is True


def test_validate_luhn_rejects_bad_checksum():
    assert validate_luhn("4111111111111112") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pii.py -v`
Expected: FAIL with `ImportError: cannot import name 'validate_pesel'` (the functions don't exist yet).

- [ ] **Step 3: Add the validators to `anonymize.py`**

Insert this new section after `anonymize_text` (after the existing `# ------------------------------------------------------------ / # Replacement map / # ------------------------------------------------------------` block ends, i.e. right after the closing of `anonymize_text`) and before the `# Office -> Markdown` section:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pii.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add anonymize.py tests/test_pii.py
git commit -m "feat: add PII checksum validators"
```

---

## Task 3: PII regex detection (`redact_pii`)

**Files:**
- Modify: `anonymize.py` (directly below the validators added in Task 2)
- Test: `tests/test_pii.py`

**Interfaces:**
- Consumes: `validate_pesel`, `validate_nip`, `validate_iban`, `validate_luhn` from Task 2.
- Produces: `redact_pii(text: str) -> tuple[str, int]` — returns `(redacted_text, count_of_redactions)`.

- [ ] **Step 1: Write the failing tests**

```python
from anonymize import redact_pii


def test_redact_pii_masks_email():
    text, count = redact_pii("Contact: jan.kowalski@example.com please")
    assert text == "Contact: [EMAIL] please"
    assert count == 1


def test_redact_pii_masks_valid_pesel_only():
    text, count = redact_pii("PESEL: 02031554796, other: 02031554797")
    assert text == "PESEL: [PESEL], other: 02031554797"
    assert count == 1


def test_redact_pii_masks_valid_nip():
    text, count = redact_pii("NIP 2134567890 na fakturze")
    assert text == "NIP [NIP] na fakturze"
    assert count == 1


def test_redact_pii_masks_iban():
    text, count = redact_pii("IBAN: PL61109010140000071219812874.")
    assert text == "IBAN: [IBAN]."
    assert count == 1


def test_redact_pii_masks_card_number_with_spaces():
    text, count = redact_pii("Card 4111 1111 1111 1111 exp 12/30")
    assert text == "Card [CARD] exp 12/30"
    assert count == 1


def test_redact_pii_masks_ipv4_address():
    text, count = redact_pii("Server at 192.168.1.10 responded")
    assert text == "Server at [IP] responded"
    assert count == 1


def test_redact_pii_masks_phone_number():
    text, count = redact_pii("Zadzwon: +48 123 456 789 dzisiaj")
    assert text == "Zadzwon: [PHONE] dzisiaj"
    assert count == 1


def test_redact_pii_returns_zero_for_clean_text():
    text, count = redact_pii("Nothing sensitive here.")
    assert text == "Nothing sensitive here."
    assert count == 0


def test_redact_pii_counts_multiple_matches():
    text, count = redact_pii("a@b.com and c@d.com")
    assert text == "[EMAIL] and [EMAIL]"
    assert count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pii.py -v`
Expected: FAIL with `ImportError: cannot import name 'redact_pii'`.

- [ ] **Step 3: Add patterns and `redact_pii` to `anonymize.py`**

Insert directly after the `validate_luhn` function from Task 2:

```python
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
```

Note: `CARD_PATTERN` intentionally matches only 16-digit numbers grouped in 4s (with optional space/dash) or a plain contiguous run of 13-19 digits — it does not attempt every card network's exact grouping (e.g. Amex's 4-6-5). This mirrors the spec's accepted heuristic-detection limitation.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pii.py -v`
Expected: PASS (18 tests total: 9 from Task 2 + 9 from this task).

- [ ] **Step 5: Commit**

```bash
git add anonymize.py tests/test_pii.py
git commit -m "feat: add regex-based PII detection and redaction"
```

---

## Task 4: Wire PII redaction into the existing pipeline

**Files:**
- Modify: `anonymize.py` — `process_file` function and `main()`'s processing loop + summary print block.
- Test: `tests/test_integration.py` (new file, first test)

**Interfaces:**
- Consumes: `redact_pii` from Task 3.
- Produces: `process_file(source, destination, replacements) -> tuple[str, int]` (status label, PII redaction count) — **return type changes from `str` to `tuple[str, int]`**. Every caller of `process_file` must be updated in this task.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration.py -v`
Expected: FAIL — either an assertion error (status/text is fine but `pii_count` unpacking fails because `process_file` still returns a plain string) or a `ValueError: too many values to unpack`.

- [ ] **Step 3: Update `process_file` in `anonymize.py`**

Replace the whole `process_file` function body (currently `anonymize.py:347-409`, the text/docx/xlsx/pptx/fallback branches) with:

```python
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

    # Unknown/binary file:
    # Copy it unchanged.
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)

    return "copied", 0
```

(This is the same structure as before, with a `redact_pii` call added after every `anonymize_text` call, and every `return` updated to a 2-tuple. The PDF branch is intentionally not added yet — that's Task 9.)

- [ ] **Step 4: Update the processing loop in `main()`**

Find this block (currently `anonymize.py:529-561`):

```python
    for source in files:
        relative_path = source.relative_to(source_dir)
        destination = output_root / relative_path

        try:
            result = process_file(
                source,
                destination,
                replacements,
            )

            if result == "anonymized":
                anonymized += 1
            elif result == "office":
                office_converted += 1
            else:
                copied += 1

        except Exception as exc:
            errors += 1

            print()
            print(
                f"ERROR: {source}: {exc}",
                file=sys.stderr,
            )

        processed += 1

        progress.update(
            processed,
            source.relative_to(source_dir),
        )
```

Replace it with:

```python
    for source in files:
        relative_path = source.relative_to(source_dir)
        destination = output_root / relative_path

        try:
            result, pii_count = process_file(
                source,
                destination,
                replacements,
            )

            pii_redacted += pii_count

            if result == "anonymized":
                anonymized += 1
            elif result == "office":
                office_converted += 1
            else:
                copied += 1

        except Exception as exc:
            errors += 1

            print()
            print(
                f"ERROR: {source}: {exc}",
                file=sys.stderr,
            )

        processed += 1

        progress.update(
            processed,
            source.relative_to(source_dir),
        )
```

- [ ] **Step 5: Add the `pii_redacted` counter and summary line**

Find the counter initialization (currently `anonymize.py:521-525`):

```python
    processed = 0
    anonymized = 0
    office_converted = 0
    copied = 0
    errors = 0
```

Replace with:

```python
    processed = 0
    anonymized = 0
    office_converted = 0
    copied = 0
    errors = 0
    pii_redacted = 0
```

Find the summary print block (currently `anonymize.py:576-582`):

```python
    print(f"Files found       : {len(files):,}")
    print(f"Files processed   : {processed:,}")
    print(f"Text/code         : {anonymized:,}")
    print(f"Office -> Markdown: {office_converted:,}")
    print(f"Copied unchanged  : {copied:,}")
    print(f"Errors            : {errors:,}")
    print(f"Processing time   : {format_duration(duration)}")
```

Replace with:

```python
    print(f"Files found       : {len(files):,}")
    print(f"Files processed   : {processed:,}")
    print(f"Text/code         : {anonymized:,}")
    print(f"Office -> Markdown: {office_converted:,}")
    print(f"Copied unchanged  : {copied:,}")
    print(f"PII fragments     : {pii_redacted:,}")
    print(f"Errors            : {errors:,}")
    print(f"Processing time   : {format_duration(duration)}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/ -v`
Expected: PASS (all tests from Tasks 1-4).

- [ ] **Step 7: Manual smoke check of the CLI**

```bash
mkdir -p /tmp/anonymize-smoke/src
echo "VM contact jan@example.com" > /tmp/anonymize-smoke/src/note.txt
python anonymize.py /tmp/anonymize-smoke/src replacements.json --output /tmp/anonymize-smoke/out
cat /tmp/anonymize-smoke/out/note.txt
```

Expected output file content: `Company1 contact [EMAIL]` and a summary block that includes a `PII fragments` line.

- [ ] **Step 8: Commit**

```bash
git add anonymize.py tests/test_integration.py
git commit -m "feat: wire PII redaction into the processing pipeline"
```

---

## Task 5: Archive extraction (`extract_archive`, `classify_archive`, `archive_stem`)

**Files:**
- Modify: `anonymize.py` (new section after "File classification", before "Progress bar")
- Modify: `requirements.txt`
- Test: `tests/test_archives.py`

**Interfaces:**
- Produces: `classify_archive(path: Path) -> str | None` (one of `"zip"`, `"tar"`, `"7z"`, `"rar"`, or `None`), `archive_stem(path: Path) -> str` (filename with the archive extension, including multi-part ones like `.tar.gz`, stripped), `is_archive_file(path: Path) -> bool`, `extract_archive(source: Path, dest_dir: Path) -> None` (raises `RuntimeError` or the underlying library's exception on failure — does not catch/hide errors, that's the caller's job).

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_archives.py -v`
Expected: FAIL with `ImportError: cannot import name 'classify_archive'`.

- [ ] **Step 3: Add dependencies to `requirements.txt`**

Append to `requirements.txt`:

```
py7zr
rarfile
```

Run: `pip install -r requirements.txt`

- [ ] **Step 4: Add the archive functions to `anonymize.py`**

Insert this new section after the `is_office_file` function (end of the existing "File classification" section, `anonymize.py:227-228`) and before the "Progress bar" section:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_archives.py -v`
Expected: PASS. The 7z test runs for real (py7zr can both write and read). The rar test only checks that a corrupt file raises — building a real `.rar` fixture isn't possible without a proprietary RAR compressor, so this is the correct-scoped test for that path. If `rarfile` can't find `unrar` on this machine, `rarfile.Error` (or a `rarfile`-specific subclass) is still raised for the corrupt input, so the test passes either way.

- [ ] **Step 6: Commit**

```bash
git add anonymize.py requirements.txt tests/test_archives.py
git commit -m "feat: add archive detection and extraction"
```

---

## Task 6: Archive-aware scanning

**Files:**
- Modify: `anonymize.py` — `scan_files` function and its call site / consumers in `main()`.
- Test: `tests/test_archives.py`

**Interfaces:**
- Consumes: `is_archive_file`, `extract_archive`, `archive_stem` from Task 5.
- Produces: `ScanEntry` (a `NamedTuple` with fields `source: Path`, `relative_destination: Path`); `scan_files(source_dir: Path, output_root: Path, temp_dirs: list, relative_root: Path = None, depth: int = 0) -> list[ScanEntry]` — **signature and return type both change**: it now takes a `temp_dirs` list (the caller owns cleanup) and returns `ScanEntry` records instead of bare `Path`s.

- [ ] **Step 1: Write the failing tests**

```python
import zipfile

from anonymize import scan_files, MAX_ARCHIVE_DEPTH


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
```

Add `from pathlib import Path` to the top of `tests/test_archives.py` if not already present from Task 5.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_archives.py -v`
Expected: FAIL with `ImportError: cannot import name 'MAX_ARCHIVE_DEPTH'` (or a `TypeError` on `scan_files`'s current signature, which only takes `source_dir, output_root`).

- [ ] **Step 3: Replace `scan_files` in `anonymize.py`**

Add `NamedTuple` to the imports at the top of the file. Find:

```python
from pathlib import Path
```

Replace with:

```python
from pathlib import Path
from typing import NamedTuple
```

Then replace the entire `scan_files` function (currently `anonymize.py:316-340`) with:

```python
MAX_ARCHIVE_DEPTH = 10


class ScanEntry(NamedTuple):
    source: Path
    relative_destination: Path


def scan_files(
    source_dir: Path,
    output_root: Path,
    temp_dirs: list,
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
    normal file-processing path) instead of raising.
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
                entries.append(ScanEntry(path, relative_path))
                continue

            temp_dirs.append(extract_dir)
            nested_root = relative_path.with_name(archive_stem(path))

            entries.extend(
                scan_files(
                    extract_dir,
                    output_root,
                    temp_dirs,
                    relative_root=nested_root,
                    depth=depth + 1,
                )
            )
            continue

        entries.append(ScanEntry(path, relative_path))

    return entries
```

Add `import tempfile` to the top-of-file imports. Find:

```python
import shutil
import sys
import time
```

Replace with:

```python
import shutil
import sys
import tempfile
import time
```

- [ ] **Step 4: Wrap scan + processing in try/finally, and switch to `ScanEntry`**

This step replaces the rest of `main()` from the `scan_start = time.monotonic()` line (near `anonymize.py:489` in the original file — line numbers have shifted slightly after Task 4's edits, use the code content below to locate it, not the number) through the final `print()` at the end of the function — i.e. everything from just before the `scan_files(...)` call to the end of the function body. Find that whole region (as it stands after Task 4's edits — loop variable still named `source`, no `temp_dirs`/`archives_extracted` yet):

```python
    scan_start = time.monotonic()

    files = scan_files(
        source_dir,
        output_root,
    )

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
    copied = 0
    errors = 0
    pii_redacted = 0

    processing_start = time.monotonic()

    for source in files:
        relative_path = source.relative_to(source_dir)
        destination = output_root / relative_path

        try:
            result, pii_count = process_file(
                source,
                destination,
                replacements,
            )

            pii_redacted += pii_count

            if result == "anonymized":
                anonymized += 1
            elif result == "office":
                office_converted += 1
            else:
                copied += 1

        except Exception as exc:
            errors += 1

            print()
            print(
                f"ERROR: {source}: {exc}",
                file=sys.stderr,
            )

        processed += 1

        progress.update(
            processed,
            source.relative_to(source_dir),
        )

    progress.finish()

    duration = time.monotonic() - processing_start

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
    print(f"Text/code         : {anonymized:,}")
    print(f"Office -> Markdown: {office_converted:,}")
    print(f"Copied unchanged  : {copied:,}")
    print(f"PII fragments     : {pii_redacted:,}")
    print(f"Errors            : {errors:,}")
    print(f"Processing time   : {format_duration(duration)}")
    print()
    print(f"Output directory:")
    print(output_root)
    print()
```

Replace that entire block with:

```python
    scan_start = time.monotonic()

    temp_dirs = []

    try:
        files = scan_files(
            source_dir,
            output_root,
            temp_dirs,
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
```

Notes on what changed vs. the pre-Task-6 version: `scan_files` now takes `temp_dirs` as a third argument; `archives_extracted = len(temp_dirs)` is new; the loop variable is `entry` (a `ScanEntry`) instead of `source`, so `destination` and the error message use `entry.source`/`entry.relative_destination` instead of `source`/`source.relative_to(source_dir)`; the summary gained an `Archives extracted` line; and everything from `files = scan_files(...)` onward is now inside a `try` whose `finally` cleans up every temp directory created during extraction — including on early `return` (no files found) and on any unhandled exception.

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS. Double check indentation didn't break `main()` by running the manual smoke check from Task 4 Step 7 again, plus a zip-specific check:

```bash
mkdir -p /tmp/anonymize-smoke2/src
cd /tmp/anonymize-smoke2/src && zip bundle.zip -j /dev/null 2>/dev/null; cd -
python -c "
import zipfile
with zipfile.ZipFile('/tmp/anonymize-smoke2/src/bundle.zip', 'w') as z:
    z.writestr('inner.txt', 'VM data jan@example.com')
"
python anonymize.py /tmp/anonymize-smoke2/src replacements.json --output /tmp/anonymize-smoke2/out
cat /tmp/anonymize-smoke2/out/bundle/inner.txt
```

Expected: `/tmp/anonymize-smoke2/out/bundle/inner.txt` exists and contains `Company1 data [EMAIL]`, and the summary shows `Archives extracted: 1`.

- [ ] **Step 6: Commit**

```bash
git add anonymize.py tests/test_archives.py
git commit -m "feat: recursively extract archives during the scan pass"
```

---

## Task 7: PDF -> Markdown conversion (text layer)

**Files:**
- Modify: `anonymize.py` (new function after `convert_pptx_to_markdown`)
- Modify: `requirements.txt`
- Test: `tests/test_pdf.py`

**Interfaces:**
- Produces: `convert_pdf_to_markdown(source: Path) -> str`.

- [ ] **Step 1: Add dependency**

Append to `requirements.txt`:

```
pymupdf
```

Run: `pip install -r requirements.txt`

- [ ] **Step 2: Write the failing test**

```python
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_pdf.py -v`
Expected: FAIL with `ImportError: cannot import name 'convert_pdf_to_markdown'`.

- [ ] **Step 4: Add `convert_pdf_to_markdown` to `anonymize.py`**

Insert this new function directly after `convert_pptx_to_markdown` (after `anonymize.py:216`, before the "File classification" section):

```python
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


def convert_pdf_to_markdown(source: Path) -> str:
    try:
        import fitz
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
```

Note: `ocr_page` is referenced here but implemented in Task 8. This is intentional — write it as a stub for now so this task's tests (which only exercise pages with a real text layer) pass without needing OCR yet:

```python
def ocr_page(page) -> str:
    raise RuntimeError("OCR fallback not implemented yet")
```

Place this stub directly above `convert_pdf_to_markdown`. Task 8 replaces it with the real implementation.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_pdf.py -v`
Expected: PASS (2 tests). Neither test triggers the `< 10` character fallback since both pages have real text.

- [ ] **Step 6: Commit**

```bash
git add anonymize.py requirements.txt tests/test_pdf.py
git commit -m "feat: add PDF to Markdown text conversion"
```

---

## Task 8: PDF OCR fallback for scanned pages

**Files:**
- Modify: `anonymize.py` — replace the `ocr_page` stub from Task 7.
- Modify: `requirements.txt`
- Test: `tests/test_pdf.py`

**Interfaces:**
- Produces: `ocr_page(page) -> str` (real implementation, replacing the Task 7 stub). `page` is a `fitz.Page`.

- [ ] **Step 1: Add dependencies**

Append to `requirements.txt`:

```
pytesseract
Pillow
```

Run: `pip install -r requirements.txt`

- [ ] **Step 2: Write the failing test**

```python
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
```

- [ ] **Step 3: Run test to verify it fails (or is skipped)**

Run: `pytest tests/test_pdf.py -v`
Expected: FAIL with `RuntimeError: OCR fallback not implemented yet` if Tesseract is installed on this machine, or `SKIPPED` if it isn't. Either outcome is acceptable at this point — if skipped, still proceed to Step 4 and verify manually per Step 5's note.

- [ ] **Step 4: Replace the `ocr_page` stub in `anonymize.py`**

Replace:

```python
def ocr_page(page) -> str:
    raise RuntimeError("OCR fallback not implemented yet")
```

with:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_pdf.py -v`
Expected: PASS (3 tests, or 2 passed + 1 skipped if Tesseract isn't installed on this machine). If Tesseract is installed but OCR misreads the synthetic text, try increasing the font size or padding in the test image — Tesseract is sensitive to image clarity, and this is a real dependency on the local OCR install, not a bug in `anonymize.py`.

If Tesseract is not installed locally and you want to verify this path at least once: install it (Windows: `winget install UB-Mannheim.TesseractOCR`), re-run, then it's fine if it's left uninstalled afterward — the skip guard means CI/other machines degrade gracefully.

- [ ] **Step 6: Commit**

```bash
git add anonymize.py requirements.txt tests/test_pdf.py
git commit -m "feat: add OCR fallback for scanned PDF pages"
```

---

## Task 9: Wire PDF conversion into `process_file`

**Files:**
- Modify: `anonymize.py` — `process_file` (add `.pdf` branch) and `main()` (add `pdf_converted` counter).
- Test: `tests/test_integration.py`

**Interfaces:**
- Consumes: `convert_pdf_to_markdown` from Task 7/8.
- Produces: `process_file` now also returns status `"pdf"` for `.pdf` sources.

- [ ] **Step 1: Write the failing test**

```python
fitz = pytest.importorskip("fitz")

from anonymize import process_file, load_replacements


def test_process_file_converts_pdf_to_markdown(tmp_path):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "VM contact jan@example.com")

    source = tmp_path / "report.pdf"
    document.save(source)
    document.close()

    replacements_file = tmp_path / "replacements.json"
    replacements_file.write_text('{"VM": "Company1"}', encoding="utf-8")
    replacements = load_replacements(replacements_file)

    destination = tmp_path / "out" / "report.pdf"

    status, pii_count = process_file(source, destination, replacements)

    md_path = destination.with_suffix(".md")

    assert status == "pdf"
    assert pii_count == 1
    assert md_path.exists()

    content = md_path.read_text(encoding="utf-8")
    assert "Company1 contact [EMAIL]" in content
```

(Add `import pytest` and `import fitz`-via-importorskip pattern consistent with `tests/test_pdf.py` if this is a fresh section of `tests/test_integration.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration.py -v`
Expected: FAIL — `.pdf` currently falls through to the "copy unchanged" branch, so `status == "copied"` and no `.md` file is created.

- [ ] **Step 3: Add the PDF branch to `process_file`**

Find the end of the PPTX branch and the start of the fallback comment in `process_file`:

```python
        return "office", pii_count

    # Unknown/binary file:
    # Copy it unchanged.
```

Replace with:

```python
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
```

- [ ] **Step 4: Add the `pdf_converted` counter in `main()`**

Note: after Task 6 Step 4, this whole section of `main()` lives inside the `try:` block, so it's indented one extra level (8 spaces for top-level statements in this block, 16/20 for the dispatch inside the nested `for`/`try`) compared to how it looked before Task 6. The snippets below match that current, post-Task-6 indentation.

Find the counter block:

```python
        processed = 0
        anonymized = 0
        office_converted = 0
        copied = 0
        errors = 0
        pii_redacted = 0
```

Replace with:

```python
        processed = 0
        anonymized = 0
        office_converted = 0
        pdf_converted = 0
        copied = 0
        errors = 0
        pii_redacted = 0
```

Find the result-dispatch inside the processing loop:

```python
                if result == "anonymized":
                    anonymized += 1
                elif result == "office":
                    office_converted += 1
                else:
                    copied += 1
```

Replace with:

```python
                if result == "anonymized":
                    anonymized += 1
                elif result == "office":
                    office_converted += 1
                elif result == "pdf":
                    pdf_converted += 1
                else:
                    copied += 1
```

Find the summary print block:

```python
        print(f"Files found       : {len(files):,}")
        print(f"Files processed   : {processed:,}")
        print(f"Archives extracted: {archives_extracted:,}")
        print(f"Text/code         : {anonymized:,}")
        print(f"Office -> Markdown: {office_converted:,}")
        print(f"Copied unchanged  : {copied:,}")
        print(f"PII fragments     : {pii_redacted:,}")
        print(f"Errors            : {errors:,}")
        print(f"Processing time   : {format_duration(duration)}")
```

Replace with:

```python
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
```

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS, all tests across all tasks so far.

- [ ] **Step 6: Commit**

```bash
git add anonymize.py tests/test_integration.py
git commit -m "feat: wire PDF-to-Markdown conversion into process_file"
```

---

## Task 10: End-to-end integration test and dependency documentation

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `requirements.txt` (add a header comment; no new packages)
- Modify: `anonymize.py` (top-of-file comment listing system dependencies)

**Interfaces:**
- None new — this task only verifies the full pipeline built across Tasks 1-9 works together end to end.

- [ ] **Step 1: Write the failing end-to-end test**

```python
import json
import zipfile


def test_full_run_processes_mixed_source_tree(tmp_path, capsys):
    from anonymize import scan_files, process_file, load_replacements
    import shutil

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

    try:
        entries = scan_files(source_dir, output_root, temp_dirs)

        results = {}
        for entry in entries:
            destination = output_root / entry.relative_destination
            status, pii_count = process_file(
                entry.source, destination, replacements
            )
            results[str(entry.relative_destination)] = (status, pii_count)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration.py -v`
Expected: FAIL only if any earlier task's wiring is incomplete. If Tasks 1-9 were implemented correctly, this may already pass — in that case, skip to Step 4 (there's nothing to implement, only to verify).

- [ ] **Step 3: Fix any wiring gaps found**

If the test fails, the failure output identifies which key (`plain.txt` or `bundle/nested.txt`) has the wrong status/content — trace it back to the relevant task above (Task 4 for the text-file path, Task 6 for the zip path) and check the corresponding code block was applied exactly as written there.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ -v`
Expected: PASS, full suite.

- [ ] **Step 5: Add a system-dependencies comment to `anonymize.py`**

Find the top of the file:

```python
#!/usr/bin/env python3

import argparse
```

Replace with:

```python
#!/usr/bin/env python3
#
# Optional system dependencies (beyond `pip install -r requirements.txt`):
#   - .rar archives: the 'unrar' (or 'unar'/'bsdtar') tool must be on
#     PATH. Windows: winget install RARLab.WinRAR
#   - Scanned PDFs (OCR): the Tesseract OCR engine must be installed.
#     Windows: winget install UB-Mannheim.TesseractOCR
# Both are optional: without them, the affected archive/PDF is reported
# as an error and the rest of the run continues normally.

import argparse
```

- [ ] **Step 6: Add a header comment to `requirements.txt`**

Read the current `requirements.txt` and rewrite it with a header comment, preserving every existing line:

```
# Core: Office/PDF conversion + PII archive handling.
python-docx
openpyxl
python-pptx
py7zr
rarfile
pymupdf
pytesseract
Pillow

# Dev: testing
pytest
```

- [ ] **Step 7: Run the full suite one last time**

Run: `pytest tests/ -v`
Expected: PASS, full suite, no regressions.

- [ ] **Step 8: Commit**

```bash
git add anonymize.py requirements.txt tests/test_integration.py
git commit -m "test: add end-to-end integration coverage; document system deps"
```

---

## Self-Review Notes

- **Spec coverage:** archive formats/extraction/depth-limit/fallback → Tasks 5-6; PDF text+OCR+tables → Tasks 7-8; PII categories+checksums+placeholders+always-on → Tasks 2-3; wiring into existing pipeline + summary counters → Tasks 4, 6, 9; requirements.txt + soft-import pattern → Tasks 1, 5, 7, 8, 10; single-file constraint → honored throughout (all functions added to `anonymize.py`); graceful degradation on missing system deps → Tasks 5 (`rarfile.Error` handling), 8 (`TesseractNotFoundError` handling); nested nomenclature (`outer/inner/...`) → Task 6.
- **Type consistency check:** `process_file` returns `tuple[str, int]` from Task 4 onward — Tasks 4, 6, 9 all match this. `scan_files` returns `list[ScanEntry]` from Task 6 onward — Task 6's `main()` update and Task 10's integration test both consume it consistently. `redact_pii` returns `tuple[str, int]` — used identically in Tasks 4 and 9. `extract_archive` raises rather than returning a status — Task 6's `scan_files` is the only caller and it wraps every call in `try/except Exception`, matching this contract.
