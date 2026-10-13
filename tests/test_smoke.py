from pathlib import Path

import anonymize
from anonymize import ProgressBar, format_duration


def test_format_duration_seconds():
    assert format_duration(30) == "30s"


def test_progress_bar_survives_a_clock_that_has_not_advanced(
    monkeypatch, capsys
):
    # Python before 3.13 on Windows has a monotonic clock that only ticks
    # every ~15.6 ms, so a fast first file leaves zero measurable elapsed
    # time. The update must still render instead of aborting the whole run.
    monkeypatch.setattr(anonymize.time, "monotonic", lambda: 1000.0)

    bar = ProgressBar(total=3)
    bar.update(1, Path("a.txt"))

    assert "(1/3)" in capsys.readouterr().out
