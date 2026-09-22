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
