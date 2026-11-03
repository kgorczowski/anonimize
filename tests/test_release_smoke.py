import shutil
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "release"))

import anonymize  # noqa: E402
import smoke_test  # noqa: E402


def _optional_tools_available() -> bool:
    try:
        import pytesseract
    except ImportError:
        return False
    tesseract = shutil.which("tesseract") or anonymize.locate_tesseract()
    rar = (
        shutil.which("unrar")
        or shutil.which("unar")
        or anonymize.locate_rar_tool()
    )
    return bool(pytesseract and tesseract and rar)


# Like the OCR and RAR tests: skipped without the tools, and
# scripts/run-tests.sh turns that skip into a CI failure.
@pytest.mark.skipif(
    not _optional_tools_available(),
    reason="Tesseract OCR or a RAR extractor not installed",
)
def test_smoke_check_passes_for_the_source_program(tmp_path):
    fixtures = tmp_path / "fx"
    smoke_test.make_fixtures(fixtures)

    failures = smoke_test.run_checks(
        [sys.executable, str(ROOT / "anonymize.py")],
        fixtures,
        anonymize.__version__,
    )

    assert failures == []


LEAKY_PROGRAM = textwrap.dedent(
    """
    import shutil, sys

    args = sys.argv[1:]
    if args == ["--version"]:
        print("anonimize VERSION")
    elif args == ["--check-tools"]:
        print("  [ok]      Tesseract OCR (scanned PDF pages): x")
        print("  [ok]      RAR extraction (.rar archives): y")
    elif not args:
        print("Interactive mode needs a terminal.", file=sys.stderr)
        sys.exit(1)
    else:
        shutil.copytree(args[0], args[args.index("--output") + 1])
        print("Errors            : 0")
    """
)


def test_smoke_check_catches_a_program_that_copies_files_raw(tmp_path):
    fixtures = tmp_path / "fx"
    smoke_test.make_fixtures(fixtures)
    leaky = tmp_path / "leaky.py"
    leaky.write_text(
        LEAKY_PROGRAM.replace("VERSION", anonymize.__version__),
        encoding="utf-8",
    )

    failures = smoke_test.run_checks(
        [sys.executable, str(leaky)], fixtures, anonymize.__version__
    )

    assert any("acmecorp" in failure.lower() for failure in failures)
