import json
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
