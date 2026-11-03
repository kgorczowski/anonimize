import re
import sys

import pytest

import anonymize


def _run_main(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["anonymize.py", *args])
    anonymize.main()


def test_version_matches_release_format():
    # The release workflow compares the tag with this value; the package
    # formats only accept plain X.Y.Z or an X.Y.Z-rc.N pre-release.
    assert re.fullmatch(r"\d+\.\d+\.\d+(-rc\.\d+)?", anonymize.__version__)


def test_version_flag_prints_version_and_exits_zero(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exited:
        _run_main(monkeypatch, "--version")

    assert exited.value.code == 0
    assert capsys.readouterr().out == f"anonimize {anonymize.__version__}\n"


def test_check_tools_flag_prints_report_and_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(
        anonymize, "report_optional_tools", lambda: print("TOOLS REPORT")
    )

    with pytest.raises(SystemExit) as exited:
        _run_main(monkeypatch, "--check-tools")

    assert exited.value.code in (0, None)
    assert "TOOLS REPORT" in capsys.readouterr().out


def test_command_name_in_source_mode(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert anonymize.command_name() == "python anonymize.py"


def test_command_name_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert anonymize.command_name() == "anonimize"


def test_terminal_hint_names_the_frozen_command(monkeypatch, capsys):
    pytest.importorskip("questionary")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with pytest.raises(SystemExit) as exited:
        anonymize.run_interactive_mode()

    err = capsys.readouterr().err
    assert exited.value.code == 1
    assert "anonimize <source> <replacements.json>" in err
    assert "python anonymize.py" not in err


# The frozen Linux program puts its bundled libraries first through
# LD_LIBRARY_PATH; external tools started from it (tesseract, unar, 7z)
# inherited that and loaded the bundled, older libstdc++ ("GLIBCXX_3.4.32
# not found" on Ubuntu 24.04).
def test_frozen_program_gives_child_processes_the_original_library_path(
    monkeypatch,
):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/usr/lib/anonimize/_internal")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/opt/users/own/lib")

    anonymize.restore_child_library_path()

    assert anonymize.os.environ["LD_LIBRARY_PATH"] == "/opt/users/own/lib"


def test_frozen_program_drops_a_library_path_the_user_never_set(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/usr/lib/anonimize/_internal")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)

    anonymize.restore_child_library_path()

    assert "LD_LIBRARY_PATH" not in anonymize.os.environ


def test_source_program_leaves_the_library_path_alone(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/somewhere")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)

    anonymize.restore_child_library_path()

    assert anonymize.os.environ["LD_LIBRARY_PATH"] == "/somewhere"
