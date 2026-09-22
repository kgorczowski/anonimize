import json
import sys
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


def _scripted_select(answers, captured=None):
    """Returns a fake `questionary.select` that ignores its arguments and
    returns the next scripted answer on each call, in order. If `captured`
    is given (a list), each call's `choices` are appended to it as a list
    of titles, so a test can assert on what was actually offered."""
    it = iter(answers)

    def fake_select(message, choices):
        if captured is not None:
            captured.append([c.title for c in choices])
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


def test_browse_for_directory_never_lists_files_as_choices(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    (tmp_path / "sub").mkdir()
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")

    captured = []
    monkeypatch.setattr(
        questionary, "select",
        _scripted_select([("select", None)], captured=captured),
    )

    anonymize.browse_for_directory(tmp_path)

    assert "notes.txt" not in captured[0]


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


def test_browse_for_replacements_file_only_lists_json_files(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    (tmp_path / "repl.json").write_text("{}", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")

    captured = []
    monkeypatch.setattr(
        questionary, "select",
        _scripted_select([("choose", tmp_path / "repl.json")], captured=captured),
    )

    anonymize.browse_for_replacements_file(tmp_path)

    assert "notes.txt" not in captured[0]
    assert "repl.json" in captured[0]


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


def test_prompt_output_directory_falls_back_to_cwd_when_parent_missing(
    tmp_path, monkeypatch
):
    questionary = pytest.importorskip("questionary")

    # Deliberately do NOT create tmp_path / "anonimized" -- this is the
    # real-world case this fallback exists for: default_output's parent
    # doesn't exist yet at this point in the wizard flow (it's only
    # created later, inside run_anonymization).
    cwd_dir = tmp_path / "cwd_target"
    cwd_dir.mkdir()
    monkeypatch.setattr(Path, "cwd", staticmethod(lambda: cwd_dir))

    default_output = tmp_path / "anonimized" / "src"

    monkeypatch.setattr(questionary, "confirm", _scripted_confirm([False]))
    monkeypatch.setattr(
        questionary, "select", _scripted_select([("select", None)])
    )

    result = anonymize.prompt_output_directory(default_output)

    assert result == cwd_dir.resolve()


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
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

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
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
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


def test_run_interactive_mode_without_a_tty_shows_hint(monkeypatch, capsys):
    questionary = pytest.importorskip("questionary")

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with pytest.raises(SystemExit):
        anonymize.run_interactive_mode()

    assert "needs a terminal" in capsys.readouterr().err


def test_main_with_no_args_enters_interactive_mode(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["anonymize.py"])
    called = []
    monkeypatch.setattr(
        anonymize, "run_interactive_mode", lambda: called.append(True)
    )
    anonymize.main()
    assert called == [True]


def test_manage_replacements_dictionary_rejects_malformed_json(
    tmp_path, capsys
):
    pytest.importorskip("questionary")

    path = tmp_path / "repl.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(SystemExit):
        anonymize.manage_replacements_dictionary(path)

    assert (
        "ERROR: cannot load replacement map:" in capsys.readouterr().err
    )


def test_manage_replacements_dictionary_rejects_non_dict_json(
    tmp_path, capsys
):
    pytest.importorskip("questionary")

    path = tmp_path / "repl.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(SystemExit):
        anonymize.manage_replacements_dictionary(path)

    assert (
        "ERROR: cannot load replacement map:" in capsys.readouterr().err
    )
