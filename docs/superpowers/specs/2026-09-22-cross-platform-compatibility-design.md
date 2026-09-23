# Cross-Platform Compatibility Design

## Goal

Make `anonymize.py` verifiably work on Windows, macOS, and Linux — not just
"probably works because it's Python," but proven on every push by an
automated test run on all three, so a platform-specific regression is
caught before merge instead of through a real user's bug report (the
pattern that produced both the `find_tables()` hang and the `install.sh`
CRLF crash earlier in this project).

## Audit findings

A pattern search of `anonymize.py` for common cross-platform footguns
(locale-dependent file encoding, hardcoded path separators, shelling out to
OS-specific commands, `sys.platform`/`os.name` branching) found the core
code already clean:

- Every file read/write specifies `encoding="utf-8"` explicitly (e.g.
  `anonymize.py:75`, every `destination.write_text(...)` call) — no
  reliance on the OS locale default encoding (which differs between
  Windows/cp1252-family and Mac/Linux/utf-8 and is a common source of
  Windows-only mojibake bugs).
- All path handling goes through `pathlib.Path`; no hardcoded `\` or `/`
  joins.
- `locate_tesseract()` (`anonymize.py:567`) checks `shutil.which("tesseract")`
  first — which works identically on all three OSes since Homebrew/apt
  both put their installed binaries on PATH — and only falls back to a
  Windows-specific common-path list. That fallback is inert (not harmful)
  on Mac/Linux.
- The Python-interpreter detection in `scripts/install.sh` /
  `scripts/install.ps1` already tries `py`/`python3`/`python` in order and
  verifies each one actually runs, on both scripts symmetrically.

The real gaps are two things, both about the two **optional** system
binaries (`unrar` for `.rar` archives, Tesseract for scanned-PDF OCR):

1. **Documentation.** Both `anonymize.py:3-7` (header comment) and
   `README.md:17-19` document install commands for these two dependencies
   for Windows only (`winget install ...`). A Mac or Linux user has no
   guidance for getting either one installed.
2. **No automated verification on any OS at all.** The project currently
   has zero CI. The full `pytest` suite has only ever been run on the
   Windows dev machine. Several tests already skip gracefully when an
   optional dependency isn't importable (e.g.
   `tests/test_integration.py`'s `fitz = pytest.importorskip("pymupdf")`),
   which means even a Mac/Linux *manual* test run could silently skip the
   PDF/OCR/RAR code paths without anyone noticing they weren't exercised.

## Design

### 1. Documentation fix

Add macOS and Linux install commands alongside the existing Windows ones,
in both locations that currently only have Windows:

- `anonymize.py:3-7` header comment
- `README.md`'s dependency table (`README.md:17-19`)

Commands: `brew install unar` / `brew install tesseract` for macOS;
`apt install unrar tesseract-ocr` (Debian/Ubuntu family) for Linux — matching
the existing Windows `winget install RARLab.WinRAR` /
`winget install UB-Mannheim.TesseractOCR` lines in tone and placement.

### 2. GitHub Actions CI matrix

New file: `.github/workflows/tests.yml`. Matrix over
`os: [ubuntu-latest, macos-latest, windows-latest]`, single Python version
(3.11 — the CI version; the tool itself keeps supporting 3.9+ as already
stated in the install scripts' error message). Triggers on push and pull
request.

Each OS job, before running the suite, installs the two optional system
binaries so the full suite runs for real rather than skipping those tests:

- **ubuntu-latest:** `sudo apt-get update && sudo apt-get install -y unrar tesseract-ocr`
- **macos-latest:** `brew install unar tesseract` (GitHub's macOS runners
  ship Homebrew preinstalled)
- **windows-latest:** `choco install unrar tesseract -y` (GitHub's Windows
  runners ship Chocolatey preinstalled; more reliable in a non-interactive
  CI job than `winget`, which is the right choice for an interactive
  install script but not for CI)

Then: `pip install -r requirements.txt`, then `pytest`.

This directly buys what "works on every OS" means in practice: the same
143+ tests (a number that will keep growing) run against real system
binaries on all three OSes on every push, so a Mac- or Linux-specific
regression shows up as a failed CI check instead of a future production
bug report.

### 3. Install-script parity check (minor, optional)

`scripts/install.sh` / `scripts/install.ps1` currently only install Python
pip dependencies — they don't mention the two optional system binaries at
all. Extend both to check for `unrar` and `tesseract` on PATH after the
pip install step and print a non-fatal warning with the appropriate
platform install command if either is missing (mirroring the existing
`locate_tesseract()` "helpfully find it or tell the user" pattern already
used elsewhere in the codebase). Since both dependencies are already
optional — the tool degrades gracefully (reports an error, excludes the
affected file, continues) when either is missing, regardless of OS — this
is a UX nicety, not a correctness requirement.

## Out of scope

- Testing multiple Python versions (this design is about OS portability,
  not language-version compatibility — a different, unrequested concern).
- Distros/environments beyond what GitHub's three standard runners
  represent (e.g. Alpine/musl, WSL specifically, ARM runners).
- Any change to the core anonymization logic — the audit found it already
  platform-clean.

## Testing

CI itself *is* the test for this feature: once `.github/workflows/tests.yml`
lands and runs green on all three OSes, that is the proof. No new unit
tests are needed for the documentation changes; the install-script warning
addition (if kept) should get the same kind of scripted-invocation test
coverage the scripts don't currently have any of — this design doesn't
add script tests beyond that warning check itself, since the scripts have
no existing test harness and building one is out of scope here.
