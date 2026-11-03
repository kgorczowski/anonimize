# Native Packages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `anonimize` as Homebrew, Scoop, winget and `.deb` packages built from one PyInstaller program per platform and published as GitHub Releases whose notes carry the install commands.

**Architecture:** Small stdlib-only scripts under `release/` freeze the program (`build.py`), wrap it as a `.deb` (`build_deb.py`), black-box test it (`smoke_test.py`) and generate every package definition plus the release notes (`render.py`, naming in `versioning.py`). A tag-triggered workflow chains them: build and smoke-test on four platforms, publish as pre-release, install through each package manager, then promote to "Latest" and commit the manifests to `main`.

**Tech Stack:** Python 3.12 (build), PyInstaller 6.22.3, pyinstaller-hooks-contrib 2026.9, `dpkg-deb`, Docker (`ubuntu:22.04` + deadsnakes), GitHub Actions (`actions/checkout@v7`, `actions/setup-python@v7`, `actions/upload-artifact@v7`, `actions/download-artifact@v8`), `gh` on runners, winget manifest schema 1.10.0.

**Spec:** `docs/superpowers/specs/2026-11-02-native-packages-design.md`

## Global Constraints

- All program code stays in `anonymize.py`; the classic CLI and interactive mode behave exactly as before.
- Never modify PATH or environment variables from our code or scripts.
- `release/*.py` use only the standard library at import time (they must run on bare Python 3.9+ in containers); `smoke_test.py fixtures` is the only code path that imports project dependencies, lazily.
- Command/package name `anonimize`; version source `__version__` in `anonymize.py`; first version `1.0.0`.
- Repo URL `https://github.com/kgorczowski/anonimize`; winget identifier `kgorczowski.anonimize`; deb maintainer `kgorczowski <kgorczowski@users.noreply.github.com>`.
- Asset names: `anonimize-<v>-windows-x64.zip`, `anonimize-<v>-macos-arm64.tar.gz`, `anonimize-<v>-macos-x64.tar.gz`, `anonimize-<v>-linux-x64.tar.gz`, `anonimize_<v>_amd64.deb`, `SHA256SUMS` (`<v>` = tag without `v`; the `.deb` control `Version` maps `-` to `~`).
- Windows build is onefile `anonimize.exe`; macOS/Linux builds are onedir `anonimize/`.
- A build containing any `replacement*.json` must fail.
- Never push a branch or tag without the user's explicit go-ahead for that push.
- Docs and release notes in English.

## Review Focus

- Source and output paths containing spaces, passed relative to a different working directory through each launcher (brew wrapper, Scoop shim, winget link, `/usr/bin` symlink), must reach the program intact → Task 4 fixtures use `client project/` and `out dir/`, and `check` runs from the fixtures folder with relative arguments.
- The program started through a symlink (`/usr/bin/anonimize` on Linux, winget's `Links` on Windows) must start normally → Task 6 asserts the symlink target and runs the check through `/usr/bin/anonimize`; Task 7's winget job runs the check through the `Links` path.
- A checker that cannot detect a leak is a fake safety net: a program that copies files raw must fail `check` → Task 4 negative test.
- Pre-release versions (`1.0.0-rc.1`) must flow through every format (deb `~`, URLs with `-`) → Tasks 2 and 3 test rc values.
- Re-running a failed release workflow for the same tag must not fail on "release already exists" → Task 7 publish step creates or updates.

---

### Task 1: Version and new CLI flags in `anonymize.py`

**Files:**
- Modify: `anonymize.py` (constants near the top; `run_interactive_mode()` hint; `main()` parser)
- Modify: `.gitignore` (add `build/`, `dist/`)
- Test: `tests/test_cli_flags.py`

**Interfaces:**
- Produces: `anonymize.__version__: str` (`"1.0.0"`); `anonymize.command_name() -> str`; CLI `--version` → stdout `anonimize <version>\n`, exit 0; CLI `--check-tools` → `report_optional_tools()` output, exit 0.

- [ ] **Step 1: Write the failing tests** in `tests/test_cli_flags.py` (use the `_run_cli`-style `monkeypatch.setattr(sys, "argv", [...])` pattern from `tests/test_integration.py`):
  - `test_version_matches_release_format`: `re.fullmatch(r"\d+\.\d+\.\d+(-rc\.\d+)?", anonymize.__version__)`.
  - `test_version_flag_prints_version_and_exits_zero`: argv `["anonymize.py", "--version"]` → `SystemExit` with code 0; stdout == `f"anonimize {anonymize.__version__}\n"`.
  - `test_check_tools_flag_prints_report_and_exits_zero`: monkeypatch `anonymize.report_optional_tools` with a stub printing `"TOOLS REPORT"`; argv `["anonymize.py", "--check-tools"]` → exit code 0 (or `None`), stdout contains `"TOOLS REPORT"`.
  - `test_command_name_in_source_mode`: `monkeypatch.delattr(sys, "frozen", raising=False)` → `command_name() == "python anonymize.py"`.
  - `test_command_name_when_frozen`: `monkeypatch.setattr(sys, "frozen", True, raising=False)` → `"anonimize"`.
  - `test_terminal_hint_names_the_frozen_command`: frozen, `monkeypatch.setattr(sys, "stdin", io.StringIO())`, call `run_interactive_mode()` → `SystemExit(1)`, stderr contains `"anonimize <source> <replacements.json>"` and not `"python anonymize.py"`.

- [ ] **Step 2: Run** `py -m pytest tests/test_cli_flags.py -q` — expected: all fail (`AttributeError: __version__` / `command_name`, unrecognized arguments).

- [ ] **Step 3: Implement**: `__version__ = "1.0.0"` after the imports; `command_name()` (returns `"anonimize"` if `getattr(sys, "frozen", False)` else `"python anonymize.py"`) used in the "needs a terminal" hint; in `main()` add `parser.add_argument("--version", action="version", version=f"anonimize {__version__}")` and `--check-tools` as an `argparse.Action` subclass with `nargs=0` that calls `report_optional_tools()` then `parser.exit()`. Help text: "Show whether the optional OCR and .rar tools are available, then exit".

- [ ] **Step 4: Run** `py -m pytest -q` — expected: whole suite passes.

- [ ] **Step 5: Commit** `feat: add --version and --check-tools, name the frozen command in hints` (stage `anonymize.py`, `.gitignore`, `tests/test_cli_flags.py`).

### Task 2: Version and asset naming (`release/versioning.py`)

**Files:**
- Create: `release/versioning.py`
- Test: `tests/test_release_versioning.py` (adds `release/` to `sys.path` at the top, like `tests/conftest.py` does for the repo root)

**Interfaces:**
- Produces:
  - `REPO_URL = "https://github.com/kgorczowski/anonimize"`, `ROOT: Path` (repo root), `PLATFORMS = ("windows-x64", "macos-arm64", "macos-x64", "linux-x64")`
  - `read_version(source: Path = ROOT / "anonymize.py") -> str` (regex `^__version__ = "([^"]+)"$`, multiline; `ValueError` if absent)
  - `check_tag(tag: str, version: str) -> None` (`ValueError` naming both when `tag != "v" + version`)
  - `is_prerelease(version: str) -> bool` (`"-" in version`)
  - `deb_version(version: str) -> str` (`-` → `~`)
  - `archive_name(version: str, platform: str) -> str`, `deb_name(version: str) -> str`, `download_url(version: str, asset: str) -> str` (`{REPO_URL}/releases/download/v{version}/{asset}`)

- [ ] **Step 1: Write the failing tests:** `read_version()` equals `anonymize.__version__`; `read_version` on a tmp file without the line raises `ValueError`; `check_tag("v1.0.0", "1.0.0")` passes, `check_tag("v1.0.1", "1.0.0")` raises with `"v1.0.1"` and `"1.0.0"` in the message; `deb_version("1.0.0-rc.1") == "1.0.0~rc.1"`, `deb_version("1.0.0") == "1.0.0"`; `is_prerelease("1.0.0-rc.1")` true, `"1.0.0"` false; `archive_name("1.0.0", "windows-x64") == "anonimize-1.0.0-windows-x64.zip"`, `archive_name("1.0.0", "macos-arm64") == "anonimize-1.0.0-macos-arm64.tar.gz"`; `deb_name("1.0.0-rc.1") == "anonimize_1.0.0-rc.1_amd64.deb"`; `download_url("1.0.0", "x.zip") == "https://github.com/kgorczowski/anonimize/releases/download/v1.0.0/x.zip"`.
- [ ] **Step 2: Run** `py -m pytest tests/test_release_versioning.py -q` — expected: fail (`ModuleNotFoundError: versioning`).
- [ ] **Step 3: Implement** `release/versioning.py` with the interfaces above.
- [ ] **Step 4: Run** the same command — expected: pass.
- [ ] **Step 5: Commit** `feat(release): version and asset naming helpers`.

### Task 3: Package definitions and release notes (`release/render.py`)

**Files:**
- Create: `release/render.py`, `release/templates/anonimize.rb`, `release/templates/release-notes.md`, `release/templates/winget/kgorczowski.anonimize.yaml`, `release/templates/winget/kgorczowski.anonimize.installer.yaml`, `release/templates/winget/kgorczowski.anonimize.locale.en-US.yaml`
- Test: `tests/test_release_render.py`

**Interfaces:**
- Consumes: everything from `versioning.py` (Task 2).
- Produces:
  - `parse_sums(text: str) -> dict[str, str]` (asset name → lowercase hex; accepts `sha256sum` output, `*` binary marker allowed)
  - `render_formula(version: str, sums: dict) -> str`
  - `render_scoop(version: str, sums: dict) -> str` (JSON, 4-space indent, trailing newline; built from a dict, no template)
  - `render_winget(version: str, sums: dict) -> dict[str, str]` (file name → content, the three `kgorczowski.anonimize*.yaml` files)
  - `write_manifests(version: str, sums: dict, out: Path) -> None` → `out/Formula/anonimize.rb`, `out/bucket/anonimize.json`, `out/release/winget/manifests/k/kgorczowski/anonimize/<version>/…`; removes other version folders there; `ValueError` naming any of the four archives missing from `sums`
  - `previous_final_tag(tags: list[str], current_tag: str) -> Optional[str]` (highest `vX.Y.Z` without `-` whose numeric tuple is below the current tag's)
  - `render_release_notes(version: str, changes: Optional[list[str]]) -> str` (`None` → "First packaged release.")
  - CLI: `render.py version` (prints `read_version()`); `render.py check-tag <tag>`; `render.py manifests --sums <file> --out <dir> [--version <v>]` (default `read_version()`; `promote` passes the tag's version because it checks out `main`, whose `__version__` may already be newer); `render.py notes --tag <tag>` (runs `git tag --list "v*"` and `git log --no-merges --format=%s <prev>..<tag>`, drops subjects starting with `release: package manifests`, prints the notes)

Template values (`string.Template`; all URLs via `download_url`):
- Formula: `class Anonimize < Formula`; `desc "Anonymize project folders before sharing them"`; `homepage`, `version`, `license "MIT"`; `on_macos do on_arm do url/sha256 end; on_intel do url/sha256 end end`; `depends_on :macos`; `depends_on "tesseract" => :recommended`; `depends_on "unar" => :recommended`; `def install` → `libexec.install Dir["*"]` and `(bin/"anonimize").write_exec_script libexec/"anonimize"`; `def caveats` → text containing `anonimize --check-tools`; `test do assert_match version.to_s, shell_output("#{bin}/anonimize --version") end`.
- Scoop: `version`, `description`, `homepage`, `license: "MIT"`, `architecture.64bit.url/hash`, `bin: "anonimize.exe"`, `suggest: {"Tesseract OCR": "main/tesseract", "7-Zip": "main/7zip"}`, `notes` containing `anonimize --check-tools`.
- winget (`ManifestVersion: 1.10.0`, schema comment lines like `winget-pkgs`): version file (`DefaultLocale: en-US`); installer file (`InstallerType: zip`, `NestedInstallerType: portable`, one `x64` installer with `NestedInstallerFiles: - RelativeFilePath: anonimize.exe` / `PortableCommandAlias: anonimize`, `InstallerUrl`, `InstallerSha256` uppercase); locale file (`Publisher: kgorczowski`, `PackageName: anonimize`, `PackageUrl`, `License: MIT`, `LicenseUrl: <repo>/blob/main/LICENSE`, `ShortDescription`, `ReleaseNotesUrl: <repo>/releases/tag/v<version>`).
- Release notes: `## Install` with macOS (brew tap + install), Windows (scoop bucket add + install), Debian/Ubuntu (`curl -LO <deb url>` + `sudo apt install ./<deb name>`), "Other Linux" (tar.gz), update commands (`brew upgrade anonimize`, `scoop update anonimize`, install the new `.deb`), `anonimize --check-tools`; `## Verify` pointing to `SHA256SUMS` (`sha256sum -c SHA256SUMS --ignore-missing`); `## Changes` with `- <subject>` lines or "First packaged release.".

- [ ] **Step 1: Write the failing tests** (version `"1.2.3"` and `"1.0.0-rc.1"`, sums built from fake 64-hex strings per asset):
  - `test_parse_sums_reads_sha256sum_output` (two lines incl. a `*name` entry).
  - `test_formula_points_each_cpu_at_its_asset`: arm/intel URL + sha present, `version "1.2.3"`, both `:recommended` lines, `write_exec_script`, `--check-tools`.
  - `test_scoop_manifest`: `json.loads` → `version`, `architecture["64bit"]` url/hash, `bin == "anonimize.exe"`, suggest values, `"--check-tools" in notes`.
  - `test_winget_manifests`: exactly the three file names; each has `PackageIdentifier: kgorczowski.anonimize`, `PackageVersion: 1.2.3`, `ManifestVersion: 1.10.0`; installer has `NestedInstallerType: portable`, `RelativeFilePath: anonimize.exe`, `PortableCommandAlias: anonimize`, the URL and the uppercase hash.
  - `test_write_manifests_keeps_only_the_current_winget_version`: pre-create `…/anonimize/0.9.0/old.yaml` → afterwards only `1.2.3/` exists, plus `Formula/anonimize.rb` and `bucket/anonimize.json`.
  - `test_write_manifests_rejects_sums_missing_an_archive`: drop `macos-x64` → `ValueError` containing `anonimize-1.2.3-macos-x64.tar.gz`.
  - `test_previous_final_tag`: `(["v0.9.0", "v1.0.0-rc.1", "v1.0.0", "v1.1.0"], "v1.1.0") → "v1.0.0"`; `(["v1.0.0-rc.1"], "v1.0.0") → None`; `(["v1.0.0", "v1.0.0-rc.2"], "v1.0.0-rc.2") → None`; `(["v1.0.0", "v1.0.1-rc.1"], "v1.0.1-rc.1") → "v1.0.0"`.
  - `test_release_notes_for_a_prerelease`: version `"1.0.0-rc.1"`, `None` → contains `brew tap kgorczowski/anonimize https://github.com/kgorczowski/anonimize`, `scoop bucket add anonimize https://github.com/kgorczowski/anonimize`, `sudo apt install ./anonimize_1.0.0-rc.1_amd64.deb`, `releases/download/v1.0.0-rc.1/anonimize_1.0.0-rc.1_amd64.deb`, `anonimize --check-tools`, `First packaged release.`
  - `test_release_notes_list_changes`: `["fix: a", "feat: b"]` → `- fix: a` and `- feat: b`, no "First packaged release.".
- [ ] **Step 2: Run** `py -m pytest tests/test_release_render.py -q` — expected: fail (module missing).
- [ ] **Step 3: Implement** `release/render.py` and the templates.
- [ ] **Step 4: Run** the same command — expected: pass.
- [ ] **Step 5: Validate the winget output with the real tool** (read-only, changes no settings): write manifests for `1.0.0` with fake sums into the scratchpad, then `winget validate --manifest <dir>/release/winget/manifests/k/kgorczowski/anonimize/1.0.0` — expected: "Manifest validation succeeded." (warnings about unreachable URLs are acceptable; errors are not).
- [ ] **Step 6: Commit** `feat(release): render Homebrew, Scoop and winget manifests and release notes`.

### Task 4: Black-box smoke test (`release/smoke_test.py`)

**Files:**
- Create: `release/smoke_test.py`
- Test: `tests/test_release_smoke.py`

**Interfaces:**
- Produces:
  - `make_fixtures(root: Path) -> None` — creates `root/client project/…`, `root/replacements.json` (`{"AcmeCorp": "Company1"}`) and `root/expectations.json`; imports `docx`, `openpyxl`, `pptx`, `pymupdf`, `PIL`, `py7zr` inside the function only.
  - `run_checks(command: list[str], fixtures: Path, version: str) -> list[str]` — returns failure messages (empty = pass); resolves `command[0]` with `shutil.which` when it is a bare name; every subprocess gets `stdin=DEVNULL`, captured text output, `timeout=600`.
  - CLI: `smoke_test.py fixtures <dir>`; `smoke_test.py check --fixtures <dir> --version <v> -- <command...>` (prints each failure, exit 1 if any, else prints "smoke test passed" and exits 0).

Fixture tree under `client project/` → expected output (relative to the output dir):

| Source | Content | Expected output |
|---|---|---|
| `AcmeCorp/notes.txt` | `Contact AcmeCorp: jan.kowalski@example.com, PESEL 44051401458` | `Company1/notes.txt` containing `Company1` |
| `acmecorp_summary.txt` | `Summary for ACMECORP` | `Company1_summary.txt` |
| `docs/report.docx` / `budget.xlsx` / `slides.pptx` / `contract.pdf` | text `AcmeCorp …` | `docs/report.md`, `docs/budget.md`, `docs/slides.md`, `docs/contract.md` |
| `docs/scan.pdf` | image-only page, 600×200 white image with `SCANNED TEXT` drawn at (20, 80), as in `tests/test_pdf.py` | `docs/scan.md` containing `SCANNED` |
| `archives/bundle.zip`, `archives/data.tar.gz`, `archives/packed.7z` | `inner_zip.txt`, `inner_tar.txt`, `inner_7z.txt` with `AcmeCorp …` | `archives/bundle/inner_zip.txt`, `archives/data/inner_tar.txt`, `archives/packed/inner_7z.txt` |
| `archives/sample_rar5_compressed.rar` | copy of `tests/fixtures/sample_rar5_compressed.rar` | `archives/sample_rar5_compressed/hello.txt` containing `[EMAIL]` |
| `images/logo.png` | solid red 64×32 PNG | `images/logo.png`, bytes differ from the source |

`expectations.json` keys: `must_exist` (list), `must_contain` (path → substring), `changed` (list), `forbidden` (`["acmecorp", "jan.kowalski@example.com", "44051401458", "jan@example.com"]`).

`run_checks` asserts, in order: `--version` stdout contains `anonimize <version>`; `--check-tools` exits 0 with two `[ok]` lines and no `[missing]`; no arguments → non-zero exit and stderr contains `Interactive mode needs a terminal`; the full run, executed with `cwd=fixtures` and arguments `client project`, `replacements.json`, `--output <tmp>/out dir`, exits 0 and stdout has a line matching `^Errors\s*:\s*0$`; every `must_exist` path exists; every `must_contain` holds; every `changed` file differs from its source; no forbidden string occurs (case-insensitive) in any output path, nor in the content of any output `.txt`/`.md` file. On a failed run, include the last 20 lines of the program's output in the message.

- [ ] **Step 1: Write the failing tests:**
  - `test_smoke_check_passes_for_the_source_program`: `make_fixtures(tmp_path / "fx")`, then `run_checks([sys.executable, str(ROOT / "anonymize.py")], tmp_path / "fx", anonymize.__version__) == []`. Skip (like `tests/test_pdf.py`) when Tesseract or a RAR tool is unavailable — `scripts/run-tests.sh` turns that skip into a CI failure.
  - `test_smoke_check_catches_a_program_that_copies_files_raw`: write a stub script to `tmp_path / "leaky.py"` that answers `--version` (prints `anonimize <version>`), `--check-tools` (two `[ok]` lines), no args (prints the terminal message to stderr, exits 1), and otherwise copies the source tree to `--output` unchanged and prints `Errors            : 0`. Assert the failures mention `acmecorp`.
- [ ] **Step 2: Run** `py -m pytest tests/test_release_smoke.py -q` — expected: fail (module missing).
- [ ] **Step 3: Implement** `release/smoke_test.py`.
- [ ] **Step 4: Run** the same command — expected: pass. Then `py -m pytest -q` — whole suite passes.
- [ ] **Step 5: Commit** `feat(release): black-box smoke test for built programs`.

### Task 5: Freezing (`release/build.py`) and the local Windows build

**Files:**
- Create: `release/build.py`, `release/requirements-build.txt` (`pyinstaller==6.22.3`, `pyinstaller-hooks-contrib==2026.9`)
- Test: `tests/test_release_build.py`

**Interfaces:**
- Consumes: `versioning.read_version`, `archive_name`, `ROOT`.
- Produces:
  - `current_platform() -> str` (from `sys.platform` + `platform.machine()`: `win32`+`AMD64` → `windows-x64`; `darwin`+`arm64` → `macos-arm64`; `darwin`+`x86_64` → `macos-x64`; `linux`+`x86_64` → `linux-x64`; anything else → `SystemExit` with a message)
  - `forbidden_files(bundle: Path) -> list[Path]` (every `replacement*.json` below `bundle`, case-insensitive)
  - `program_path(platform: str) -> Path` (`build/pyinstaller/dist/anonimize.exe` on Windows, `build/pyinstaller/dist/anonimize/anonimize` otherwise)
  - CLI `py release/build.py`: runs `sys.executable -m PyInstaller anonymize.py --name anonimize --console --noconfirm --clean --distpath build/pyinstaller/dist --workpath build/pyinstaller/work --specpath build/pyinstaller` plus `--onefile` (Windows) or `--onedir`; fails if `forbidden_files` is non-empty; writes `dist/<archive_name>` (zip with `anonimize.exe` at the root, or tar.gz with `anonimize/` at the root, file modes kept); prints the program and archive paths.

- [ ] **Step 1: Write the failing tests:** `forbidden_files` finds `x/replacements.json`, `replacement.json`, `REPLACEMENTS.JSON` and ignores `notes.json`; `current_platform` for the four mappings and an unsupported one (monkeypatch `sys.platform` and `build.platform.machine`).
- [ ] **Step 2: Run** `py -m pytest tests/test_release_build.py -q` — expected: fail.
- [ ] **Step 3: Implement** `release/build.py` and `release/requirements-build.txt`.
- [ ] **Step 4: Run** the same command — expected: pass.
- [ ] **Step 5: Build locally on Windows** in a throwaway venv: `py -m venv build/venv`, then `build/venv/Scripts/python -m pip install -r requirements.txt -r release/requirements-build.txt`, then `build/venv/Scripts/python release/build.py` — expected: `dist/anonimize-1.0.0-windows-x64.zip` exists.
- [ ] **Step 6: Smoke-test the frozen program**: `build/venv/Scripts/python release/smoke_test.py fixtures build/fx`, then `… check --fixtures build/fx --version 1.0.0 -- build/pyinstaller/dist/anonimize.exe` — expected: `smoke test passed`. If a module is reported missing, add the narrowest PyInstaller option for exactly that package (`--hidden-import`, `--collect-submodules` or `--copy-metadata`) with a comment saying which failure it fixes, rebuild and re-run.
- [ ] **Step 7: Commit** `feat(release): freeze the program with PyInstaller and archive it per platform`.

### Task 6: Linux build, `.deb`, clean-install tests (Docker)

**Files:**
- Create: `release/build_deb.py`, `release/build-linux-in-docker.sh`, `release/test-deb-in-docker.sh`
- Test: `tests/test_release_deb.py`

**Interfaces:**
- Consumes: `versioning` (Task 2), `build.program_path` layout (Task 5), `smoke_test` CLI (Task 4).
- Produces:
  - `control_file(version: str, installed_size_kib: int) -> str` — fields `Package: anonimize`, `Version: <deb_version>`, `Architecture: amd64`, `Maintainer: kgorczowski <kgorczowski@users.noreply.github.com>`, `Installed-Size`, `Depends: libc6 (>= 2.35)`, `Recommends: tesseract-ocr, unar`, `Section: utils`, `Priority: optional`, `Homepage: <REPO_URL>`, `Description: Anonymize project folders before sharing them` plus a one-paragraph extended description (each line indented by one space); ends with a newline.
  - CLI `python release/build_deb.py` (Linux only): stages `usr/lib/anonimize/` (copy of the onedir build), relative symlink `usr/bin/anonimize -> ../lib/anonimize/anonimize`, `usr/share/doc/anonimize/copyright` (= `LICENSE`), `DEBIAN/control`; runs `dpkg-deb --build --root-owner-group <stage> dist/<deb_name>`.
  - `release/build-linux-in-docker.sh`: in `ubuntu:22.04`, installs `python3.12 python3.12-venv python3.12-dev` from `ppa:deadsnakes/ppa` plus `binutils tesseract-ocr unar`; copies the working tree to `/work` (dropping `build/`, `dist/`, `__pycache__`); venv; installs both requirements files; runs `build.py`, `build_deb.py`, `smoke_test.py fixtures`, and `smoke_test.py check` against the onedir program; copies the assets to the host's `dist/` and the fixtures to `build/fixtures/smoke-fixtures/`. Same Git Bash path handling as `scripts/test-in-docker.sh`.
  - `release/test-deb-in-docker.sh <image>`: in a fresh `<image>`, `apt-get install -y ./dist/anonimize_*_amd64.deb python3`, asserts `readlink -f /usr/bin/anonimize` is `/usr/lib/anonimize/anonimize`, then runs `smoke_test.py check --fixtures build/fixtures/smoke-fixtures --version <render.py version> -- /usr/bin/anonimize`.

- [ ] **Step 1: Write the failing tests** for `control_file`: version `1.0.0-rc.1` gives `Version: 1.0.0~rc.1`; every field above is present; the extended-description lines start with a space; the text ends with `\n`.
- [ ] **Step 2: Run** `py -m pytest tests/test_release_deb.py -q` — expected: fail.
- [ ] **Step 3: Implement** `release/build_deb.py` and both shell scripts (LF line endings are enforced by `.gitattributes`).
- [ ] **Step 4: Run** the same command — expected: pass.
- [ ] **Step 5: Build in Docker** (Git Bash): `bash release/build-linux-in-docker.sh` — expected: ends with `smoke test passed`; `dist/` contains `anonimize-1.0.0-linux-x64.tar.gz` and `anonimize_1.0.0_amd64.deb`.
- [ ] **Step 6: Clean installs**: `bash release/test-deb-in-docker.sh ubuntu:22.04`, then `ubuntu:24.04`, then `debian:12` — expected: `smoke test passed` in each (this also proves apt installed the recommended `tesseract-ocr` and `unar`, since `--check-tools` must report `[ok]`).
- [ ] **Step 7: Commit** `feat(release): build the Linux program and .deb in ubuntu:22.04 and test clean installs`.

### Task 7: Release workflow

**Files:**
- Create: `.github/workflows/release.yml`
- Modify: `.github/workflows/tests.yml` (add `workflow_call:` to `on:`)

**Interfaces:**
- Consumes: CLIs from Tasks 3–6; the `program_path` locations from Task 5.

Workflow shape (`permissions: contents: read` at the top; `concurrency: release-${{ github.ref }}`, cancelling only for pull requests):
- Triggers: `push: tags: ["v*"]`; `pull_request: paths: [anonymize.py, requirements.txt, "release/**", .github/workflows/release.yml]`; `workflow_dispatch`.
- `check-version` (tags only): `python3 release/render.py check-tag "$GITHUB_REF_NAME"`.
- `tests` (tags only): `uses: ./.github/workflows/tests.yml`, `needs: check-version`.
- `build` (matrix `windows-latest`/`windows-x64`, `macos-15`/`macos-arm64`, `macos-15-intel`/`macos-x64`; `if: ${{ !failure() && !cancelled() }}` so it runs when the tag-only jobs are skipped): setup-python 3.12; system tools exactly as in `tests.yml`; install both requirements files; `python release/build.py`; `smoke_test.py fixtures "$RUNNER_TEMP/fx"`; `smoke_test.py check` against the platform's program path; upload `dist/*` as artifact `asset-<platform>`.
- `build-linux` (`ubuntu-24.04`, same `if`): `bash release/build-linux-in-docker.sh`; upload `dist/*` as `asset-linux-x64`, `build/fixtures/smoke-fixtures` as `smoke-fixtures`.
- `deb` (`needs: build-linux`, matrix image `ubuntu:22.04`/`ubuntu:24.04`/`debian:12`): download `asset-linux-x64` into `dist/` and `smoke-fixtures` into `build/fixtures/smoke-fixtures`; `bash release/test-deb-in-docker.sh "$image"`.
- `publish` (tags only, `needs: [build, build-linux, deb]`, `permissions: contents: write`, checkout with `fetch-depth: 0`): download all `asset-*` merged into `dist/`; `(cd dist && sha256sum * > SHA256SUMS)`; `python3 release/render.py notes --tag "$GITHUB_REF_NAME" > notes.md`; if `gh release view` finds the tag, `gh release upload --clobber` and `gh release edit --notes-file`, else `gh release create "$GITHUB_REF_NAME" dist/* --prerelease --title "anonimize <version>" --notes-file notes.md`; upload `dist/SHA256SUMS` as artifact `sums`.
- `verify-brew` (tags only, `needs: publish`, matrix `macos-latest`, `macos-15-intel`): setup-python; download `sums` + `smoke-fixtures`; `render.py manifests --sums … --out "$RUNNER_TEMP/m"`; `brew tap-new --no-git local/anonimize`; copy the formula into `$(brew --repository local/anonimize)/Formula/`; `brew install local/anonimize/anonimize`; `brew test local/anonimize/anonimize`; `smoke_test.py check … -- anonimize`.
- `verify-scoop` (tags only, `needs: publish`, `windows-latest`): setup-python; `choco install tesseract -y --no-progress`; render manifests; install Scoop with `-RunAsAdmin`; add `~\scoop\shims` to `$GITHUB_PATH`; `scoop install "$RUNNER_TEMP\m\bucket\anonimize.json"`; in the next step `smoke_test.py check … -- anonimize`.
- `verify-winget` (tags only, `needs: publish`, `windows-latest`): setup-python; Tesseract via choco; render manifests; `winget validate --manifest <dir>`; `winget settings --enable LocalManifestFiles`; `winget install --manifest <dir> --accept-source-agreements --accept-package-agreements --disable-interactivity`; `smoke_test.py check … -- "$env:LOCALAPPDATA\Microsoft\WinGet\Links\anonimize.exe"`.
- `promote` (only `startsWith(github.ref, 'refs/tags/') && !contains(github.ref_name, '-')`, `needs: [verify-brew, verify-scoop, verify-winget]`, `permissions: contents: write`): `gh release edit "$GITHUB_REF_NAME" --prerelease=false --latest`; checkout `main` with `fetch-depth: 0`; download `sums`; `render.py manifests --sums … --out . --version "${GITHUB_REF_NAME#v}"`; commit `Formula/ bucket/ release/winget/` as `github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>` with the message `release: package manifests for <tag>`; push, and on rejection `git pull --rebase origin main` then push again (up to 3 attempts).

- [ ] **Step 1: Write** `release.yml` and the `tests.yml` change as above. The workflow's comments explain the non-obvious lines (the `!failure()` pattern, why winget's check runs through `Links`, why `promote` skips pre-releases).
- [ ] **Step 2: Lint** with `docker run --rm -v "<worktree>:/repo" -w /repo rhysd/actionlint:<latest 1.7.x tag> -color` — expected: no findings.
- [ ] **Step 3: Commit** `ci: build, test, publish and verify native packages on tags`.

### Task 8: Documentation

**Files:**
- Modify: `README.md` (new "Installation" section after the intro; usage shows `anonimize …` next to `python anonymize.py …`; current requirements/pip text becomes "From source")
- Modify: `CONTRIBUTING.md` (new "Releasing" section)

- [ ] **Step 1: README**: release badge `[![Latest release](https://img.shields.io/github/v/release/kgorczowski/anonimize)](https://github.com/kgorczowski/anonimize/releases/latest)`; per-OS commands from Task 3's notes (with "download the `.deb` from the latest release" instead of a fixed version); updating; `anonimize --check-tools`; "Manual download" (archives on the release page; macOS: `xattr -d com.apple.quarantine` on the extracted folder; Windows Scoop/winget note that Tesseract/7-Zip are suggested, not installed); `anonimize --version`.
- [ ] **Step 2: CONTRIBUTING "Releasing"**: bump `__version__`, commit, `git tag vX.Y.Z`, `git push origin main vX.Y.Z`; rehearse with `X.Y.Z-rc.N` (version and tag together); what the workflow does and that only verified versions become "Latest"; `git pull` afterwards (the workflow commits the manifests); re-running a failed job is safe; local reproduction (`bash release/build-linux-in-docker.sh`, `bash release/test-deb-in-docker.sh <image>`); submitting `release/winget/manifests/…` to `microsoft/winget-pkgs` by copying the folder into a fork.
- [ ] **Step 3: Run** `py -m pytest -q` — expected: pass (docs-only change, sanity).
- [ ] **Step 4: Commit** `docs: explain installing packages and cutting releases`.

### Task 9: Branch review, push and pull-request dry run

- [ ] **Step 1: Whole-branch review** of `git diff main...native-packages` by a fresh reviewer; fix findings with their own commits.
- [ ] **Step 2: Full local verification**: `py -m pytest -q`; Windows build + smoke test (Task 5 steps 5–6); `bash release/build-linux-in-docker.sh`; the three `.deb` tests.
- [ ] **Step 3: Ask the user** to push `native-packages`; after their yes, `git push -u origin native-packages` and hand over the `.../pull/new/native-packages` link with a title and description.
- [ ] **Step 4: Read the PR's `release` and `tests` runs** through the unauthenticated API (`actions/runs?branch=native-packages`, jobs, check-run annotations); fix failures with follow-up commits (each push confirmed by the user).
- [ ] **Step 5: After the merge**, propose the rehearsal: `__version__ = "1.0.0-rc.1"`, tag `v1.0.0-rc.1` — pushed only with the user's go-ahead — then `1.0.0`.
