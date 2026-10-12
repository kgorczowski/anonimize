# Cross-Platform Compatibility Design

## Goal

Make `anonymize.py` verifiably work on Windows, macOS, and Linux — not just
"probably works because it's Python," but proven on every push by an
automated test run on all three, so a platform-specific regression is
caught before merge instead of through a real user's bug report (the
pattern that produced both the `find_tables()` hang and the `install.sh`
CRLF crash earlier in this project).

Revised 2026-10-12 after actually running the suite on a second OS and
exercising real `.rar` extraction; the first draft of this spec was based
on a code audit alone and several of its claims did not survive contact
with evidence (see "What verification changed").

## Audit findings

A pattern search of `anonymize.py` for common cross-platform footguns
(locale-dependent file encoding, hardcoded path separators, shelling out to
OS-specific commands, `sys.platform`/`os.name` branching) found the core
code clean, and running the real suite confirmed it:

- Every file read/write specifies `encoding="utf-8"` explicitly — no
  reliance on the OS locale default encoding.
- All path handling goes through `pathlib.Path`; no hardcoded `\` or `/`
  joins.
- `locate_tesseract()` checks `shutil.which("tesseract")` first and only
  then a Windows-specific list of default install folders. Inert on
  Mac/Linux.
- **Verified on Linux:** the full suite (170 tests at the time) passes on
  Debian/Python 3.11 with a real Tesseract 5.5 installed, with zero
  skipped tests — run locally in an ephemeral `python:3.11-slim` Docker
  container. It also passes on Windows/Python 3.14 (the dev machine).
  macOS cannot be tested locally; CI is its only verification.

## What verification changed

1. **RAR extraction was never actually tested.** The only RAR test feeds
   garbage bytes and asserts an error. `rarfile` reads *stored*
   (uncompressed) entries in pure Python, so even a naive fixture would
   not exercise the external tool; real-world archives are compressed and
   need one. Installing `unrar` in CI, as the first draft proposed, would
   have verified nothing.
2. **Compressed RAR5 backend support is uneven** (measured with
   `rarfile` 4.5 against a real RAR 7.00-produced archive):

   | Backend | Result |
   |---|---|
   | `unrar` (Ubuntu 24.04) | works |
   | `unar` (Ubuntu 24.04) | works |
   | `bsdtar` (libarchive-tools, Ubuntu 24.04) | fails (`BadRarFile`) |
   | `7z` (p7zip 16.02, Ubuntu 24.04) | fails (`BadRarFile`) |
   | 7-Zip 26.02 on Windows, via absolute path | works |
   | Windows built-in `tar.exe` (bsdtar 3.8.8) | fails (`BadRarFile`) |

   So the documented "`unrar` (or `unar`/`bsdtar`)" is wrong about
   `bsdtar`, and `unar` is the better cross-platform recommendation: free,
   in the standard repositories of Homebrew and Debian/Ubuntu.
3. **On Windows, `.rar` extraction fails out of the box.** `rarfile` only
   looks for tools on PATH. On the dev machine 7-Zip is installed but not
   on PATH and WinRAR is absent, so extracting a compressed RAR fails with
   `RarCannotExec: Cannot find working tool`; pointing `rarfile` at
   `C:\Program Files\7-Zip\7z.exe` makes the same archive extract
   correctly. This is the same class of problem `locate_tesseract()`
   already solves for OCR, and the documented `winget install
   RARLab.WinRAR` does not put the tool on PATH either.
4. **A PATH-only check in the install scripts would give false warnings
   on Windows**, because the Python code (by design, per the earlier
   decision not to touch system PATH) finds Tesseract and RAR tools in
   their default install folders even when they are not on PATH. Detection
   therefore belongs in one place — Python — and the scripts call it.
5. **The OCR test would silently skip on a Windows runner** where
   Tesseract is installed but not on PATH: its availability check
   (`_tesseract_available()` in `tests/test_pdf.py`) ignores the fallback
   the product uses, so CI could report green without ever running OCR.

## Design

### 1. RAR tool auto-detection (code change)

New `locate_rar_tool()` next to `extract_archive`, analogous to
`locate_tesseract()`: returns `None` when `unrar` or `unar` is already on
PATH; otherwise the first existing default Windows install of WinRAR's
`UnRAR.exe` or 7-Zip's `7z.exe` as a `(rarfile_setting, path)` pair.
`extract_archive`'s RAR branch applies it (`rarfile.UNRAR_TOOL` /
`rarfile.SEVENZIP_TOOL`, then `rarfile.tool_setup(force=True)`) before
opening the archive, inside the existing error handling, and its error
message names the real requirements (unrar or unar; on Windows also WinRAR
or 7-Zip) instead of only `unrar`.

A small compressed RAR5 fixture (`tests/fixtures/sample_rar5_compressed.rar`,
124 bytes, produced by RAR 7.00 with `rar a -ep -m3 -ma5` from 40 lines of
`VM contact: jan@example.com`) backs a real extraction test that skips only
when no working backend exists. `.gitattributes` marks `*.rar` binary so a
Windows checkout can never CRLF-corrupt it.

### 2. Optional-tool report (code change) and install-script integration

New `report_optional_tools()` prints, for Tesseract and RAR extraction,
whether each is available (PATH or the same default-folder fallbacks) and,
when missing, the install command for the current OS (`sys.platform`).
`scripts/install.sh` and `scripts/install.ps1` call it after the pip
install, non-fatally, so the warning is accurate on every OS and the
detection logic exists once. (Supersedes the first draft's per-shell PATH
checks.)

### 3. Documentation

Header comment in `anonymize.py` and the dependency table in `README.md`
get macOS and Linux commands next to the Windows ones, recommend `unar` /
`unrar` for RAR (dropping the incorrect `bsdtar` claim), add `winget
install 7zip.7zip` as a Windows option (package IDs `7zip.7zip`,
`RARLab.WinRAR` and `UB-Mannheim.TesseractOCR` verified with `winget
show`), and state that Tesseract, WinRAR and 7-Zip are found in their
default Windows folders without a PATH change.

### 4. OCR test honors the product's fallback

`_tesseract_available()` in `tests/test_pdf.py` configures
`pytesseract` from `anonymize.locate_tesseract()` before probing the
version, so the real OCR test runs — and therefore exercises the fallback
end to end — wherever the product itself could run OCR.

### 5. GitHub Actions CI

New `.github/workflows/tests.yml`: matrix over `ubuntu-latest`,
`macos-latest`, `windows-latest`; Python 3.11 (the tool's stated floor is
3.9, CI intentionally stays at one version; widening the matrix is a
one-line change); triggers on push to `main` and on pull requests;
least-privilege `permissions: contents: read`; per-job timeout (the project
has a history of a library call that hung forever); superseded runs
cancelled.

Per-OS system tools: Linux `apt-get install tesseract-ocr unar`; macOS
`brew install tesseract unar`; Windows `choco install tesseract` plus the
7-Zip that GitHub's Windows image already ships.

The test step fails the job if *any* test was skipped, so "the full suite
runs for real on every OS" is enforced rather than hoped for. Each job also
runs the install script for its OS (`bash scripts/install.sh` everywhere,
including Windows' Git Bash, which is exactly the setup that exposed the
CRLF bug; plus `scripts/install.ps1` under Windows PowerShell 5.1 on
Windows).

The workflow is linted locally with `actionlint` (Docker) before pushing.
The repository is public, so Actions minutes are free.

## Out of scope

- Testing multiple Python versions (this is about OS portability).
- Distros beyond GitHub's three standard runners (Alpine/musl, ARM, WSL).
- A RAR4 fixture: RAR 7.x can no longer create RAR4 archives, and RAR5 is
  the stricter case for backend support.
- Changes to the anonymization logic — the audit and the Linux run found
  it platform-clean.

## Testing

- Unit tests for `locate_rar_tool()` and `report_optional_tools()` using
  monkeypatched `shutil.which`, install-folder tables and `sys.platform`
  (same pattern as the existing `locate_tesseract()` tests).
- A wiring test proving `extract_archive` points `rarfile` at the located
  tool, and the real compressed-RAR5 extraction test described above.
- CI itself is the verification for macOS and for the workflow; before
  pushing, the Linux job is reproduced locally in an Ubuntu 24.04 container
  with the same packages and the zero-skips rule.
