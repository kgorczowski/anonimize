# Interactive TUI Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive terminal UI to `anonymize.py`, triggered by running it with zero arguments, that lets the user pick/create a replacements dictionary file, add/edit/delete its entries (persisted to disk immediately), pick a source folder via a navigable directory browser, confirm an output folder, and run the same anonymization engine the classic CLI already uses.

**Architecture:** Extract the existing scan/process/summary body of `main()` into a standalone `run_anonymization(source_dir, replacements_file, output_root)` so both the classic CLI path and the new interactive path share one engine. Add four new `questionary`-based functions (`browse_for_directory`, `browse_for_replacements_file`, `manage_replacements_dictionary`, `prompt_output_directory`) plus an orchestrator (`run_interactive_mode`) that calls them in sequence and hands off to `run_anonymization`.

**Tech Stack:** Python 3, `questionary` (new dependency) for console prompts/menus.

**Spec:** `docs/superpowers/specs/2026-09-22-interactive-tui-mode-design.md`

## Global Constraints

- Interactive mode triggers only when `anonymize.py` is invoked with zero command-line arguments (`len(sys.argv) == 1`); any arguments at all use the existing classic CLI path, unchanged.
- All new code lives in `anonymize.py` — no new source modules (deliberate choice, matches the rest of this project).
- The directory browser (`browse_for_directory`) lists and lets the user select only directories, never individual files.
- Every dictionary edit (add/edit/delete) is written to the replacements file on disk immediately after that single change, not batched until the session ends.
- "Edit entry" changes only the value of an existing key; the key itself never changes (renaming is delete + add, as two separate actions).
- Selecting "Edit entry" or "Delete entry" while the dictionary has no entries prints `"No entries yet."` and returns to the menu, without attempting to render an empty selection list.
- Any prompt returning `None` (Ctrl-C) raises `KeyboardInterrupt`, caught once at the top of `run_interactive_mode`, which prints `"Cancelled."` and returns — no traceback reaches the user.
- If `questionary` is not installed, running with zero arguments prints `"Interactive mode requires questionary. Install it with: pip install questionary"` to stderr and exits with status 1 — the classic CLI path must keep working even without `questionary` installed, matching the existing soft-dependency pattern used for `pymupdf`/`pytesseract`.

---

## File Structure

- **Modify:** `anonymize.py` — extract `run_anonymization`, add the four TUI helper functions, add `run_interactive_mode`, update `main()`.
- **Modify:** `requirements.txt` — add `questionary`.
- **Modify:** `README.md` — document the interactive mode.
- **Create:** `tests/test_interactive.py` — all tests for the new functions (scripted-prompt helpers defined once here, reused by every task's tests).

**A note on line references below:** every "Find" instruction is followed by the exact code block to search for — that block is the real anchor. Parenthetical `anonymize.py:NNN` references are line numbers from the plan's starting point and will drift as earlier tasks add code above later ones — always locate code by matching the shown text, never by jumping to a stale line number.

---

## Task 1: Extract `run_anonymization()` from `main()`

**Files:**
- Modify: `anonymize.py` (the entire `main()` function, currently `anonymize.py:1279-1499`)
- Test: `tests/test_integration.py`

**Interfaces:**
- Produces: `run_anonymization(source_dir: Path, replacements_file: Path, output_root: Path) -> None` — loads the replacements file itself and runs the full scan/process/summary pipeline. Every later task in this plan calls this function as the final step of the interactive wizard.

This task is a pure refactor: it must not change the classic CLI's behavior at all. There is no new user-facing functionality yet — the "test" for this task is proving nothing broke, plus proving the extracted function is independently callable (which the interactive mode will depend on).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_integration.py` (it already imports `anonymize` at the top):

```python
def test_run_anonymization_can_be_called_directly(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "notes.txt").write_text("VM note", encoding="utf-8")

    replacements_file = tmp_path / "replacements.json"
    replacements_file.write_text('{"VM": "Company1"}', encoding="utf-8")

    output_root = tmp_path / "out"

    anonymize.run_anonymization(source_dir, replacements_file, output_root)

    assert (output_root / "notes.txt").read_text(encoding="utf-8") == (
        "Company1 note"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/test_integration.py::test_run_anonymization_can_be_called_directly -v`
Expected: FAIL with `AttributeError: module 'anonymize' has no attribute 'run_anonymization'`

- [ ] **Step 3: Replace `main()` with `run_anonymization()` + a slimmer `main()`**

Find the entire function, from its `def` line through the end of the file (this exact block appears once, at the end of `anonymize.py`):

```python
def main():
    parser = argparse.ArgumentParser(
        description=(
            "Recursively anonymize text/code files and convert "
            "DOCX/XLSX/PPTX files to Markdown."
        )
    )

    parser.add_argument(
        "source",
        help="Source directory",
    )

    parser.add_argument(
        "replacements",
        help="JSON file containing replacement mappings",
    )

    parser.add_argument(
        "--output",
        help=(
            "Optional output directory. "
            "Default: <source-parent>/anonimized/<source-name>"
        ),
    )

    args = parser.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    replacements_file = Path(args.replacements).expanduser().resolve()

    if not source_dir.exists():
        print(f"ERROR: source directory does not exist: {source_dir}")
        sys.exit(1)

    if not source_dir.is_dir():
        print(f"ERROR: source path is not a directory: {source_dir}")
        sys.exit(1)

    if not replacements_file.exists():
        print(f"ERROR: replacement file does not exist: {replacements_file}")
        sys.exit(1)

    try:
        replacements = load_replacements(replacements_file)
    except Exception as exc:
        print(f"ERROR: cannot load replacement map: {exc}")
        sys.exit(1)

    if args.output:
        output_root = Path(args.output).expanduser().resolve()
    else:
        output_root = (
            source_dir.parent
            / "anonimized"
            / source_dir.name
        )

    # --------------------------------------------------------
    # PASS 1 - scan
    # --------------------------------------------------------

    print()
    print("==============================================")
    print(" ANONYMIZATION")
    print("==============================================")
    print()
    print(f"Source       : {source_dir}")
    print(f"Output       : {output_root}")
    print(f"Replacements : {len(replacements)}")
    print()
    print("Scanning files...")

    scan_start = time.monotonic()

    temp_dirs = []
    extraction_errors = []

    try:
        files = scan_files(
            source_dir,
            output_root,
            temp_dirs,
            extraction_errors,
        )

        # Anonymize folder/file names before deduplicating: two
        # differently-cased source names (BDR/, bdr/) can now land on
        # the same destination, and dedup is what resolves that.
        files, dictionary_replacements = anonymize_destinations(
            files, replacements
        )

        # An extracted archive can land on the same output path as a
        # plain sibling (data.zip next to data/) or as another archive
        # with the same stem. Rename instead of silently overwriting.
        files = deduplicate_destinations(files)

        archives_extracted = len(temp_dirs)

        scan_duration = time.monotonic() - scan_start

        print(
            f"Found {len(files):,} files "
            f"in {format_duration(scan_duration)}."
        )
        print()

        if not files:
            print("Nothing to process.")
            return

        # --------------------------------------------------------
        # PASS 2 - processing
        # --------------------------------------------------------

        output_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        progress = ProgressBar(
            total=len(files)
        )

        processed = 0
        anonymized = 0
        office_converted = 0
        pdf_converted = 0
        images_redacted = 0
        copied = 0
        errors = 0
        pii_redacted = 0

        processing_start = time.monotonic()

        for entry in files:
            destination = output_root / entry.relative_destination

            try:
                result, pii_count, dict_count = process_file(
                    entry.source,
                    destination,
                    replacements,
                )

                pii_redacted += pii_count
                dictionary_replacements += dict_count

                if result == "anonymized":
                    anonymized += 1
                elif result == "office":
                    office_converted += 1
                elif result == "pdf":
                    pdf_converted += 1
                elif result == "image":
                    images_redacted += 1
                else:
                    copied += 1

            except Exception as exc:
                errors += 1

                print()
                print(
                    f"ERROR: {entry.source}: {exc}",
                    file=sys.stderr,
                )

                # Deliberately not copied unchanged: this tool exists to
                # anonymize PII, and a file that failed to process is
                # exactly the file we could not guarantee is safe. The
                # error is already counted and logged; the file is
                # simply excluded from the output rather than risking a
                # raw, un-anonymized copy landing in it.

            processed += 1

            progress.update(
                processed,
                entry.relative_destination,
            )

        progress.finish()

        duration = time.monotonic() - processing_start

        errors += len(extraction_errors)

        # --------------------------------------------------------
        # Summary
        # --------------------------------------------------------

        print()
        print("==============================================")
        print(" DONE")
        print("==============================================")
        print()
        print(f"Files found       : {len(files):,}")
        print(f"Files processed   : {processed:,}")
        print(f"Archives extracted: {archives_extracted:,}")
        print(f"Text/code         : {anonymized:,}")
        print(f"Office -> Markdown: {office_converted:,}")
        print(f"PDF -> Markdown   : {pdf_converted:,}")
        print(f"Images redacted   : {images_redacted:,}")
        print(f"Copied unchanged  : {copied:,}")
        print(f"Dict replacements : {dictionary_replacements:,}")
        print(f"PII fragments     : {pii_redacted:,}")
        print(f"Errors            : {errors:,}")
        print(f"Processing time   : {format_duration(duration)}")
        print()
        print(f"Output directory:")
        print(output_root)
        print()
    finally:
        for temp_dir in temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
```

Replace it with:

```python
def run_anonymization(
    source_dir: Path,
    replacements_file: Path,
    output_root: Path,
) -> None:
    try:
        replacements = load_replacements(replacements_file)
    except Exception as exc:
        print(f"ERROR: cannot load replacement map: {exc}")
        sys.exit(1)

    # --------------------------------------------------------
    # PASS 1 - scan
    # --------------------------------------------------------

    print()
    print("==============================================")
    print(" ANONYMIZATION")
    print("==============================================")
    print()
    print(f"Source       : {source_dir}")
    print(f"Output       : {output_root}")
    print(f"Replacements : {len(replacements)}")
    print()
    print("Scanning files...")

    scan_start = time.monotonic()

    temp_dirs = []
    extraction_errors = []

    try:
        files = scan_files(
            source_dir,
            output_root,
            temp_dirs,
            extraction_errors,
        )

        # Anonymize folder/file names before deduplicating: two
        # differently-cased source names (BDR/, bdr/) can now land on
        # the same destination, and dedup is what resolves that.
        files, dictionary_replacements = anonymize_destinations(
            files, replacements
        )

        # An extracted archive can land on the same output path as a
        # plain sibling (data.zip next to data/) or as another archive
        # with the same stem. Rename instead of silently overwriting.
        files = deduplicate_destinations(files)

        archives_extracted = len(temp_dirs)

        scan_duration = time.monotonic() - scan_start

        print(
            f"Found {len(files):,} files "
            f"in {format_duration(scan_duration)}."
        )
        print()

        if not files:
            print("Nothing to process.")
            return

        # --------------------------------------------------------
        # PASS 2 - processing
        # --------------------------------------------------------

        output_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        progress = ProgressBar(
            total=len(files)
        )

        processed = 0
        anonymized = 0
        office_converted = 0
        pdf_converted = 0
        images_redacted = 0
        copied = 0
        errors = 0
        pii_redacted = 0

        processing_start = time.monotonic()

        for entry in files:
            destination = output_root / entry.relative_destination

            try:
                result, pii_count, dict_count = process_file(
                    entry.source,
                    destination,
                    replacements,
                )

                pii_redacted += pii_count
                dictionary_replacements += dict_count

                if result == "anonymized":
                    anonymized += 1
                elif result == "office":
                    office_converted += 1
                elif result == "pdf":
                    pdf_converted += 1
                elif result == "image":
                    images_redacted += 1
                else:
                    copied += 1

            except Exception as exc:
                errors += 1

                print()
                print(
                    f"ERROR: {entry.source}: {exc}",
                    file=sys.stderr,
                )

                # Deliberately not copied unchanged: this tool exists to
                # anonymize PII, and a file that failed to process is
                # exactly the file we could not guarantee is safe. The
                # error is already counted and logged; the file is
                # simply excluded from the output rather than risking a
                # raw, un-anonymized copy landing in it.

            processed += 1

            progress.update(
                processed,
                entry.relative_destination,
            )

        progress.finish()

        duration = time.monotonic() - processing_start

        errors += len(extraction_errors)

        # --------------------------------------------------------
        # Summary
        # --------------------------------------------------------

        print()
        print("==============================================")
        print(" DONE")
        print("==============================================")
        print()
        print(f"Files found       : {len(files):,}")
        print(f"Files processed   : {processed:,}")
        print(f"Archives extracted: {archives_extracted:,}")
        print(f"Text/code         : {anonymized:,}")
        print(f"Office -> Markdown: {office_converted:,}")
        print(f"PDF -> Markdown   : {pdf_converted:,}")
        print(f"Images redacted   : {images_redacted:,}")
        print(f"Copied unchanged  : {copied:,}")
        print(f"Dict replacements : {dictionary_replacements:,}")
        print(f"PII fragments     : {pii_redacted:,}")
        print(f"Errors            : {errors:,}")
        print(f"Processing time   : {format_duration(duration)}")
        print()
        print(f"Output directory:")
        print(output_root)
        print()
    finally:
        for temp_dir in temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Recursively anonymize text/code files and convert "
            "DOCX/XLSX/PPTX files to Markdown."
        )
    )

    parser.add_argument(
        "source",
        help="Source directory",
    )

    parser.add_argument(
        "replacements",
        help="JSON file containing replacement mappings",
    )

    parser.add_argument(
        "--output",
        help=(
            "Optional output directory. "
            "Default: <source-parent>/anonimized/<source-name>"
        ),
    )

    args = parser.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    replacements_file = Path(args.replacements).expanduser().resolve()

    if not source_dir.exists():
        print(f"ERROR: source directory does not exist: {source_dir}")
        sys.exit(1)

    if not source_dir.is_dir():
        print(f"ERROR: source path is not a directory: {source_dir}")
        sys.exit(1)

    if not replacements_file.exists():
        print(f"ERROR: replacement file does not exist: {replacements_file}")
        sys.exit(1)

    if args.output:
        output_root = Path(args.output).expanduser().resolve()
    else:
        output_root = (
            source_dir.parent
            / "anonimized"
            / source_dir.name
        )

    run_anonymization(source_dir, replacements_file, output_root)


if __name__ == "__main__":
    main()
```

Note exactly what moved and what stayed: `load_replacements` moved into `run_anonymization` (with its existing error handling verbatim); the `args.output` default-computation logic stayed in `main()` since it's specific to the CLI's `argparse` result. Nothing else changed — every print statement, counter, and the `finally` cleanup are byte-for-byte the same code, just inside a differently-named function.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/test_integration.py::test_run_anonymization_can_be_called_directly -v`
Expected: PASS

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `py -m pytest tests/ -v`
Expected: PASS, same pass/skip counts as before this task (this is the real proof the refactor didn't change CLI behavior — several existing tests in `tests/test_integration.py` already drive `main()` end-to-end via `sys.argv`).

- [ ] **Step 6: Commit**

```bash
git add anonymize.py tests/test_integration.py
git commit -m "refactor: extract run_anonymization() from main()"
```

---

## Task 2: Directory browser (`browse_for_directory`)

**Files:**
- Modify: `anonymize.py` (new function, and a new import)
- Modify: `requirements.txt`
- Create: `tests/test_interactive.py`

**Interfaces:**
- Produces: `browse_for_directory(start_path: Path) -> Path` — navigates directories starting at `start_path`, returns the chosen directory. Raises `KeyboardInterrupt` if the user cancels (Ctrl-C). Used directly by Task 5's `run_interactive_mode` (for the source folder) and indirectly via Task 5's `prompt_output_directory` (for the output folder).
- Produces (test-only, but reused by Tasks 3-5): `_ScriptedAsk`, `_scripted_select`, `_scripted_text` helper classes/functions in `tests/test_interactive.py`, for scripting `questionary` prompt answers without a real terminal.

- [ ] **Step 1: Add the dependency**

Append to `requirements.txt` (currently ends with `pytest` on its own line under a `# Dev: testing` comment):

```
questionary
```

Run: `py -m pip install -r requirements.txt`

- [ ] **Step 2: Write the failing tests**

Create `tests/test_interactive.py`:

```python
from pathlib import Path

import pytest

import anonymize


class _ScriptedAsk:
    """Stands in for questionary's `Question` object: `.ask()` returns a
    pre-programmed value instead of reading real terminal input."""

    def __init__(self, value):
        self._value = value

    def ask(self):
        return self._value


def _scripted_select(answers):
    """Returns a fake `questionary.select` that ignores its arguments and
    returns the next scripted answer on each call, in order."""
    it = iter(answers)

    def fake_select(message, choices):
        return _ScriptedAsk(next(it))

    return fake_select


def _scripted_text(answers):
    it = iter(answers)

    def fake_text(message, **kwargs):
        return _ScriptedAsk(next(it))

    return fake_text


def _scripted_confirm(answers):
    it = iter(answers)

    def fake_confirm(message, **kwargs):
        return _ScriptedAsk(next(it))

    return fake_confirm


def test_browse_for_directory_selects_current_folder_immediately(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    monkeypatch.setattr(
        questionary, "select", _scripted_select([("select", None)])
    )

    result = anonymize.browse_for_directory(tmp_path)

    assert result == tmp_path.resolve()


def test_browse_for_directory_navigates_into_subfolder_then_selects(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    sub = tmp_path / "sub"
    sub.mkdir()

    monkeypatch.setattr(
        questionary,
        "select",
        _scripted_select([("enter", sub), ("select", None)]),
    )

    result = anonymize.browse_for_directory(tmp_path)

    assert result == sub.resolve()


def test_browse_for_directory_up_navigates_to_parent(tmp_path, monkeypatch):
    questionary = pytest.importorskip("questionary")

    sub = tmp_path / "sub"
    sub.mkdir()

    monkeypatch.setattr(
        questionary,
        "select",
        _scripted_select([("up", None), ("select", None)]),
    )

    result = anonymize.browse_for_directory(sub)

    assert result == tmp_path.resolve()


def test_browse_for_directory_raises_keyboard_interrupt_on_cancel(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    monkeypatch.setattr(questionary, "select", _scripted_select([None]))

    with pytest.raises(KeyboardInterrupt):
        anonymize.browse_for_directory(tmp_path)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `py -m pytest tests/test_interactive.py -v`
Expected: FAIL with `AttributeError: module 'anonymize' has no attribute 'browse_for_directory'`

- [ ] **Step 4: Add `browse_for_directory` to `anonymize.py`**

Find the boundary between `run_anonymization` and `main()` — the blank
lines immediately followed by `def main():` (unique in the file at this
point in the plan):

```python
def main():
```

Replace it with the new function followed by that same `def main():`
line (i.e., insert above it, don't remove or duplicate it):

```python
# ------------------------------------------------------------
# Interactive mode
# ------------------------------------------------------------

def browse_for_directory(start_path: Path) -> Path:
    """
    Lets the user navigate directories with arrow keys and Enter,
    starting at start_path. Returns the chosen directory. Raises
    KeyboardInterrupt if the user cancels (Ctrl-C).
    """
    import questionary

    current = start_path.resolve()

    while True:
        try:
            subdirs = sorted(
                (p for p in current.iterdir() if p.is_dir()),
                key=lambda p: p.name.lower(),
            )
        except PermissionError:
            print(
                f"WARNING: cannot list {current}: permission denied",
                file=sys.stderr,
            )
            subdirs = []

        choices = [
            questionary.Choice(
                title="[Select this folder]", value=("select", None)
            )
        ]

        if current.parent != current:
            choices.append(
                questionary.Choice(title="..", value=("up", None))
            )

        choices.extend(
            questionary.Choice(title=p.name, value=("enter", p))
            for p in subdirs
        )

        answer = questionary.select(
            f"Folder: {current}",
            choices=choices,
        ).ask()

        if answer is None:
            raise KeyboardInterrupt

        action, target = answer

        if action == "select":
            return current
        if action == "up":
            current = current.parent
        elif action == "enter":
            current = target


def main():
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/test_interactive.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add anonymize.py requirements.txt tests/test_interactive.py
git commit -m "feat: add directory browser for interactive mode"
```

---

## Task 3: Replacements file browser (`browse_for_replacements_file`)

**Files:**
- Modify: `anonymize.py` (new function)
- Modify: `tests/test_interactive.py`

**Interfaces:**
- Consumes: `_ScriptedAsk`, `_scripted_select`, `_scripted_text` from Task 2 (already in `tests/test_interactive.py`).
- Produces: `browse_for_replacements_file(start_path: Path) -> Path` — lets the user pick an existing `.json` file or create a new one, starting the browse at `start_path`. Raises `KeyboardInterrupt` on cancel. Used by Task 5's `run_interactive_mode`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_interactive.py`:

```python
def test_browse_for_replacements_file_selects_existing_json(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    existing = tmp_path / "repl.json"
    existing.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        questionary, "select", _scripted_select([("choose", existing)])
    )

    result = anonymize.browse_for_replacements_file(tmp_path)

    assert result == existing


def test_browse_for_replacements_file_creates_new_file(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    monkeypatch.setattr(
        questionary, "select", _scripted_select([("create", None)])
    )
    monkeypatch.setattr(
        questionary, "text", _scripted_text(["new_dict.json"])
    )

    result = anonymize.browse_for_replacements_file(tmp_path)

    assert result == tmp_path / "new_dict.json"
    assert result.read_text(encoding="utf-8") == "{}"


def test_browse_for_replacements_file_navigates_into_subfolder(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    sub = tmp_path / "sub"
    sub.mkdir()
    target = sub / "repl.json"
    target.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        questionary,
        "select",
        _scripted_select([("enter", sub), ("choose", target)]),
    )

    result = anonymize.browse_for_replacements_file(tmp_path)

    assert result == target


def test_browse_for_replacements_file_raises_keyboard_interrupt_on_cancel(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    monkeypatch.setattr(questionary, "select", _scripted_select([None]))

    with pytest.raises(KeyboardInterrupt):
        anonymize.browse_for_replacements_file(tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_interactive.py -v -k replacements_file`
Expected: FAIL with `AttributeError: module 'anonymize' has no attribute 'browse_for_replacements_file'`

- [ ] **Step 3: Add `browse_for_replacements_file` to `anonymize.py`**

Find the same `def main():` line again (Task 2 just moved it further
down the file, but it's still the only occurrence):

```python
def main():
```

Replace it with the new function followed by that same `def main():`
line:

```python
def browse_for_replacements_file(start_path: Path) -> Path:
    """
    Lets the user navigate to an existing .json file, or create a new
    one, starting at start_path. Returns the chosen/created file's path.
    Raises KeyboardInterrupt if the user cancels (Ctrl-C).
    """
    import questionary

    current = start_path.resolve()

    while True:
        try:
            entries = sorted(
                current.iterdir(), key=lambda p: p.name.lower()
            )
        except PermissionError:
            print(
                f"WARNING: cannot list {current}: permission denied",
                file=sys.stderr,
            )
            entries = []

        subdirs = [p for p in entries if p.is_dir()]
        json_files = [
            p
            for p in entries
            if p.is_file() and p.suffix.lower() == ".json"
        ]

        choices = [
            questionary.Choice(
                title="+ Create new replacements file here",
                value=("create", None),
            )
        ]

        if current.parent != current:
            choices.append(
                questionary.Choice(title="..", value=("up", None))
            )

        choices.extend(
            questionary.Choice(title=f"{p.name}/", value=("enter", p))
            for p in subdirs
        )
        choices.extend(
            questionary.Choice(title=p.name, value=("choose", p))
            for p in json_files
        )

        answer = questionary.select(
            f"Replacements file: {current}",
            choices=choices,
        ).ask()

        if answer is None:
            raise KeyboardInterrupt

        action, target = answer

        if action == "create":
            name = questionary.text(
                "File name (e.g. replacements.json):"
            ).ask()

            if name is None:
                raise KeyboardInterrupt
            if not name:
                continue

            new_path = current / name
            if not new_path.exists():
                new_path.write_text("{}", encoding="utf-8")
            return new_path

        if action == "up":
            current = current.parent
        elif action == "enter":
            current = target
        elif action == "choose":
            return target


def main():
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_interactive.py -v -k replacements_file`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite**

Run: `py -m pytest tests/ -v`
Expected: PASS (all Task 2 tests plus these, no regressions)

- [ ] **Step 6: Commit**

```bash
git add anonymize.py tests/test_interactive.py
git commit -m "feat: add replacements file browser/creator for interactive mode"
```

---

## Task 4: Dictionary management loop (`manage_replacements_dictionary`)

**Files:**
- Modify: `anonymize.py` (new function)
- Modify: `tests/test_interactive.py`

**Interfaces:**
- Consumes: `_scripted_select`, `_scripted_text` from Task 2.
- Produces: `manage_replacements_dictionary(replacements_path: Path) -> dict` — interactive Add/Edit/Delete/Continue loop; every change is written to `replacements_path` immediately; returns the final dictionary when the user selects Continue. Raises `KeyboardInterrupt` on cancel. Used by Task 5's `run_interactive_mode`, which passes it the path returned by Task 3's `browse_for_replacements_file`.

- [ ] **Step 1: Write the failing tests**

First, add the missing import. Find the top of `tests/test_interactive.py`:

```python
from pathlib import Path

import pytest

import anonymize
```

Replace it with:

```python
import json
from pathlib import Path

import pytest

import anonymize
```

Then append to the end of the file:

```python
def test_manage_replacements_dictionary_add_entry_persists_to_disk(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    path = tmp_path / "repl.json"
    path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        questionary, "select", _scripted_select(["Add entry", "Continue"])
    )
    monkeypatch.setattr(
        questionary, "text", _scripted_text(["BDR", "namespace1"])
    )

    result = anonymize.manage_replacements_dictionary(path)

    assert result == {"BDR": "namespace1"}
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "BDR": "namespace1"
    }


def test_manage_replacements_dictionary_edit_entry_persists_to_disk(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    path = tmp_path / "repl.json"
    path.write_text(json.dumps({"BDR": "old_value"}), encoding="utf-8")

    monkeypatch.setattr(
        questionary,
        "select",
        _scripted_select(["Edit entry", "BDR", "Continue"]),
    )
    monkeypatch.setattr(questionary, "text", _scripted_text(["new_value"]))

    result = anonymize.manage_replacements_dictionary(path)

    assert result == {"BDR": "new_value"}
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "BDR": "new_value"
    }


def test_manage_replacements_dictionary_delete_entry_persists_to_disk(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    path = tmp_path / "repl.json"
    path.write_text(
        json.dumps({"BDR": "namespace1", "VM": "Company1"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        questionary,
        "select",
        _scripted_select(["Delete entry", "BDR", "Continue"]),
    )

    result = anonymize.manage_replacements_dictionary(path)

    assert result == {"VM": "Company1"}
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "VM": "Company1"
    }


def test_manage_replacements_dictionary_edit_on_empty_dict_returns_to_menu(
    tmp_path, monkeypatch, capsys
):
    questionary = pytest.importorskip("questionary")

    path = tmp_path / "repl.json"
    path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        questionary, "select", _scripted_select(["Edit entry", "Continue"])
    )

    result = anonymize.manage_replacements_dictionary(path)

    assert result == {}
    assert "No entries yet." in capsys.readouterr().out


def test_manage_replacements_dictionary_raises_keyboard_interrupt_on_cancel(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    path = tmp_path / "repl.json"
    path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(questionary, "select", _scripted_select([None]))

    with pytest.raises(KeyboardInterrupt):
        anonymize.manage_replacements_dictionary(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_interactive.py -v -k manage_replacements_dictionary`
Expected: FAIL with `AttributeError: module 'anonymize' has no attribute 'manage_replacements_dictionary'`

- [ ] **Step 3: Add `manage_replacements_dictionary` to `anonymize.py`**

Find the same `def main():` line once more (still the only occurrence):

```python
def main():
```

Replace it with the new function followed by that same `def main():`
line:

```python
def manage_replacements_dictionary(replacements_path: Path) -> dict:
    """
    Interactive Add/Edit/Delete/Continue loop over the dictionary stored
    at replacements_path. Every change is written back to the file
    immediately. Returns the current dictionary when the user selects
    Continue. Raises KeyboardInterrupt if the user cancels (Ctrl-C).
    """
    import questionary

    data = json.loads(replacements_path.read_text(encoding="utf-8"))

    def save():
        replacements_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    while True:
        print()
        print(f"Dictionary: {replacements_path}")
        if data:
            for key, value in data.items():
                print(f"  {key!r} -> {value!r}")
        else:
            print("  (empty)")
        print()

        action = questionary.select(
            "What next?",
            choices=["Add entry", "Edit entry", "Delete entry", "Continue"],
        ).ask()

        if action is None:
            raise KeyboardInterrupt

        if action == "Continue":
            return data

        if action == "Add entry":
            key = questionary.text("Key (text to find):").ask()
            if key is None:
                raise KeyboardInterrupt
            if not key:
                continue

            value = questionary.text("Value (replacement):").ask()
            if value is None:
                raise KeyboardInterrupt

            data[key] = value
            save()
            continue

        if not data:
            print("No entries yet.")
            continue

        if action == "Edit entry":
            key = questionary.select(
                "Which entry?", choices=list(data)
            ).ask()
            if key is None:
                raise KeyboardInterrupt

            value = questionary.text(
                f"New value for {key!r}:", default=data[key]
            ).ask()
            if value is None:
                raise KeyboardInterrupt

            data[key] = value
            save()
        elif action == "Delete entry":
            key = questionary.select(
                "Which entry?", choices=list(data)
            ).ask()
            if key is None:
                raise KeyboardInterrupt

            del data[key]
            save()


def main():
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_interactive.py -v -k manage_replacements_dictionary`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full suite**

Run: `py -m pytest tests/ -v`
Expected: PASS, no regressions

- [ ] **Step 6: Commit**

```bash
git add anonymize.py tests/test_interactive.py
git commit -m "feat: add interactive dictionary add/edit/delete"
```

---

## Task 5: Output prompt, orchestration, and `main()` wiring

**Files:**
- Modify: `anonymize.py` (two new functions, plus `main()`'s first lines)
- Modify: `tests/test_interactive.py`

**Interfaces:**
- Consumes: `browse_for_directory` (Task 2), `browse_for_replacements_file` (Task 3), `manage_replacements_dictionary` (Task 4), `run_anonymization` (Task 1).
- Produces: `prompt_output_directory(default_output: Path) -> Path`; `run_interactive_mode() -> None` — the full wizard orchestrator, called from `main()` when there are no command-line arguments.

- [ ] **Step 1: Write the failing tests**

First, add the missing import. Find the top of `tests/test_interactive.py`
(Task 4 already added `import json` above `from pathlib import Path`):

```python
import json
from pathlib import Path

import pytest

import anonymize
```

Replace it with:

```python
import json
import sys
from pathlib import Path

import pytest

import anonymize
```

Then append to the end of the file:

```python
def test_prompt_output_directory_returns_default_when_confirmed(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    default_output = tmp_path / "anonimized" / "src"

    monkeypatch.setattr(
        questionary, "confirm", _scripted_confirm([True])
    )

    result = anonymize.prompt_output_directory(default_output)

    assert result == default_output


def test_prompt_output_directory_browses_when_declined(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    # default_output's parent must exist for browse_for_directory to
    # have somewhere real to start listing from -- in real usage
    # ".../anonimized/" usually doesn't exist yet at this point (it's
    # only created later, inside run_anonymization), which is exactly
    # what prompt_output_directory's cwd fallback (see Step 3) is for.
    # This test pre-creates it so it exercises the "parent exists"
    # branch specifically, without depending on the real cwd's contents.
    (tmp_path / "anonimized").mkdir()
    default_output = tmp_path / "anonimized" / "src"
    custom = tmp_path / "custom_out"
    custom.mkdir()

    monkeypatch.setattr(
        questionary, "confirm", _scripted_confirm([False])
    )
    monkeypatch.setattr(
        questionary,
        "select",
        _scripted_select([("enter", custom), ("select", None)]),
    )

    result = anonymize.prompt_output_directory(default_output)

    assert result == custom.resolve()


def test_prompt_output_directory_raises_keyboard_interrupt_on_cancel(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    monkeypatch.setattr(questionary, "confirm", _scripted_confirm([None]))

    with pytest.raises(KeyboardInterrupt):
        anonymize.prompt_output_directory(tmp_path / "out")


def test_run_interactive_mode_happy_path_runs_anonymization(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "notes.txt").write_text("VM note", encoding="utf-8")

    monkeypatch.setattr(Path, "cwd", staticmethod(lambda: tmp_path))

    monkeypatch.setattr(
        questionary,
        "select",
        _scripted_select(
            [
                ("create", None),  # replacements file: create new
                "Add entry",  # dictionary: add
                "Continue",  # dictionary: done
                ("enter", source_dir),  # source folder: enter src
                ("select", None),  # source folder: select src
            ]
        ),
    )
    monkeypatch.setattr(
        questionary, "text", _scripted_text(["repl.json", "VM", "Company1"])
    )
    monkeypatch.setattr(
        questionary, "confirm", _scripted_confirm([True, True])
    )

    anonymize.run_interactive_mode()

    output_root = tmp_path / "anonimized" / "src"
    assert (output_root / "notes.txt").read_text(encoding="utf-8") == (
        "Company1 note"
    )
    assert json.loads(
        (tmp_path / "repl.json").read_text(encoding="utf-8")
    ) == {"VM": "Company1"}


def test_run_interactive_mode_cancelled_at_first_prompt_prints_cancelled(
    tmp_path, monkeypatch, capsys
):
    questionary = pytest.importorskip("questionary")

    monkeypatch.setattr(Path, "cwd", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(questionary, "select", _scripted_select([None]))

    anonymize.run_interactive_mode()

    assert "Cancelled." in capsys.readouterr().out


def test_run_interactive_mode_missing_questionary_shows_install_hint(
    monkeypatch, capsys
):
    monkeypatch.setitem(sys.modules, "questionary", None)

    with pytest.raises(SystemExit):
        anonymize.run_interactive_mode()

    assert "pip install questionary" in capsys.readouterr().err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_interactive.py -v -k "prompt_output_directory or run_interactive_mode"`
Expected: FAIL with `AttributeError` (neither function exists yet)

- [ ] **Step 3: Add `prompt_output_directory` and `run_interactive_mode` to `anonymize.py`, and wire `main()`**

Insert directly after `manage_replacements_dictionary` (before `def main():`):

```python
def prompt_output_directory(default_output: Path) -> Path:
    """
    Asks whether to use default_output; if declined, lets the user pick
    a different folder via browse_for_directory, starting from its
    parent if that exists, or the current directory otherwise (the
    default output's parent -- typically ".../anonimized/" -- usually
    doesn't exist yet at this point; it's only created later, inside
    run_anonymization, and browse_for_directory needs a real directory
    to start listing from). Raises KeyboardInterrupt if the user cancels
    (Ctrl-C).
    """
    import questionary

    use_default = questionary.confirm(
        f"Use default output folder? {default_output}",
        default=True,
    ).ask()

    if use_default is None:
        raise KeyboardInterrupt

    if use_default:
        return default_output

    start = (
        default_output.parent
        if default_output.parent.exists()
        else Path.cwd()
    )
    return browse_for_directory(start)


def run_interactive_mode() -> None:
    try:
        import questionary
    except ImportError:
        print(
            "Interactive mode requires questionary. Install it with: "
            "pip install questionary",
            file=sys.stderr,
        )
        sys.exit(1)

    print("=== Anonimize - interactive mode ===")

    try:
        replacements_file = browse_for_replacements_file(Path.cwd())
        manage_replacements_dictionary(replacements_file)

        source_dir = browse_for_directory(Path.cwd())

        default_output = (
            source_dir.parent / "anonimized" / source_dir.name
        )
        output_root = prompt_output_directory(default_output)

        replacements_count = len(
            json.loads(replacements_file.read_text(encoding="utf-8"))
        )

        confirmed = questionary.confirm(
            f"Anonymize {source_dir} -> {output_root} "
            f"using {replacements_count} dictionary entries?",
            default=True,
        ).ask()

        if confirmed is None:
            raise KeyboardInterrupt
    except KeyboardInterrupt:
        print()
        print("Cancelled.")
        return

    if not confirmed:
        print("Cancelled.")
        return

    run_anonymization(source_dir, replacements_file, output_root)
```

Then find this exact two-line start of `main()` (unique — it's the only `def main():` in the file):

```python
def main():
    parser = argparse.ArgumentParser(
```

and replace it with:

```python
def main():
    if len(sys.argv) == 1:
        run_interactive_mode()
        return

    parser = argparse.ArgumentParser(
```

Everything else in `main()` — the rest of `argparse` setup, validation, and the final `run_anonymization(...)` call — stays exactly as Task 1 left it; this step only adds the three new lines (`if len(sys.argv) == 1:`, `run_interactive_mode()`, `return`) plus a blank line before the pre-existing `parser = argparse.ArgumentParser(` line.

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_interactive.py -v`
Expected: PASS (all tests in the file, including Tasks 2-4's)

- [ ] **Step 5: Run the full suite**

Run: `py -m pytest tests/ -v`
Expected: PASS, no regressions

- [ ] **Step 6: Manual smoke check**

Run interactively (not scripted) to see the real prompts render correctly:

```bash
py anonymize.py
```

Walk through: create a new replacements file in a scratch folder, add one entry, continue, pick a small test folder as source, accept the default output, confirm. Verify the summary at the end looks like a normal run and the output folder has the anonymized files. Ctrl-C at one of the prompts and confirm you see `"Cancelled."` with no traceback.

- [ ] **Step 7: Commit**

```bash
git add anonymize.py tests/test_interactive.py
git commit -m "feat: wire up interactive mode orchestration and no-args entry point"
```

---

## Task 6: Documentation and final polish

**Files:**
- Modify: `README.md`
- Test: none (documentation only; final verification reruns the existing suite)

**Interfaces:**
- None new.

- [ ] **Step 1: Add an "Interactive mode" section to `README.md`**

Find the `## Usage` section's code block:

```
```bash
python anonymize.py <source> <replacements.json> [--output <dir>]
```
```

Directly after the arguments table and the `### Example` block that follow it (i.e., right before the `## Replacements file format` heading), add:

```markdown
### Interactive mode

Running `python anonymize.py` with **no arguments** starts an interactive
wizard instead: pick or create a replacements file, add/edit/delete its
entries (each change is saved immediately), pick a source folder with an
arrow-key directory browser, confirm (or change) the output folder, and
run. Requires the `questionary` package (already in `requirements.txt`);
if it isn't installed, the no-argument form prints an install hint and
exits, while `python anonymize.py <source> <replacements.json>` keeps
working exactly as before.
```

- [ ] **Step 2: Run the full suite one final time**

Run: `py -m pytest tests/ -v`
Expected: PASS, full suite green.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document the interactive mode"
```

---

## Self-Review Notes

- **Spec coverage:** trigger condition (no-args) → Task 5; replacements file picker/creator → Task 3; dictionary Add/Edit/Delete/Continue with immediate persistence and the "Edit changes only the value" / "No entries yet." rules → Task 4; source folder browser → Task 2; output folder confirm/override → Task 5; shared `run_anonymization` engine → Task 1; `questionary` soft-dependency with install hint → Task 5; Ctrl-C handling → every task that adds a prompt (2, 3, 4, 5) plus the top-level catch in `run_interactive_mode` (Task 5); single-file constraint → honored throughout; README documentation → Task 6.
- **Type consistency check:** `browse_for_directory`/`browse_for_replacements_file` both return `Path` and raise `KeyboardInterrupt` — used consistently by Task 5. `manage_replacements_dictionary` returns `dict` — Task 5 only uses it for its side effect (the file on disk) and separately re-reads the file for the entry count, so its return value isn't otherwise consumed; this is intentional, not an inconsistency. `run_anonymization(source_dir: Path, replacements_file: Path, output_root: Path) -> None` — identical signature used in Task 1's own test and Task 5's `run_interactive_mode` call. Every `questionary.select/text/confirm(...).ask()` call site checks for `None` and raises `KeyboardInterrupt`, matching the Global Constraints.
