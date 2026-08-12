# Contributing

## Development setup

### Python dependencies

Run the setup script for your platform:

- PowerShell (Windows): `.\scripts\install.ps1`
- bash (macOS / Linux / Git Bash): `./scripts/install.sh`

Both just install `requirements.txt` with whichever Python interpreter they
find, so `pip install -r requirements.txt` works too if you already know
your interpreter is set up correctly.

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
