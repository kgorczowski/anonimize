# Cross-Platform Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `anonymize.py` verifiably work on Windows, macOS and Linux: fix the one real cross-platform gap found (`.rar` extraction on Windows when no tool is on PATH), make optional-tool detection and documentation accurate on every OS, and add a three-OS GitHub Actions matrix that runs the full suite with the optional tools installed and fails on any skipped test.

**Architecture:** One new detection helper (`locate_rar_tool`, the RAR twin of `locate_tesseract`) wired into `extract_archive`; one reporting helper (`report_optional_tools`) that both install scripts call so detection lives in Python once; test-suite fixes so OCR and RAR tests really run where the product can run them; a workflow plus two small scripts (`run-tests.sh`, `test-in-docker.sh`) so the same strict run works in CI and locally.

**Tech Stack:** Python 3.9+ (stdlib + existing dependencies), `rarfile` 4.x, pytest, bash/PowerShell scripts, GitHub Actions, Docker (local Linux reproduction and `actionlint` only).

**Spec:** `docs/superpowers/specs/2026-09-22-cross-platform-compatibility-design.md` (revised 2026-10-12 with the verification evidence this plan relies on)

## Global Constraints

- All code stays in the single file `anonymize.py` — no new source modules (deliberate project rule). New *test* files and shell scripts are fine.
- Python 3.9+ compatible syntax in `anonymize.py` and the tests: no `X | Y` type unions, no `match` statements, no parenthesized multi-item `with`. (CI runs 3.11; the dev machine runs 3.14.)
- Never modify system PATH or environment variables. Tools installed in their default Windows folders are found by absolute path from Python (user-chosen design, same as `locate_tesseract`).
- Windows default-install-folder tables must be inert on macOS/Linux (`Path(...).is_file()` is simply `False` there), exactly like `TESSERACT_COMMON_PATHS`.
- Console output and comments are English and ASCII-only (Windows consoles).
- A RAR that cannot be extracted must keep raising (`RuntimeError`), so the file stays excluded from the output — the project's core rule that the output directory never contains a non-anonymized file does not change.
- Shell scripts must keep LF line endings (`*.sh text eol=lf` already in `.gitattributes`); `*.rar` fixtures are binary (`*.rar binary`, already in `.gitattributes`).
- Run Python as `py` on the dev machine (bare `python`/`python3` are broken Microsoft Store stubs there).
- Interactive-mode and classic-CLI behavior must not change.

## Prerequisites already committed with this plan (do not recreate)

- `tests/fixtures/sample_rar5_compressed.rar` — 124 bytes, SHA-256 `989874C5B2618322A81B3D07C6B344758F1D9FC89927C576EA47E5121F5A78C5`. Produced by RAR 7.00 (`rar a -ep -m3 -ma5`) from a `hello.txt` of 40 identical lines `VM contact: jan@example.com`. It is compressed on purpose: `rarfile` reads stored entries in pure Python, so only a compressed archive exercises the external tool.
- `.gitattributes` rule `*.rar binary`.

---

## File Structure

- **Modify:** `anonymize.py` — `RAR_TOOL_COMMON_PATHS`, `locate_rar_tool()`, the RAR branch of `extract_archive()`, `report_optional_tools()`, header comment.
- **Modify:** `tests/test_archives.py` — RAR detection, wiring and real-extraction tests.
- **Create:** `tests/test_optional_tools.py` — tests for `report_optional_tools()`.
- **Modify:** `tests/test_pdf.py` — OCR test honors the product's Tesseract fallback.
- **Modify:** `scripts/install.sh`, `scripts/install.ps1` — print the optional-tool report.
- **Create:** `scripts/run-tests.sh`, `scripts/test-in-docker.sh`.
- **Create:** `.github/workflows/tests.yml`.
- **Modify:** `README.md`, `CONTRIBUTING.md`.

**A note on anchors:** every "Find" instruction shows the exact text to search for — that text is the anchor. Line numbers are only hints and drift as earlier tasks edit the file.

---

## Task 1: RAR tool auto-detection and a real extraction test

**Files:**
- Modify: `anonymize.py`
- Modify: `tests/test_archives.py`

**Interfaces:**
- Produces: `RAR_TOOL_COMMON_PATHS: tuple` of `(rarfile_setting_name, path)` pairs, and `locate_rar_tool() -> Optional[tuple]` returning `(rarfile_setting_name, path)` or `None`. Task 2's `report_optional_tools()` consumes the return value (`result[1]` is the path).

**Background (verified, do not re-derive):** `rarfile` 4.5 reads its tool settings at call time (`rarfile.UNRAR_TOOL`, `rarfile.SEVENZIP_TOOL`, ...) and caches the chosen tool in `rarfile.CURRENT_SETUP`; `rarfile.tool_setup(force=True)` clears that cache and re-picks, trying unrar, unar, 7z, 7zz, bsdtar in that order. On the dev machine (Windows) 7-Zip is installed but not on PATH and WinRAR is absent, so the default lookup fails with `RarCannotExec: Cannot find working tool`, while setting `rarfile.SEVENZIP_TOOL = r"C:\Program Files\7-Zip\7z.exe"` makes the fixture extract correctly.

- [ ] **Step 1: Write the failing tests**

In `tests/test_archives.py`, find the import block:

```python
import pytest

from anonymize import (
    classify_archive,
    archive_stem,
    anonymize_destinations,
    anonymize_relative_path,
    deduplicate_destinations,
    is_archive_file,
    extract_archive,
    scan_files,
```

Replace it with (adds `import anonymize` and `locate_rar_tool`):

```python
import pytest

import anonymize
from anonymize import (
    classify_archive,
    archive_stem,
    anonymize_destinations,
    anonymize_relative_path,
    deduplicate_destinations,
    is_archive_file,
    extract_archive,
    locate_rar_tool,
    scan_files,
```

Then find this existing test:

```python
def test_extract_archive_raises_on_corrupt_rar(tmp_path):
    pytest.importorskip("rarfile")

    source = tmp_path / "broken.rar"
    source.write_bytes(b"not a real rar file")

    with pytest.raises(Exception):
        extract_archive(source, tmp_path / "extracted")
```

Replace it with itself followed by the new tests:

```python
def test_extract_archive_raises_on_corrupt_rar(tmp_path):
    pytest.importorskip("rarfile")

    source = tmp_path / "broken.rar"
    source.write_bytes(b"not a real rar file")

    with pytest.raises(Exception):
        extract_archive(source, tmp_path / "extracted")


def test_locate_rar_tool_returns_none_when_unar_is_on_path(monkeypatch):
    monkeypatch.setattr(
        anonymize.shutil,
        "which",
        lambda name: "/usr/bin/unar" if name == "unar" else None,
    )

    assert locate_rar_tool() is None


def test_locate_rar_tool_returns_none_when_unrar_is_on_path(monkeypatch):
    monkeypatch.setattr(
        anonymize.shutil,
        "which",
        lambda name: "/usr/bin/unrar" if name == "unrar" else None,
    )

    assert locate_rar_tool() is None


def test_locate_rar_tool_finds_a_default_windows_install(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(anonymize.shutil, "which", lambda name: None)

    fake_7zip = tmp_path / "7-Zip" / "7z.exe"
    fake_7zip.parent.mkdir()
    fake_7zip.write_bytes(b"")

    monkeypatch.setattr(
        anonymize,
        "RAR_TOOL_COMMON_PATHS",
        (("SEVENZIP_TOOL", str(fake_7zip)),),
    )

    assert locate_rar_tool() == ("SEVENZIP_TOOL", str(fake_7zip))


def test_locate_rar_tool_prefers_the_first_existing_candidate(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(anonymize.shutil, "which", lambda name: None)

    winrar = tmp_path / "WinRAR" / "UnRAR.exe"
    sevenzip = tmp_path / "7-Zip" / "7z.exe"

    for tool in (winrar, sevenzip):
        tool.parent.mkdir()
        tool.write_bytes(b"")

    monkeypatch.setattr(
        anonymize,
        "RAR_TOOL_COMMON_PATHS",
        (
            ("UNRAR_TOOL", str(tmp_path / "missing" / "UnRAR.exe")),
            ("UNRAR_TOOL", str(winrar)),
            ("SEVENZIP_TOOL", str(sevenzip)),
        ),
    )

    assert locate_rar_tool() == ("UNRAR_TOOL", str(winrar))


def test_locate_rar_tool_returns_none_when_nothing_is_installed(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(anonymize.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        anonymize,
        "RAR_TOOL_COMMON_PATHS",
        (("UNRAR_TOOL", str(tmp_path / "nope.exe")),),
    )

    assert locate_rar_tool() is None


@pytest.fixture
def isolated_rarfile(monkeypatch):
    """extract_archive reconfigures rarfile's module-level tool settings
    and rarfile caches the tool it picks; restore all of it after the
    test so tests cannot leak a tool choice into each other."""
    rarfile = pytest.importorskip("rarfile")

    monkeypatch.setattr(rarfile, "UNRAR_TOOL", rarfile.UNRAR_TOOL)
    monkeypatch.setattr(rarfile, "SEVENZIP_TOOL", rarfile.SEVENZIP_TOOL)
    monkeypatch.setattr(rarfile, "CURRENT_SETUP", None)

    return rarfile


class _FakeRarFile:
    def __init__(self, path):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def extractall(self, dest):
        _FakeRarFile.extracted_to = str(dest)


def test_extract_archive_rar_points_rarfile_at_a_located_tool(
    monkeypatch, tmp_path, isolated_rarfile
):
    rarfile = isolated_rarfile
    tool_setup_calls = []

    monkeypatch.setattr(
        anonymize,
        "locate_rar_tool",
        lambda: ("SEVENZIP_TOOL", r"C:\fake\7-Zip\7z.exe"),
    )
    monkeypatch.setattr(
        rarfile, "tool_setup", lambda **kwargs: tool_setup_calls.append(kwargs)
    )
    monkeypatch.setattr(rarfile, "RarFile", _FakeRarFile)

    source = tmp_path / "x.rar"
    source.write_bytes(b"")
    dest = tmp_path / "out"

    extract_archive(source, dest)

    assert rarfile.SEVENZIP_TOOL == r"C:\fake\7-Zip\7z.exe"
    assert tool_setup_calls == [{"force": True}]
    assert _FakeRarFile.extracted_to == str(dest)


def test_extract_archive_rar_does_not_touch_rarfile_when_nothing_located(
    monkeypatch, tmp_path, isolated_rarfile
):
    rarfile = isolated_rarfile
    original_unrar = rarfile.UNRAR_TOOL
    original_sevenzip = rarfile.SEVENZIP_TOOL
    tool_setup_calls = []

    monkeypatch.setattr(anonymize, "locate_rar_tool", lambda: None)
    monkeypatch.setattr(
        rarfile, "tool_setup", lambda **kwargs: tool_setup_calls.append(kwargs)
    )
    monkeypatch.setattr(rarfile, "RarFile", _FakeRarFile)

    source = tmp_path / "x.rar"
    source.write_bytes(b"")

    extract_archive(source, tmp_path / "out")

    assert rarfile.UNRAR_TOOL == original_unrar
    assert rarfile.SEVENZIP_TOOL == original_sevenzip
    assert tool_setup_calls == []


def test_extract_archive_rar_names_the_real_requirements_when_no_tool(
    monkeypatch, tmp_path, isolated_rarfile
):
    rarfile = isolated_rarfile

    class NoToolRarFile(_FakeRarFile):
        def extractall(self, dest):
            raise rarfile.RarCannotExec("Cannot find working tool")

    monkeypatch.setattr(anonymize, "locate_rar_tool", lambda: None)
    monkeypatch.setattr(rarfile, "RarFile", NoToolRarFile)

    source = tmp_path / "x.rar"
    source.write_bytes(b"")

    with pytest.raises(RuntimeError, match="unrar or unar"):
        extract_archive(source, tmp_path / "out")


# tests/fixtures/sample_rar5_compressed.rar is 124 bytes, made with RAR 7.00
# (`rar a -ep -m3 -ma5`) from a hello.txt of 40 lines of
# "VM contact: jan@example.com". It is compressed on purpose: rarfile reads
# stored entries itself, only compressed ones need an external tool.
def test_extract_archive_extracts_a_real_compressed_rar5(
    tmp_path, isolated_rarfile
):
    fixture = (
        Path(__file__).parent / "fixtures" / "sample_rar5_compressed.rar"
    )
    dest = tmp_path / "extracted"

    try:
        extract_archive(fixture, dest)
    except RuntimeError as exc:
        pytest.skip(f"No working RAR extraction tool on this machine: {exc}")

    lines = (dest / "hello.txt").read_text(encoding="utf-8").splitlines()

    assert len(lines) == 40
    assert set(lines) == {"VM contact: jan@example.com"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_archives.py -v`
Expected: collection error — `ImportError: cannot import name 'locate_rar_tool' from 'anonymize'`.

- [ ] **Step 3: Implement `locate_rar_tool` and wire it into `extract_archive`**

In `anonymize.py`, find this exact text (the start of `extract_archive`, unique in the file):

```python
def extract_archive(source: Path, dest_dir: Path) -> None:
    kind = classify_archive(source)
```

Replace it with the new constant and function followed by the same two lines:

```python
# rarfile only looks for its extraction tools on PATH, and neither the
# WinRAR nor the 7-Zip Windows installer adds itself to PATH. Same problem
# (and same remedy) as TESSERACT_COMMON_PATHS. Each entry is the rarfile
# module setting to point at the tool, and the tool's default location.
RAR_TOOL_COMMON_PATHS = (
    ("UNRAR_TOOL", r"C:\Program Files\WinRAR\UnRAR.exe"),
    ("UNRAR_TOOL", r"C:\Program Files (x86)\WinRAR\UnRAR.exe"),
    ("SEVENZIP_TOOL", r"C:\Program Files\7-Zip\7z.exe"),
    ("SEVENZIP_TOOL", r"C:\Program Files (x86)\7-Zip\7z.exe"),
)


def locate_rar_tool():
    """
    Returns (rarfile_setting_name, path) for a RAR-capable tool that is
    installed but not on PATH, so rarfile can be pointed at it directly.
    Returns None if unrar or unar is already on PATH (rarfile finds those
    itself), or if no known install location has a tool. bsdtar and old
    p7zip builds are deliberately not considered: they fail on compressed
    RAR5 archives.
    """
    if shutil.which("unrar") or shutil.which("unar"):
        return None

    for setting, candidate in RAR_TOOL_COMMON_PATHS:
        if Path(candidate).is_file():
            return setting, candidate

    return None


def extract_archive(source: Path, dest_dir: Path) -> None:
    kind = classify_archive(source)
```

Then find the RAR branch's `try` block (unique):

```python
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
```

Replace it with:

```python
        try:
            located = locate_rar_tool()

            if located is not None:
                setting, path = located
                setattr(rarfile, setting, path)
                rarfile.tool_setup(force=True)

            with rarfile.RarFile(source) as archive:
                archive.extractall(dest_dir)
        except rarfile.NeedFirstVolume:
            raise
        except rarfile.Error as exc:
            raise RuntimeError(
                "Cannot extract RAR archive. Extracting .rar needs a "
                "RAR-capable tool: unrar or unar (on Windows also WinRAR "
                "or 7-Zip). It was not found, or the archive is "
                f"corrupt/password-protected: {exc}"
            ) from exc
        return
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_archives.py -v`
Expected: all pass. **On the Windows dev machine 7-Zip is installed at `C:\Program Files\7-Zip`, so `test_extract_archive_extracts_a_real_compressed_rar5` must PASS, not skip** — that is the end-to-end proof that the fallback works. If it skips, stop and report BLOCKED with the skip message.

- [ ] **Step 5: Run the full suite**

Run: `py -m pytest tests/ -q`
Expected: everything passes, no regressions (baseline before this task: 170 tests; this task adds 9).

- [ ] **Step 6: Commit**

```bash
git add anonymize.py tests/test_archives.py
git commit -m "feat: find 7-Zip/WinRAR in default Windows folders for .rar extraction"
```

---

## Task 2: Optional-tool report, used by both install scripts

**Files:**
- Modify: `anonymize.py`
- Create: `tests/test_optional_tools.py`
- Modify: `scripts/install.sh`, `scripts/install.ps1`
- Modify: `CONTRIBUTING.md`

**Interfaces:**
- Consumes: `locate_tesseract() -> Optional[str]` (existing; `None` both when Tesseract is on PATH and when it is not found at all) and `locate_rar_tool() -> Optional[tuple]` from Task 1.
- Produces: `report_optional_tools() -> None`, printing to stdout. Task 5's CI smoke steps run the install scripts, which call it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_optional_tools.py`:

```python
import pytest

import anonymize


def _no_tools(monkeypatch):
    monkeypatch.setattr(anonymize.shutil, "which", lambda name: None)
    monkeypatch.setattr(anonymize, "locate_tesseract", lambda: None)
    monkeypatch.setattr(anonymize, "locate_rar_tool", lambda: None)


def test_report_optional_tools_lists_what_is_on_path(monkeypatch, capsys):
    monkeypatch.setattr(
        anonymize.shutil, "which", lambda name: f"/usr/bin/{name}"
    )
    monkeypatch.setattr(anonymize, "locate_tesseract", lambda: None)
    monkeypatch.setattr(anonymize, "locate_rar_tool", lambda: None)

    anonymize.report_optional_tools()

    out = capsys.readouterr().out

    assert "Optional system tools:" in out
    assert (
        "[ok]      Tesseract OCR (scanned PDF pages): /usr/bin/tesseract"
        in out
    )
    assert "[ok]      RAR extraction (.rar archives): /usr/bin/unar" in out
    assert "[missing]" not in out


def test_report_optional_tools_counts_default_folder_installs_as_found(
    monkeypatch, capsys
):
    monkeypatch.setattr(anonymize.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        anonymize,
        "locate_tesseract",
        lambda: r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    )
    monkeypatch.setattr(
        anonymize,
        "locate_rar_tool",
        lambda: ("SEVENZIP_TOOL", r"C:\Program Files\7-Zip\7z.exe"),
    )

    anonymize.report_optional_tools()

    out = capsys.readouterr().out

    assert (
        r"[ok]      Tesseract OCR (scanned PDF pages): "
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    ) in out
    assert (
        r"[ok]      RAR extraction (.rar archives): "
        r"C:\Program Files\7-Zip\7z.exe"
    ) in out
    assert "[missing]" not in out


@pytest.mark.parametrize(
    "platform,tesseract_hint,rar_hint",
    [
        ("darwin", "brew install tesseract", "brew install unar"),
        (
            "linux",
            "sudo apt install tesseract-ocr",
            "sudo apt install unar",
        ),
        (
            "win32",
            "winget install UB-Mannheim.TesseractOCR",
            "winget install 7zip.7zip",
        ),
    ],
)
def test_report_optional_tools_shows_the_install_hint_for_this_os(
    monkeypatch, capsys, platform, tesseract_hint, rar_hint
):
    _no_tools(monkeypatch)
    monkeypatch.setattr(anonymize.sys, "platform", platform)

    anonymize.report_optional_tools()

    out = capsys.readouterr().out

    assert (
        "[missing] Tesseract OCR (scanned PDF pages) - install with: "
        f"{tesseract_hint}"
    ) in out
    assert (
        "[missing] RAR extraction (.rar archives) - install with: "
        f"{rar_hint}"
    ) in out


def test_report_optional_tools_reports_each_tool_independently(
    monkeypatch, capsys
):
    _no_tools(monkeypatch)
    monkeypatch.setattr(
        anonymize, "locate_tesseract", lambda: "/opt/tesseract"
    )

    anonymize.report_optional_tools()

    out = capsys.readouterr().out

    assert "[ok]      Tesseract OCR (scanned PDF pages): /opt/tesseract" in out
    assert "[missing] RAR extraction (.rar archives)" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_optional_tools.py -v`
Expected: FAIL with `AttributeError: module 'anonymize' has no attribute 'report_optional_tools'`.

- [ ] **Step 3: Add `report_optional_tools` to `anonymize.py`**

Find this exact line (the last line of `extract_archive`, unique in the file):

```python
    raise ValueError(f"Not a supported archive: {source}")
```

Replace it with itself followed by the new function:

```python
    raise ValueError(f"Not a supported archive: {source}")


def report_optional_tools() -> None:
    """
    Prints whether the optional system tools (Tesseract OCR and a RAR
    extractor) are available - on PATH or in the default Windows install
    folders the product itself falls back to - with an install command for
    this OS for each one that is missing. scripts/install.sh and
    scripts/install.ps1 call this, so the detection exists once here
    instead of being re-implemented (and disagreeing) in each shell.
    """
    if sys.platform == "darwin":
        install_tesseract = "brew install tesseract"
        install_rar = "brew install unar"
    elif sys.platform == "win32":
        install_tesseract = "winget install UB-Mannheim.TesseractOCR"
        install_rar = "winget install 7zip.7zip"
    else:
        install_tesseract = "sudo apt install tesseract-ocr"
        install_rar = "sudo apt install unar"

    rar_fallback = locate_rar_tool()

    tesseract = shutil.which("tesseract") or locate_tesseract()
    rar = (
        shutil.which("unar")
        or shutil.which("unrar")
        or (rar_fallback[1] if rar_fallback else None)
    )

    print("Optional system tools:")

    for label, found, install in (
        ("Tesseract OCR (scanned PDF pages)", tesseract, install_tesseract),
        ("RAR extraction (.rar archives)", rar, install_rar),
    ):
        if found:
            print(f"  [ok]      {label}: {found}")
        else:
            print(f"  [missing] {label} - install with: {install}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_optional_tools.py -v`
Expected: PASS (6 tests: the parametrized one counts three).

- [ ] **Step 5: Make both install scripts print the report**

In `scripts/install.sh`, find the last line (unique):

```bash
"$PYTHON" -m pip install -r "$SCRIPT_DIR/../requirements.txt"
```

Replace it with:

```bash
"$PYTHON" -m pip install -r "$SCRIPT_DIR/../requirements.txt"

# Informational only: never fail the install over a missing optional tool.
echo
(cd "$SCRIPT_DIR/.." && "$PYTHON" -c "import anonymize; anonymize.report_optional_tools()") || true
```

In `scripts/install.ps1`, find the last line (unique):

```powershell
& $pythonExe -m pip install -r $requirementsPath
```

Replace it with:

```powershell
& $pythonExe -m pip install -r $requirementsPath

# Informational only: never fail the install over a missing optional tool.
Write-Host ""
Push-Location (Join-Path $PSScriptRoot "..")
try {
    & $pythonExe -c "import anonymize; anonymize.report_optional_tools()"
} catch {
    Write-Host "Could not check optional system tools: $_"
} finally {
    Pop-Location
}
```

- [ ] **Step 6: Run both scripts for real**

Run: `bash scripts/install.sh`
Expected: pip output (all "Requirement already satisfied"), then a blank line and:

```
Optional system tools:
  [ok]      Tesseract OCR (scanned PDF pages): <path to tesseract.exe>
  [ok]      RAR extraction (.rar archives): C:\Program Files\7-Zip\7z.exe
```

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install.ps1`
Expected: the same report. (On this machine the RAR line shows the 7-Zip default-folder path — that is the Task 1 fallback visible to the user. If a line says `[missing]` although the tool exists, report it as a concern.)

- [ ] **Step 7: Update `CONTRIBUTING.md`**

Find:

```markdown
Both just install `requirements.txt` with whichever Python interpreter they
find, so `pip install -r requirements.txt` works too if you already know
your interpreter is set up correctly.
```

Replace it with:

```markdown
Both install `requirements.txt` with whichever Python interpreter they find
(so `pip install -r requirements.txt` works too if you already know your
interpreter is set up correctly), then report whether the optional system
tools are available — Tesseract for scanned PDFs and a `.rar` extractor —
with the install command for your OS when one is missing. Tools installed
in their default Windows folders count as available; no PATH change needed.
```

- [ ] **Step 8: Run the full suite**

Run: `py -m pytest tests/ -q`
Expected: all pass, no regressions.

- [ ] **Step 9: Commit**

```bash
git add anonymize.py tests/test_optional_tools.py scripts/install.sh scripts/install.ps1 CONTRIBUTING.md
git commit -m "feat: report missing optional tools from the install scripts"
```

---

## Task 3: Documentation for every OS

**Files:**
- Modify: `anonymize.py` (header comment only)
- Modify: `README.md`

**Interfaces:** none.

Package IDs below were verified with `winget show --exact`: `7zip.7zip`, `RARLab.WinRAR`, `UB-Mannheim.TesseractOCR`.

- [ ] **Step 1: Update the header comment in `anonymize.py`**

Find this exact block (lines 3-9 of the file):

```python
# Optional system dependencies (beyond `pip install -r requirements.txt`):
#   - .rar archives: the 'unrar' (or 'unar'/'bsdtar') tool must be on
#     PATH. Windows: winget install RARLab.WinRAR
#   - Scanned PDFs (OCR): the Tesseract OCR engine must be installed.
#     Windows: winget install UB-Mannheim.TesseractOCR
# Both are optional: without them, the affected archive/PDF is reported
# as an error and the rest of the run continues normally.
```

Replace it with:

```python
# Optional system dependencies (beyond `pip install -r requirements.txt`):
#   - .rar archives: needs `unar` or `unrar` (bsdtar and older p7zip builds
#     fail on some RAR5 archives, so they are not recommended).
#     macOS: brew install unar. Linux: sudo apt install unar.
#     Windows: winget install 7zip.7zip (or RARLab.WinRAR); found in its
#     default install folder automatically, no PATH change needed.
#   - Scanned PDFs (OCR): the Tesseract OCR engine must be installed.
#     macOS: brew install tesseract. Linux: sudo apt install tesseract-ocr.
#     Windows: winget install UB-Mannheim.TesseractOCR (also found in its
#     default install folder automatically).
# Both are optional: without them, the affected archive/PDF is reported
# as an error and the rest of the run continues normally.
# scripts/install.sh and scripts/install.ps1 report which are missing.
```

- [ ] **Step 2: Update the dependency table in `README.md`**

Find this exact block:

```markdown
Two dependencies are optional system tools (not pip packages), needed only for specific file types:

| Needed for | Tool | Windows install |
|---|---|---|
| `.rar` archives | `unrar` (or `unar`/`bsdtar`) on PATH | `winget install RARLab.WinRAR` |
| Scanned/OCR'd PDF pages | Tesseract OCR engine | `winget install UB-Mannheim.TesseractOCR` |

Without them, the affected archive/PDF is reported as an error (and excluded from the output — see below) rather than crashing the run. If Tesseract is installed but not found, `anonymize.py` also checks the common Windows install locations directly, so it works even before you open a new terminal.
```

Replace it with:

```markdown
Two dependencies are optional system tools (not pip packages), needed only for specific file types:

| Needed for | Tool | macOS | Linux (Debian/Ubuntu) | Windows |
|---|---|---|---|---|
| `.rar` archives | `unar` or `unrar` | `brew install unar` | `sudo apt install unar` | `winget install 7zip.7zip` (or `RARLab.WinRAR`) |
| Scanned/OCR'd PDF pages | Tesseract OCR engine | `brew install tesseract` | `sudo apt install tesseract-ocr` | `winget install UB-Mannheim.TesseractOCR` |

Without them, the affected archive/PDF is reported as an error (and excluded from the output — see below) rather than crashing the run. On Windows you don't need to touch PATH: Tesseract, 7-Zip and WinRAR are also looked up in their default install folders, so they work even before you open a new terminal. `bsdtar` and the older `p7zip` shipped with some Linux distributions can fail on compressed RAR5 archives, so prefer `unar` or `unrar` there. `scripts/install.sh` / `scripts/install.ps1` print which of these tools are still missing.
```

- [ ] **Step 3: Run the full suite**

Run: `py -m pytest tests/ -q`
Expected: all pass (documentation-only change; this confirms the header edit didn't break the module).

- [ ] **Step 4: Commit**

```bash
git add anonymize.py README.md
git commit -m "docs: document optional tools for macOS, Linux and Windows"
```

---

## Task 4: The OCR test honors the product's Tesseract fallback

**Files:**
- Modify: `tests/test_pdf.py`

**Interfaces:** none.

Today `_tesseract_available()` asks `pytesseract` directly, which only looks at PATH. On a machine where Tesseract is installed in its default Windows folder but not on PATH — the exact case `locate_tesseract()` exists for — the real OCR test is silently skipped, so nothing ever proves the fallback works end to end. After this task the test runs wherever the product could run OCR.

- [ ] **Step 1: Make the availability check use the fallback**

In `tests/test_pdf.py`, find:

```python
def _tesseract_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False
```

Replace it with:

```python
def _tesseract_available() -> bool:
    try:
        import pytesseract

        located = anonymize.locate_tesseract()
        original = pytesseract.pytesseract.tesseract_cmd

        if located:
            pytesseract.pytesseract.tesseract_cmd = located

        try:
            pytesseract.get_tesseract_version()
        finally:
            # This runs at collection time. Leave the process-wide setting as
            # we found it, so the real OCR test depends on ocr_page doing its
            # own configuration (the thing the fallback exists for) rather
            # than on this probe having already done it.
            pytesseract.pytesseract.tesseract_cmd = original

        return True
    except Exception:
        return False
```

- [ ] **Step 2: Stop the fake-path test from leaking a global**

`anonymize.ocr_page` assigns `pytesseract.pytesseract.tesseract_cmd`, a process-wide setting; the existing fake-path test leaves its fake path behind for every later test. In `tests/test_pdf.py`, find:

```python
    pytesseract = pytest.importorskip("pytesseract")

    fake_tesseract = tmp_path / "tesseract.exe"
    fake_tesseract.write_bytes(b"")
```

Replace it with:

```python
    pytesseract = pytest.importorskip("pytesseract")

    monkeypatch.setattr(
        pytesseract.pytesseract,
        "tesseract_cmd",
        pytesseract.pytesseract.tesseract_cmd,
    )

    fake_tesseract = tmp_path / "tesseract.exe"
    fake_tesseract.write_bytes(b"")
```

- [ ] **Step 3: Run the PDF tests**

Run: `py -m pytest tests/test_pdf.py -v -rs`
Expected: all pass; `test_convert_pdf_to_markdown_ocrs_scanned_page` must show PASSED, not SKIPPED, on this machine (Tesseract is installed here).

- [ ] **Step 4: Run the full suite**

Run: `py -m pytest tests/ -q -rs`
Expected: all pass, no skips, no regressions.

- [ ] **Step 5: Commit**

```bash
git add tests/test_pdf.py
git commit -m "test: run the OCR test wherever the Tesseract fallback can find it"
```

---

## Task 5: Three-OS CI, a strict test runner, and a local Linux reproduction

**Files:**
- Create: `scripts/run-tests.sh`
- Create: `scripts/test-in-docker.sh`
- Create: `.github/workflows/tests.yml`
- Modify: `CONTRIBUTING.md`

**Interfaces:**
- Consumes: the install scripts from Task 2 (the workflow runs them), `locate_rar_tool`/`locate_tesseract` indirectly through the test suite.
- Produces: `scripts/run-tests.sh` (strict runner; env var `PYTHON` selects the interpreter, default `python`; extra arguments go to pytest) used by both the workflow and `scripts/test-in-docker.sh`.

- [ ] **Step 1: Create the strict test runner**

Create `scripts/run-tests.sh` (LF line endings):

```bash
#!/usr/bin/env bash
# Runs the test suite and fails if ANY test was skipped. Tests that need
# an optional system tool (Tesseract, a .rar extractor) skip themselves when
# it is missing; CI installs every such tool, so a skip there means a tool
# is missing or was not detected, and a green run would otherwise be
# claiming coverage it did not get.
#
#   PYTHON=py bash scripts/run-tests.sh          # pick the interpreter
#   bash scripts/run-tests.sh tests/test_pdf.py  # extra args go to pytest
set -eo pipefail

PYTHON="${PYTHON:-python}"
LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT

"$PYTHON" -m pytest -q -rs "$@" | tee "$LOG"

if grep -Eq '[0-9]+ skipped' "$LOG"; then
    echo >&2
    echo "ERROR: tests were skipped. Every optional dependency should be installed here, so a skip means one is missing or not detected." >&2
    exit 1
fi
```

- [ ] **Step 2: Verify the runner, including that the guard really trips**

Run: `PYTHON=py bash scripts/run-tests.sh`
Expected: all tests pass, exit code 0, no "skipped" in the summary.

Negative check — create a scratch test that skips (outside the repo, e.g. in your scratchpad directory) named `skip_probe_test.py`:

```python
import pytest


def test_probe():
    pytest.skip("probe")
```

Run: `PYTHON=py bash scripts/run-tests.sh <path-to>/skip_probe_test.py; echo "exit=$?"`
Expected: pytest reports `1 skipped`, the ERROR message above is printed, and `exit=1`.

- [ ] **Step 3: Create the local Linux reproduction script**

Create `scripts/test-in-docker.sh` (LF line endings):

```bash
#!/usr/bin/env bash
# Runs the strict test suite the way the Linux CI job does, in a throwaway
# Ubuntu container, so Linux-only failures can be reproduced locally (for
# example from Windows with Docker Desktop). Requires Docker.
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Git Bash on Windows: hand Docker a Windows-style path and stop MSYS from
# rewriting the container-side paths. Both are no-ops elsewhere.
if WIN_ROOT="$(cd "$REPO_ROOT" && pwd -W 2>/dev/null)"; then
    REPO_ROOT="$WIN_ROOT"
fi
export MSYS_NO_PATHCONV=1

docker run --rm -v "$REPO_ROOT:/src:ro" ubuntu:24.04 bash -c '
    set -e
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv tesseract-ocr unar >/dev/null
    cp -r /src /work
    cd /work
    find . -name __pycache__ -prune -exec rm -rf {} +
    python3 -m venv /venv
    /venv/bin/pip install -q -r requirements.txt
    PYTHON=/venv/bin/python bash scripts/run-tests.sh
'
```

The path handling was verified from Git Bash on the dev machine: a Windows-style path (`pwd -W`, e.g. `C:/Users/...`) with `MSYS_NO_PATHCONV=1` mounts correctly into the container. On Linux and macOS `pwd -W` fails (stderr is silenced), so the plain path is used. If the script nevertheless fails here, report it rather than reworking the approach.

- [ ] **Step 4: Run the local Linux reproduction**

Run: `bash scripts/test-in-docker.sh`
Expected: pip installs, then all tests pass with no skips (the RAR extraction test runs through `unar`, the OCR test through Tesseract), exit code 0. This takes a few minutes the first time.

- [ ] **Step 5: Create the workflow**

Create `.github/workflows/tests.yml`:

```yaml
name: tests

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: tests-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    name: pytest on ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    timeout-minutes: 20
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    env:
      # Makes the Windows `py` launcher (used by the install scripts) pick the
      # Python that setup-python installed instead of the newest preinstalled.
      PY_PYTHON: "3.11"
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install system tools (Linux)
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y tesseract-ocr unar

      - name: Install system tools (macOS)
        if: runner.os == 'macOS'
        run: brew install tesseract unar

      # 7-Zip, which handles .rar here, ships on the Windows image.
      - name: Install system tools (Windows)
        if: runner.os == 'Windows'
        shell: pwsh
        run: choco install tesseract -y --no-progress

      - name: Install Python dependencies
        run: python -m pip install -r requirements.txt

      - name: Run tests (fails if any test is skipped)
        shell: bash
        run: bash scripts/run-tests.sh

      - name: Smoke-test scripts/install.sh
        shell: bash
        run: bash scripts/install.sh

      - name: Smoke-test scripts/install.ps1 (Windows PowerShell 5.1)
        if: runner.os == 'Windows'
        shell: powershell
        run: .\scripts\install.ps1
```

- [ ] **Step 6: Lint the workflow locally**

Run (PowerShell or bash, from the repo root): `docker run --rm -v "${PWD}:/repo" -w /repo rhysd/actionlint:latest -color`
Expected: no output and exit code 0. Fix anything it reports (it also shellchecks the `run:` blocks).

- [ ] **Step 7: Document CI in `CONTRIBUTING.md`**

Append to the end of `CONTRIBUTING.md` (keep one blank line before it):

````markdown

### Tests and continuous integration

`python -m pytest` runs the suite normally; tests that need an optional
system tool (Tesseract, a `.rar` extractor) skip themselves when it is
missing. CI (`.github/workflows/tests.yml`) runs the suite on Ubuntu, macOS
and Windows with those tools installed, through `scripts/run-tests.sh`,
which additionally fails if *any* test was skipped — so a green run means
the OCR and RAR paths really ran on every OS. The same script works
locally: `bash scripts/run-tests.sh`.

To reproduce the Linux job on your machine (needs Docker; works from
Windows, macOS and Linux):

```bash
bash scripts/test-in-docker.sh
```
````

- [ ] **Step 8: Run the full suite one more time**

Run: `py -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add scripts/run-tests.sh scripts/test-in-docker.sh .github/workflows/tests.yml CONTRIBUTING.md
git commit -m "ci: run the suite on Ubuntu, macOS and Windows, failing on skipped tests"
```

---

## Task 6: Ship it and watch the first CI run (controller task)

Not for a subagent: it needs a push, a human to open the PR, and reading CI results. The controller does it after Task 5's review passes.

- [ ] **Step 1: Final local verification**

Run `PYTHON=py bash scripts/run-tests.sh` (Windows/Python 3.14, zero skips) and `bash scripts/test-in-docker.sh` (Linux, zero skips) once more on the final commit.

- [ ] **Step 2: Push and hand over the PR link**

`git push -u origin cross-platform-compat`, then give the user the `.../pull/new/cross-platform-compat` URL with a ready-to-paste title and description (`gh` is not authenticated). The PR must mention what it deliberately cannot prove locally: macOS has never been run, and the Windows job is the first run on a GitHub-hosted Windows image.

- [ ] **Step 3: Read the first CI results**

The repository is public. After the PR exists, read run and job status unauthenticated from `https://api.github.com/repos/kgorczowski/anonimize/actions/runs?branch=cross-platform-compat` and `.../actions/runs/<id>/jobs` (step names and conclusions); read failing logs through the run's page in the built-in browser (the log-download API needs auth).

- [ ] **Step 4: Triage failures forward on the same branch**

Expected first-run risks, in order of likelihood: (1) a macOS-only test failure (case-insensitive APFS, `/private/var` temp paths) — never run before; (2) the Windows job's 7-Zip being too old for compressed RAR5 (the evidence: 7-Zip 26.02 works, p7zip 16.02 does not) — fix by installing a current 7-Zip with `choco install 7zip -y` in the Windows setup step; (3) `choco install tesseract` placing the binary somewhere `TESSERACT_COMMON_PATHS` does not cover — the zero-skips guard will say so; (4) the zero-skips guard tripping on a legitimately platform-skipped test — decide per test whether the test or the guard is wrong, never by loosening the guard silently. Each fix is its own commit, re-verified locally where possible, pushed to the PR branch.

---

## Self-Review Notes

- **Spec coverage:** RAR auto-detection + fixture + real test → Task 1; optional-tool report + install-script integration → Task 2; documentation (header, README, CONTRIBUTING) → Tasks 2 and 3 and 5; OCR test fallback → Task 4; CI matrix, zero-skips rule, install-script smoke steps, `actionlint`, Linux reproduction → Task 5; verification and first-run triage → Task 6.
- **Types:** `locate_rar_tool()` returns `(setting_name, path)` or `None` everywhere; Task 2 reads `[1]`. `report_optional_tools()` is called with no arguments by both scripts. `scripts/run-tests.sh` reads `PYTHON` and forwards remaining arguments, consistently in the workflow and in `test-in-docker.sh`.
- **Resolved spec ambiguities:** the install scripts are exercised by CI smoke steps and by running them locally (Task 2 Step 6), not by pytest.
- **Known limits, stated rather than hidden:** WinRAR's `UnRAR.exe` path is by convention and was not verified here (WinRAR is not installed on the dev machine); macOS is unverifiable until CI runs.
