# Contributing

## Development setup

### Python dependencies

Run the setup script for your platform:

- PowerShell (Windows): `.\scripts\install.ps1`
- bash (macOS / Linux / Git Bash): `./scripts/install.sh`

Both install `requirements.txt` with whichever Python interpreter they find
(so `pip install -r requirements.txt` works too if you already know your
interpreter is set up correctly), then report whether the optional system
tools are available — Tesseract for scanned PDFs and a `.rar` extractor —
with the install command for your OS when one is missing. Tools installed
in their default Windows folders count as available; no PATH change needed.

Homebrew Python on macOS and the system Python on Debian/Ubuntu are
"externally managed" (PEP 668) and refuse `pip install` outside a virtual
environment, so `./scripts/install.sh` fails there on its first step: create
one first with `python3 -m venv .venv` then `. .venv/bin/activate` (on
Debian/Ubuntu install the venv module before that with
`sudo apt install python3-venv`), or on Windows with `py -m venv .venv` then
`.venv\Scripts\Activate.ps1`. `.venv/` is already gitignored.

### Windows: `python` opens the Microsoft Store instead of running

Windows ships a Store-redirect stub for `python`/`python3` on PATH that only
gets out of the way once a real Python installation is also on PATH ahead of
it. If you see *"Python was not found; run without arguments to install from
the Microsoft Store"* despite having Python installed, use the Python
Launcher (`py`) instead of `python`, or fix the alias itself:

1. **Disable the stub:** Settings > Apps > Advanced app settings > App
   execution aliases > turn off `python.exe` / `python3.exe`.
2. **Or alias `python` to `py` for your shell:**
   - PowerShell profile (`$PROFILE`): `Set-Alias python py`
   - Git Bash / WSL (`~/.bashrc`): `alias python=py`

### GitHub CLI (`gh`)

Used for creating pull requests from the command line
(`gh pr create`). After installing, authenticate once with `gh auth login`.
If `gh` isn't recognized afterward, it's a PATH problem:

- **Windows** — package-manager installs (`winget`, `choco`, `scoop`) add it
  to PATH automatically. For a manual zip install, add the extracted `bin`
  folder yourself: System Settings > Environment Variables > User variables
  > `Path` > New, or from PowerShell:
  ```powershell
  [Environment]::SetEnvironmentVariable("Path", "$env:Path;C:\path\to\gh\bin", "User")
  ```
  (open a new terminal afterward — existing ones won't pick it up).
- **macOS** — `brew install gh` puts it on PATH via Homebrew automatically.
  A manual download needs its directory added in `~/.zshrc` /
  `~/.bash_profile`: `export PATH="$PATH:/path/to/gh/bin"`.
- **Linux** — distro package managers (`apt`, `dnf`, `pacman`) add it to
  PATH automatically. A manual tarball install needs the same `export
  PATH=...` line as macOS, in `~/.bashrc` / `~/.zshrc`.

### Tests and continuous integration

`python -m pytest` runs the suite normally; tests that need an optional
system tool (Tesseract, a `.rar` extractor) skip themselves when it is
missing. CI (`.github/workflows/tests.yml`) runs the suite on Ubuntu, macOS
and Windows with those tools installed, through `scripts/run-tests.sh`,
which additionally fails if *any* test was skipped — so a green run means
the OCR and RAR paths really ran on every OS. The same script works
locally: `bash scripts/run-tests.sh`. The interpreter is chosen with the
`PYTHON` variable and defaults to `python`, which does not exist (or is the
Microsoft Store stub) on a default Windows machine and may be missing on
macOS or Debian/Ubuntu, so set it there:

```bash
PYTHON=py bash scripts/run-tests.sh       # Windows (Git Bash)
PYTHON=python3 bash scripts/run-tests.sh  # macOS / Linux
```

To reproduce the Linux job on your machine (needs Docker and bash, so on
Windows run it from Git Bash or WSL):

```bash
bash scripts/test-in-docker.sh
```

## Releasing

Releases are built and published by `.github/workflows/release.yml` from a
version tag. The version lives in one place: `__version__` in
`anonymize.py`, and the workflow refuses a tag that is not `v` + that value.

### Cutting a release

```bash
# 1. set __version__ = "1.2.0" in anonymize.py, then:
git commit -m "release: 1.2.0" anonymize.py   # only this file: never -a
git tag v1.2.0
git push origin main v1.2.0
```

Commit only `anonymize.py`: `git commit -a` would also pick up a locally
edited `replacements.json`, which holds real client names.

The workflow then:

1. runs the test suite on all three OSes;
2. freezes the program with PyInstaller on Windows, macOS (arm64 and Intel)
   and Linux (in `ubuntu:22.04`), builds the `.deb`, and runs
   `release/smoke_test.py` against every built program: a real run over
   every file type that must end with zero errors and no dictionary term
   or PII in the output;
3. installs the `.deb` into fresh Ubuntu 22.04, Ubuntu 24.04 and Debian 12
   containers and smoke-tests it there;
4. publishes a GitHub Release as a **pre-release**, with the archives, the
   `.deb`, `SHA256SUMS` and generated notes (install commands and the commit
   subjects since the previous release);
5. installs that release through Homebrew (arm64 and Intel), Scoop and
   winget and smoke-tests each installed command;
6. only then marks the release as "Latest" and commits the updated
   `Formula/anonimize.rb`, `bucket/anonimize.json` and
   `release/winget/manifests/…` to `main` (as `github-actions[bot]`).

So `brew upgrade` and `scoop update` only ever see versions that installed
and ran cleanly everywhere. Run `git pull` after a release to get the bot's
manifest commit before committing on `main` again. If a job fails, fix the
cause and release the next patch version; re-running the failed jobs of the
same tag is also safe (the publish step updates an existing release).

### Rehearsing a release

A pre-release tag runs everything up to and including the package-manager
installs, but never becomes "Latest" and never touches `main`:

```bash
# __version__ = "1.2.0-rc.1"
git commit -m "release: 1.2.0-rc.1" anonymize.py   # only this file: never -a
git tag v1.2.0-rc.1
git push origin main v1.2.0-rc.1
```

Pull requests that change `anonymize.py`, `requirements.txt` or `release/`
run the build-and-smoke-test part as a dry run, so packaging problems show
up before merging.

### Reproducing the Linux build locally

Needs Docker and bash (on Windows: Git Bash or WSL):

```bash
bash release/build-linux-in-docker.sh       # dist/*.tar.gz, dist/*.deb
bash release/test-deb-in-docker.sh ubuntu:24.04
```

On Windows or macOS, build for the current platform in a virtual
environment with `requirements.txt` and `release/requirements-build.txt`
installed: `python release/build.py`, then
`python release/smoke_test.py fixtures build/fx` and
`python release/smoke_test.py check --fixtures build/fx --version <version> -- <built program>`.

### Publishing to winget

`winget install anonimize` by name needs the manifest in Microsoft's
community repository. Each release leaves a validated manifest in
`release/winget/manifests/k/kgorczowski/anonimize/<version>/`; to submit it,
copy that folder to the same path in a fork of
[microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs) and open a
pull request there (or use `wingetcreate submit <folder>`).
