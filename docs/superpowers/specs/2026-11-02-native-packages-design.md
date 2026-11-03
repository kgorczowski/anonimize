# Native Packages Design

## Goal

Let people install `anonimize` with their operating system's package
manager — no `git clone`, no Python — and let them see which versions exist
and how to install each one. Every published version is built, tested as
the frozen program users will actually run, and installed through every
package manager by CI before it becomes the latest release.

## Decisions (made with the user, 2026-10-13 and 2026-11-02)

- **Native package managers:** Homebrew (macOS), Scoop and winget
  (Windows), `.deb` (Debian/Ubuntu).
- **Self-hosted channels**, everything served from this repository: no
  extra repositories, no tokens, no secrets. The winget manifest is
  generated and validated on every release; submitting it to
  `microsoft/winget-pkgs` is a manual step the user takes whenever they
  choose.
- **Linux:** a `.deb` attached to the GitHub Release (no apt repository, no
  `.rpm`).
- **One frozen program per platform** (PyInstaller); the packages only wrap
  it, no package manager resolves Python dependencies. Rejected: letting
  each manager resolve the Python dependencies itself (three diverging
  dependency worlds, PyMuPDF built from source under Homebrew, distro
  `python3-*` versions that differ or are missing), and native packages that
  create a venv from a PyPI wheel at install time (network access during
  install, breaks offline or behind a proxy, not reproducible).
- **Versions are published as GitHub Releases.** Every release page, the
  README and the package managers' post-install notes say how to install.
- **Name:** command and package `anonimize`, like the repository; the
  source file stays `anonymize.py`. First version `1.0.0`.

## Facts this design rests on (checked 2026-11-02)

- `anonymize.py` freezes without restructuring: concurrency is threads only
  (`ThreadPoolExecutor`; no `multiprocessing`, so no `freeze_support()`),
  every third-party import is a static `import` statement inside a function
  (PyInstaller's bytecode scan finds those), and nothing reads files
  relative to `__file__`.
- A run exits with code 0 even when files failed; failures show up only in
  the summary line `Errors            : N`. Automated checks must read that
  line, not the exit code.
- With no arguments and no TTY, `run_interactive_mode()` imports
  `questionary` first and only then prints "Interactive mode needs a
  terminal". Getting that message therefore proves `questionary` is bundled.
- On Windows, starting a PyInstaller *onedir* executable through a symlink
  fails with "Error loading Python DLL" (pyinstaller/pyinstaller#5575).
  winget installs portable apps by linking them into its `Links` folder, so
  the Windows build must be *onefile*. Scoop starts programs through shim
  executables rather than symlinks.
- GitHub runner images: `ubuntu-22.04` is deprecated (since 2026-09-17,
  unsupported from 2027-04-17); `macos-latest` has been macOS 26 on arm64
  since 2026-06; `macos-15-intel` is the remaining Intel image; winget is
  preinstalled on `windows-2025` (= `windows-latest`).
- `main` is not branch-protected, so a workflow can push to it with
  `GITHUB_TOKEN`.
- A Homebrew tap and a Scoop bucket can live in any Git repository:
  `brew tap <user>/<name> <url>` reads `Formula/`, and
  `scoop bucket add <name> <url>` reads `bucket/`.

## Design

### 1. Program changes (`anonymize.py`, still one file)

- `__version__ = "1.0.0"` is the single source of the version.
- `--version` prints `anonimize 1.0.0` and exits 0.
- `--check-tools` prints the existing `report_optional_tools()` report and
  exits 0.
- Both flags work without the positional arguments (argparse actions that
  exit, like the built-in `version` action).
- The "Interactive mode needs a terminal" hint names the command that is
  actually running: `anonimize <source> <replacements.json>` in the frozen
  program (`sys.frozen`), `python anonymize.py <source> <replacements.json>`
  otherwise.
- Nothing else changes: the classic CLI, interactive mode, output layout and
  the exclude-on-failure rule stay as they are.

### 2. Build (`release/`)

A new `release/` directory holds everything that produces a release. It is
not called `packaging/`, because that name would shadow the `packaging`
library that pip and pytest import.

| File | Purpose |
|---|---|
| `release/requirements-build.txt` | PyInstaller, pinned to an exact version |
| `release/build.py` | Freezes `anonymize.py` for the current OS and writes the archive to `dist/` |
| `release/build_deb.py` | Turns the Linux build into a `.deb` with `dpkg-deb` |
| `release/build-linux-in-docker.sh` | Runs the Linux build and the `.deb` build in `ubuntu:22.04`; used by CI and locally |
| `release/smoke_test.py` | Black-box test of a built program (section 6) |
| `release/render.py` | Writes the Homebrew formula, the Scoop manifest, the winget manifests and the release notes from templates |
| `release/templates/` | The templates `render.py` fills in |

Build settings:

- PyInstaller with Python 3.12 on every platform. Windows: onefile
  `anonimize.exe`. macOS and Linux: onedir folder `anonimize/` (faster
  start, nothing unpacked per run).
- Linux builds run in an `ubuntu:22.04` container (glibc 2.35) with
  Python 3.12 from the deadsnakes PPA, so the program runs on Ubuntu 22.04+
  and Debian 12+. macOS builds run on `macos-15` (arm64) and
  `macos-15-intel` (x64).
- Only `anonymize.py` and what it imports go into the bundle. `build.py`
  fails the build if a file named `replacement*.json` or
  `replacements*.json` ended up inside it.
- `build/` and `dist/` are gitignored.

### 3. Release assets

For version `X.Y.Z`, the GitHub Release carries:

| Asset | Contents |
|---|---|
| `anonimize-X.Y.Z-windows-x64.zip` | `anonimize.exe` |
| `anonimize-X.Y.Z-macos-arm64.tar.gz` | `anonimize/` folder |
| `anonimize-X.Y.Z-macos-x64.tar.gz` | `anonimize/` folder |
| `anonimize-X.Y.Z-linux-x64.tar.gz` | `anonimize/` folder, for non-Debian distributions |
| `anonimize_X.Y.Z_amd64.deb` | Debian/Ubuntu package |
| `SHA256SUMS` | Checksums of all of the above |

### 4. Package definitions

All of them are generated by `release/render.py` from the release's version
and checksums and are never edited by hand.

**Homebrew: `Formula/anonimize.rb`** (macOS only)

- `url` and `sha256` per CPU through `on_arm` / `on_intel`.
- `depends_on "tesseract" => :recommended` and
  `depends_on "unar" => :recommended`: installed by default, skipped with
  `--without-tesseract` / `--without-unar`.
- Installs the folder into `libexec` and creates `bin/anonimize` with
  `write_exec_script`, a wrapper script, so nothing depends on how the
  PyInstaller bootloader resolves symlinks on macOS.
- `caveats` points to `anonimize --check-tools`; `test do` runs
  `anonimize --version`.
- For users: `brew tap kgorczowski/anonimize https://github.com/kgorczowski/anonimize`,
  then `brew install anonimize`.

**Scoop: `bucket/anonimize.json`**

- Zip URL and hash, `bin: anonimize.exe`, `suggest` for Tesseract and
  7-Zip, `notes` pointing to `anonimize --check-tools`.
- For users: `scoop bucket add anonimize https://github.com/kgorczowski/anonimize`,
  then `scoop install anonimize`.

**winget: `release/winget/manifests/k/kgorczowski/anonimize/X.Y.Z/`**

- Multi-file manifest (version, installer, defaultLocale) with the
  identifier `kgorczowski.anonimize`, `InstallerType: zip`, nested
  `portable` installer `anonimize.exe`, and the command alias `anonimize`.
- The folder mirrors the `winget-pkgs` layout, so a later submission is a
  copy. Only the latest version is kept.

**Debian/Ubuntu: `anonimize_X.Y.Z_amd64.deb`**

- The program goes in `/usr/lib/anonimize/`, with a symlink at
  `/usr/bin/anonimize` (on Linux the bootloader finds its real location
  through `/proc/self/exe`). The license goes in
  `/usr/share/doc/anonimize/copyright`.
- `Depends: libc6 (>= 2.35)`; `Recommends: tesseract-ocr, unar` (apt
  installs recommended packages by default).
- `Maintainer: kgorczowski <kgorczowski@users.noreply.github.com>`;
  `Homepage:` is the repository.
- For users: download it, then `sudo apt install ./anonimize_X.Y.Z_amd64.deb`.

**Versions.** The package version is the tag without the leading `v`. A
pre-release tag such as `v1.0.0-rc.1` becomes `1.0.0~rc.1` in the `.deb`,
so that it sorts before `1.0.0`.

Nothing on our side modifies PATH. The Homebrew `bin` folder, Scoop shims,
winget's `Links` folder and `/usr/bin` are each package manager's own
mechanism.

### 5. Release workflow (`.github/workflows/release.yml`)

Triggers:

- **Tag `v*`**: a full release.
- **Pull requests** that touch `anonymize.py`, `requirements.txt`,
  `release/**` or the workflow itself: jobs 3 and 4 only (build and test),
  nothing published. This proves packaging changes before they are merged.
- **`workflow_dispatch`**: the same dry run, on demand.

Jobs:

1. **check-version** (tags): the tag must equal `v` + `__version__`, read
   from the file with a regex. This also applies to pre-releases
   (`__version__ = "1.0.0-rc.1"` for tag `v1.0.0-rc.1`). On a mismatch the
   job fails before anything is built.
2. **tests** (tags): the existing suite on all three OSes. `tests.yml` gains
   a `workflow_call` trigger and is reused, not copied. Pull requests
   already run `tests.yml` on their own.
3. **build** (matrix: `windows-latest`, `macos-15`, `macos-15-intel`, and
   the Linux container): install `requirements.txt` and
   `release/requirements-build.txt`, plus Tesseract and a RAR tool as in
   `tests.yml`; freeze; archive; create the smoke-test fixtures; run
   `release/smoke_test.py` against the built program. Upload the assets and
   the fixtures as workflow artifacts.
4. **deb**: build the `.deb`, install it with `apt install ./….deb` into
   fresh `ubuntu:22.04`, `ubuntu:24.04` and `debian:12` containers, and run
   the smoke test there. `python3` is installed in those containers only to
   run the checker; the package itself does not need it.
5. **publish** (tags, `contents: write`): create the GitHub Release as a
   **pre-release**, with all assets, `SHA256SUMS` and the generated notes.
6. **verify-install** (tags): render the manifests from the published
   assets, install through each package manager, then run the smoke test
   against the installed `anonimize` command:
   - `brew` on `macos-latest` (arm64, macOS 26) and on `macos-15-intel`,
     through a local tap holding the rendered formula;
   - Scoop on `windows-latest`, from the rendered manifest;
   - winget on `windows-latest`: `winget validate`, then
     `winget install --manifest`. The runner is an administrator, so
     `LocalManifestFiles` can be enabled there. This never happens on a
     user's machine.
7. **promote** (final tags only, i.e. without `-`): mark the release as a
   regular release and as "Latest", then commit `Formula/anonimize.rb`,
   `bucket/anonimize.json` and `release/winget/…` to `main` as
   `github-actions[bot]` ("release: package manifests for vX.Y.Z"). If
   `main` moved in the meantime, fetch, rebase that single commit and push
   again.

The result: `brew upgrade`, `scoop update` and the "Latest" marker only
ever reach versions that installed and ran cleanly through every package
manager. A failure anywhere leaves a pre-release that nobody receives
automatically; the fix ships as the next patch version. Pre-release tags
(`-rc.N`) stop after job 6, so the whole pipeline can be rehearsed without
touching `main`.

### 6. Smoke test of the built program (`release/smoke_test.py`)

It has two subcommands.

`fixtures <dir>` needs the project's Python dependencies and runs in the
build job. It creates a source tree and a replacements file that cover every
processing path:

- a folder and a file named after a dictionary term;
- text containing the term, an e-mail address and a PESEL;
- `.docx`, `.xlsx` and `.pptx` files;
- a text PDF and an image-only PDF page (OCR);
- `.zip`, `.tar.gz` and `.7z` archives containing text with the term;
- the existing RAR5 fixture `tests/fixtures/sample_rar5_compressed.rar`;
- a `logo.png`.

`check <command> <fixtures-dir>` uses only the standard library, so it also
runs in the bare `.deb` containers and after package-manager installs. It
runs the program and requires all of the following:

- `--version` prints the expected version;
- `--check-tools` reports both tools as `[ok]`;
- running without arguments and without a TTY prints the "needs a
  terminal" message (proves `questionary` is bundled);
- a full run exits 0 with `Errors            : 0` in the summary;
- the expected outputs exist: a `.md` for each Office and PDF file, the
  extracted archive contents including the RAR's text, and the blacked-out
  logo;
- no output file name or content contains a dictionary key
  (case-insensitive), the e-mail address or the PESEL.

This is where a module that PyInstaller failed to bundle shows up. The tool
would exclude the affected file and count an error rather than crash, which
is why the check reads the error count and not just the exit code.

### 7. Where versions and install instructions appear

- **GitHub Releases** (`/releases`, `/releases/latest`): one page per
  version. `release/render.py` generates the notes:
  - *Install*: the commands from section 4 with this version's file names,
    the upgrade commands, and `anonimize --check-tools`;
  - *Verify*: a pointer to `SHA256SUMS`;
  - *Changes*: commit subjects since the previous final tag, as written
    (`feat:`, `fix:`, `docs:`). The first release says "First packaged
    release" instead of listing the whole history.
- **README**: a new "Installation" section at the top with:
  - a release badge (shields.io) and a link to `/releases/latest`;
  - the three package-manager commands and how to update;
  - `anonimize --check-tools`;
  - a short "Manual download" note: macOS quarantines files downloaded in a
    browser, so they need `xattr -d com.apple.quarantine`.

  The existing `pip install -r requirements.txt` route stays, as "From
  source". Usage examples show `anonimize …` next to
  `python anonymize.py …`.
- **In the program:** `anonimize --version`.
- **In the package managers:** `brew info`, `scoop info` and `apt show` show
  the version, description and homepage. Homebrew `caveats` and Scoop
  `notes` print the `--check-tools` hint after installing.
- **CONTRIBUTING**: a new "Releasing" section covering:
  - the release itself: bump `__version__`, commit, tag `vX.Y.Z`, push
    `main` and the tag;
  - rehearsing a release with `-rc.N` tags;
  - running `git pull` after a release, because the workflow commits the
    manifests to `main`;
  - how to submit `release/winget/…` to `winget-pkgs` if that is wanted.

Release notes and docs are in English, like the rest of the repository.

### 8. Safety

- The bundle contains the program only, and `build.py` refuses to produce
  one that contains a replacements file.
- The smoke test checks the anonymization guarantee on the built program
  itself (no dictionary key or PII in the output, zero errors). It runs on
  every platform and after every package-manager install.
- Workflow permissions stay `contents: read`, except in the publish and
  promote jobs.

## Out of scope

- PyPI
- `.rpm` packages
- an apt repository
- code signing and notarization (they need paid certificates; see Risks)
- automatic submission to `winget-pkgs`
- Linux and Windows on ARM
- `homebrew-core`, and Homebrew on Linux
- keeping the console window open after `anonimize.exe` is double-clicked
  (the packages are meant to be used from a terminal)

## Risks

- **Antivirus false positives.** Windows Defender occasionally flags
  unsigned PyInstaller executables, especially onefile ones. Signing is the
  only way to prevent that. If it happens, the usual first remedy is
  building the PyInstaller bootloader from source.
- **macOS is tested in CI only.** The dev machine cannot run macOS, so the
  pull-request dry run and the `-rc` rehearsal are the only proof.
- **Intel macOS.** `macos-15-intel` is GitHub's last Intel image. When it is
  retired, the Intel asset and the formula's `on_intel` block go with it.
- **Startup time on Windows.** A onefile program unpacks to a temporary
  folder on every start: a few seconds, longer with real-time antivirus
  scanning. That does not matter for long runs but is noticeable when
  starting the interactive wizard.

## Testing

- **Unit tests** (pytest, run by `tests.yml` on all three OSes):
  - `--version`, `--check-tools`, and the hint text in frozen and
    non-frozen mode;
  - `render.py` output for fixed inputs: the Scoop JSON parses and has the
    right URL and hash; the formula and winget texts contain the right
    version, URLs and hashes; the `.deb` version mapping; the release notes
    for a first and a later release;
  - the tag/version check;
  - `build.py`'s replacements-file guard.
- **Built program:** `release/smoke_test.py` runs on every platform
  (job 3), in three clean distribution containers (job 4), and after every
  package-manager install (job 6).
- **Locally during implementation:** the Windows build and its smoke test
  on the dev machine; the Linux build, the `.deb` and the container installs
  through Docker with `release/build-linux-in-docker.sh`. macOS: the
  pull-request dry run only.
- **End-to-end rehearsal before 1.0.0:** tag `v1.0.0-rc.1` (pushed only
  with the user's go-ahead) runs the complete pipeline, including the
  package-manager installs, without changing `main`. Then `v1.0.0`.

## One-time manual steps for the user

- Push the tags (`v1.0.0-rc.1`, then `v1.0.0`).
- Optional: set the repository's "About" website to
  `https://github.com/kgorczowski/anonimize/releases/latest`.
- Optional, later: submit the winget manifest to `microsoft/winget-pkgs`.
