from anonymize import format_duration


def test_format_duration_seconds():
    assert format_duration(30) == "30s"
