## Install

**macOS** (Homebrew; also installs Tesseract OCR and unar)

```bash
brew tap kgorczowski/anonimize $repo_url
brew install anonimize
```

**Windows** (Scoop)

```powershell
scoop bucket add anonimize $repo_url
scoop install anonimize
```

**Debian / Ubuntu** (apt also installs tesseract-ocr and unar)

```bash
curl -LO $deb_url
sudo apt install ./$deb_name
```

**Other Linux:** download `$linux_archive`, extract it and run `anonimize/anonimize`.

**Update:** `brew upgrade anonimize` / `scoop update anonimize` / install the newer `.deb` the same way.

Then check that the optional OCR and `.rar` tools were found:

```bash
anonimize --check-tools
```

## Verify

Every file of this release is listed in `SHA256SUMS`:

```bash
sha256sum -c SHA256SUMS --ignore-missing
```

## Changes

$changes
