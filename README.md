# Anonimize

A command-line tool that recursively walks a directory, anonymizes text and code files by replacing sensitive strings with placeholders, and converts Office documents to Markdown before anonymizing them too.

## Requirements

- Python 3.9+
- Dependencies from `requirements.txt`

```bash
pip install -r requirements.txt
```

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
  "VM": "Company1",
  "BDR": "Company2"
}
```

Matching is an exact, case-sensitive substring replacement. Longer keys are matched before shorter ones, so a more specific string is never shadowed by a shorter one contained within it.

## What gets processed

| File type | Behavior |
|---|---|
| Text/code (`.txt`, `.md`, `.py`, `.js`, `.json`, `.sql`, `.cs`, `.ps1`, and other common source/config extensions) | Read as text, anonymized in place |
| Office (`.docx`, `.xlsx`, `.pptx`) | Converted to Markdown, then anonymized, written as `.md` |
| Everything else | Copied unchanged |

Non-UTF-8 text files that can't be decoded are copied unchanged rather than corrupted.

The tool scans the whole source tree first (so it can show accurate progress and an ETA), then processes every file, and prints a summary of how many files were anonymized, converted, copied, or errored.

## License

MIT — see [LICENSE](LICENSE).
