# Anonimize

A command-line tool that recursively walks a directory, anonymizes text and code files by replacing sensitive strings with placeholders, converts Office documents and PDFs to Markdown before anonymizing them too, extracts archives so their contents get the same treatment, and automatically redacts common PII (emails, phone numbers, PESEL, NIP, IBAN, card numbers, IP addresses) on top of the dictionary-based replacements.

## Requirements

- Python 3.9+
- Dependencies from `requirements.txt` — see [CONTRIBUTING.md](CONTRIBUTING.md) for setup scripts and Windows-specific `python`/`gh` PATH notes.

```bash
pip install -r requirements.txt
```

Two dependencies are optional system tools (not pip packages), needed only for specific file types:

| Needed for | Tool | Windows install |
|---|---|---|
| `.rar` archives | `unrar` (or `unar`/`bsdtar`) on PATH | `winget install RARLab.WinRAR` |
| Scanned/OCR'd PDF pages | Tesseract OCR engine | `winget install UB-Mannheim.TesseractOCR` |

Without them, the affected archive/PDF is reported as an error (and excluded from the output — see below) rather than crashing the run. If Tesseract is installed but not found, `anonymize.py` also checks the common Windows install locations directly, so it works even before you open a new terminal.

## Usage

```bash
python anonymize.py <source> <replacements.json> [--output <dir>]
```

| Argument | Required | Description |
|---|---|---|
| `source` | yes | Source directory to scan recursively |
| `replacements` | yes | Path to a JSON file mapping strings to replace with their anonymized value |
| `--output` | no | Output directory. Defaults to `<source-parent>/anonimized/<source-name>` |

### Example

```bash
python anonymize.py ./client-project ./replacements.json --output ./anonymized-output
```

## Replacements file format

A flat JSON object mapping each sensitive string to the value it should be replaced with:

```json
{
  "LLM Company": "Company1",
  "BRG Company": "Company2"
}
```

Matching is a case-insensitive substring replacement — a dictionary entry `"BDR": "namespace1"` matches `BDR`, `bdr`, and `Bdr` alike, always substituting the exact value from the dictionary regardless of how the match was cased. This also applies to **folder and file names**: a folder literally named `BDR` (or `bdr`) is renamed to `namespace1` in the output, and a file named `BDR_report.pdf` becomes `namespace1_report.pdf` (the extension itself is never touched). This is what makes case/namespace conventions that differ by language work out of the box — a C# `namespace BDR.Services` (PascalCase) and a Java `package com.company.bdr.services` (lowercase) both match the same dictionary entry.

Longer keys are matched before shorter ones, so a more specific string is never shadowed by a shorter one contained within it.

## What gets processed

| File type | Behavior |
|---|---|
| Text/code (`.txt`, `.md`, `.py`, `.js`, `.json`, `.sql`, `.cs`, `.java`, `.ps1`, and other common source/config extensions) | Read as text, dictionary + PII anonymized in place |
| Office (`.docx`, `.xlsx`, `.pptx`) | Converted to Markdown, anonymized, written as `.md` |
| PDF | Converted to Markdown (OCR fallback for scanned pages), anonymized, written as `.md` |
| Archives (`.zip`, `.tar`/`.tar.gz`/`.tar.bz2`/`.tar.xz`, `.7z`, `.rar`) | Extracted (recursively, including nested archives) and every file inside gets the same treatment as above; the archive itself doesn't appear in the output |
| Everything else | Copied unchanged |

Folder and file **names** are anonymized against the dictionary for every one of the above (see "Replacements file format"). File **contents** additionally go through automatic PII detection after the dictionary replacement, redacting emails, phone numbers, PESEL, NIP, IBAN, card numbers, and IPv4 addresses with generic tags (`[EMAIL]`, `[PESEL]`, etc.) — this only applies to file types that are actually read as text/converted above, never to binaries copied unchanged. PII detection is regex-based and heuristic: it can occasionally miss an unusual format, and four-part version strings (`"1.0.0.0"` in `.cs`/`.json`/`.xml`/build files) are indistinguishable from IPv4 addresses and get redacted as `[IP]`.

Non-UTF-8 text files that can't be decoded are copied unchanged rather than corrupted. A file, archive, or PDF page that fails to process is reported as an error and **excluded from the output** rather than copied in unprocessed — this tool exists to anonymize PII, so a raw source file that couldn't be safely anonymized must not end up in what's meant to be a safe output directory.

The tool scans the whole source tree first (so it can show accurate progress and an ETA), then processes every file, and prints a summary of how many files were anonymized, converted, extracted, copied, redacted, or errored.

## License

MIT — see [LICENSE](LICENSE).
