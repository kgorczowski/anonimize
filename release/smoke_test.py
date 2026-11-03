"""
Black-box test of a built anonimize program: runs it the way a user would
and checks the result, without importing anything from it.

    python release/smoke_test.py fixtures <dir>
    python release/smoke_test.py check --fixtures <dir> --version 1.0.0 -- <command...>

`fixtures` needs the project's Python dependencies (it writes Office, PDF
and archive files). `check` uses only the standard library, so it also runs
in bare Debian/Ubuntu containers and after package-manager installs.

The program reports a file it could not process as an error and leaves it
out of the output instead of crashing, and still exits 0. A module that
PyInstaller failed to bundle therefore shows up as a non-zero "Errors"
count and a missing output file, never as a crash: that is what `check`
looks at.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
RAR_FIXTURE = ROOT / "tests" / "fixtures" / "sample_rar5_compressed.rar"

# Spaces on purpose: real client folders have them, and they must survive
# every launcher (brew wrapper, Scoop shim, winget link, /usr/bin symlink).
SOURCE_NAME = "client project"
OUTPUT_NAME = "out dir"
TERM = "AcmeCorp"
PLACEHOLDER = "Company1"
EMAIL = "jan.kowalski@example.com"
PESEL = "44051401458"  # valid checksum, so the PII redaction must catch it

TIMEOUT_SECONDS = 600
TEXT_SUFFIXES = {".txt", ".md"}

EXPECTATIONS = {
    "must_exist": [
        "Company1/notes.txt",
        "Company1_summary.txt",
        "docs/report.md",
        "docs/budget.md",
        "docs/slides.md",
        "docs/contract.md",
        "docs/scan.md",
        "archives/bundle/inner_zip.txt",
        "archives/data/inner_tar.txt",
        "archives/packed/inner_7z.txt",
        "archives/sample_rar5_compressed/hello.txt",
        "images/logo.png",
    ],
    # Case-insensitive, like the OCR test in tests/test_pdf.py.
    "must_contain": {
        "Company1/notes.txt": PLACEHOLDER,
        "docs/report.md": PLACEHOLDER,
        "docs/scan.md": "SCANNED",
        "archives/packed/inner_7z.txt": PLACEHOLDER,
        "archives/sample_rar5_compressed/hello.txt": "[EMAIL]",
    },
    # Blacked out, so it must differ from the source image.
    "changed": ["images/logo.png"],
    "forbidden": [TERM.lower(), EMAIL, PESEL, "jan@example.com"],
}


def make_fixtures(root: Path) -> None:
    """Writes a source tree covering every processing path, plus the
    replacements file and expectations.json that `check` reads."""
    import docx
    import openpyxl
    import pptx
    import py7zr
    import pymupdf
    from PIL import Image, ImageDraw

    source = root / SOURCE_NAME
    for folder in ("AcmeCorp", "docs", "archives", "images"):
        (source / folder).mkdir(parents=True, exist_ok=True)

    (source / "AcmeCorp" / "notes.txt").write_text(
        f"Contact {TERM}: {EMAIL}, PESEL {PESEL}\n", encoding="utf-8"
    )
    (source / "acmecorp_summary.txt").write_text(
        f"Summary for {TERM.upper()}\n", encoding="utf-8"
    )

    document = docx.Document()
    document.add_paragraph(f"{TERM} quarterly report")
    document.save(source / "docs" / "report.docx")

    workbook = openpyxl.Workbook()
    workbook.active["A1"] = f"{TERM} budget"
    workbook.save(source / "docs" / "budget.xlsx")

    presentation = pptx.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = f"{TERM} roadmap"
    presentation.save(source / "docs" / "slides.pptx")

    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), f"{TERM} contract")
    pdf.save(source / "docs" / "contract.pdf")
    pdf.close()

    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)

        # Image-only page, as in tests/test_pdf.py: only OCR finds the text.
        image = Image.new("RGB", (600, 200), "white")
        ImageDraw.Draw(image).text((20, 80), "SCANNED TEXT", fill="black")
        scan_image = scratch / "scan.png"
        image.save(scan_image)
        pdf = pymupdf.open()
        pdf.new_page().insert_image(
            pymupdf.Rect(0, 0, 600, 200), filename=str(scan_image)
        )
        pdf.save(source / "docs" / "scan.pdf")
        pdf.close()

        inner = {}
        for name in ("inner_zip.txt", "inner_tar.txt", "inner_7z.txt"):
            inner[name] = scratch / name
            inner[name].write_text(f"{TERM} archived\n", encoding="utf-8")

        with zipfile.ZipFile(source / "archives" / "bundle.zip", "w") as archive:
            archive.write(inner["inner_zip.txt"], "inner_zip.txt")
        with tarfile.open(source / "archives" / "data.tar.gz", "w:gz") as archive:
            archive.add(inner["inner_tar.txt"], "inner_tar.txt")
        with py7zr.SevenZipFile(source / "archives" / "packed.7z", "w") as archive:
            archive.write(inner["inner_7z.txt"], "inner_7z.txt")

    shutil.copyfile(RAR_FIXTURE, source / "archives" / RAR_FIXTURE.name)
    Image.new("RGB", (64, 32), "red").save(source / "images" / "logo.png")

    (root / "replacements.json").write_text(
        json.dumps({TERM: PLACEHOLDER}), encoding="utf-8"
    )
    (root / "expectations.json").write_text(
        json.dumps(EXPECTATIONS, indent=2), encoding="utf-8"
    )


def _resolve(command: List[str]) -> List[str]:
    """
    Makes the command independent of the working directory: the full run
    starts it from the fixtures folder. A bare name is looked up on PATH,
    a relative path that exists (`anonymize.py`) becomes absolute.
    """
    resolved = []
    for index, part in enumerate(command):
        if index == 0 and not any(sep in part for sep in ("/", "\\")):
            part = shutil.which(part) or part
        elif Path(part).exists():
            part = str(Path(part).resolve())
        resolved.append(part)
    return resolved


def _tail(result: subprocess.CompletedProcess, lines: int = 20) -> str:
    output = (result.stdout or "") + (result.stderr or "")
    return "\n".join(output.splitlines()[-lines:])


def run_checks(command: List[str], fixtures: Path, version: str) -> List[str]:
    """Runs the program; returns failure messages (empty list = passed)."""
    command = _resolve(command)
    fixtures = Path(fixtures).resolve()
    expectations = json.loads(
        (fixtures / "expectations.json").read_text(encoding="utf-8")
    )
    failures: List[str] = []

    def run(*args: str, cwd: Optional[Path] = None):
        # stdin is an empty pipe, not DEVNULL: on Windows isatty() is True
        # for the NUL device, so DEVNULL would look like a terminal.
        return subprocess.run(
            [*command, *args],
            cwd=cwd,
            input="",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
        )

    try:
        result = run("--version")
        if result.returncode != 0 or f"anonimize {version}" not in result.stdout:
            failures.append(
                f"--version: expected 'anonimize {version}', got:\n{_tail(result)}"
            )

        result = run("--check-tools")
        if (
            result.returncode != 0
            or "[missing]" in result.stdout
            or result.stdout.count("[ok]") < 2
        ):
            failures.append(
                "--check-tools: both optional tools must be [ok]:\n"
                + _tail(result)
            )

        # No arguments and no terminal: questionary is imported before the
        # TTY check, so this message also proves it was bundled.
        result = run()
        if (
            result.returncode == 0
            or "Interactive mode needs a terminal" not in result.stderr
        ):
            failures.append(
                "no arguments without a TTY: expected the 'needs a terminal' "
                f"message:\n{_tail(result)}"
            )

        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch) / OUTPUT_NAME
            # Relative arguments from the fixtures folder, as a user would.
            result = run(
                SOURCE_NAME,
                "replacements.json",
                "--output",
                str(output),
                cwd=fixtures,
            )
            if result.returncode != 0 or not re.search(
                r"^Errors\s*:\s*0\s*$", result.stdout, re.MULTILINE
            ):
                failures.append(
                    "full run: expected exit 0 and 'Errors : 0', got exit "
                    f"{result.returncode}:\n{_tail(result)}"
                )
            failures.extend(
                _check_output(output, fixtures / SOURCE_NAME, expectations)
            )
    except FileNotFoundError:
        failures.append(f"program not found: {command[0]}")
    except subprocess.TimeoutExpired as exc:
        failures.append(f"timed out after {exc.timeout}s: {exc.cmd}")

    return failures


def _check_output(output: Path, source: Path, expectations: dict) -> List[str]:
    failures = []

    for relative in expectations["must_exist"]:
        if not (output / relative).is_file():
            failures.append(f"missing output file: {relative}")

    for relative, expected in expectations["must_contain"].items():
        path = output / relative
        if path.is_file():
            content = path.read_text(encoding="utf-8", errors="replace")
            if expected.lower() not in content.lower():
                failures.append(f"{relative} does not contain {expected!r}")

    for relative in expectations["changed"]:
        path = output / relative
        if path.is_file() and path.read_bytes() == (source / relative).read_bytes():
            failures.append(f"{relative} was copied unchanged")

    if output.is_dir():
        for path in sorted(output.rglob("*")):
            relative = path.relative_to(output).as_posix()
            for term in expectations["forbidden"]:
                if term.lower() in relative.lower():
                    failures.append(f"output path {relative!r} contains {term!r}")
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                content = path.read_text(encoding="utf-8", errors="replace")
                for term in expectations["forbidden"]:
                    if term.lower() in content.lower():
                        failures.append(f"{relative} contains {term!r}")

    return failures


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    fixtures = commands.add_parser("fixtures", help="write the test fixtures")
    fixtures.add_argument("dir", type=Path)

    check = commands.add_parser("check", help="test a built program")
    check.add_argument("--fixtures", type=Path, required=True)
    check.add_argument("--version", required=True)
    check.add_argument("program", nargs="+", help="command to run, after --")

    args = parser.parse_args(argv)

    if args.command == "fixtures":
        make_fixtures(args.dir)
        print(f"fixtures written to {args.dir}")
        return 0

    failures = run_checks(args.program, args.fixtures, args.version)
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"smoke test FAILED ({len(failures)} problem(s))")
        return 1
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
