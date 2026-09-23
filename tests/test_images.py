from pathlib import Path

import pytest

from anonymize import path_matches_redaction_signal, blackout_image


# ------------------------------------------------------------
# path_matches_redaction_signal
# ------------------------------------------------------------

def test_path_matches_redaction_signal_filename_matches_dictionary():
    result = path_matches_redaction_signal(
        Path("src/assets/BDR_report.png"), {"BDR": "namespace1"}
    )
    assert result is True


def test_path_matches_redaction_signal_parent_folder_matches_dictionary():
    result = path_matches_redaction_signal(
        Path("src/BDR/report.png"), {"BDR": "namespace1"}
    )
    assert result is True


def test_path_matches_redaction_signal_filename_contains_keyword():
    result = path_matches_redaction_signal(
        Path("src/assets/company_logo.png"), {}
    )
    assert result is True


def test_path_matches_redaction_signal_parent_folder_contains_keyword():
    result = path_matches_redaction_signal(Path("src/icons/pic.png"), {})
    assert result is True


@pytest.mark.parametrize(
    "keyword", ["logo", "icon", "brand", "avatar", "banner", "trademark"]
)
def test_path_matches_redaction_signal_covers_every_keyword(keyword):
    result = path_matches_redaction_signal(
        Path(f"src/{keyword}_asset.png"), {}
    )
    assert result is True


def test_path_matches_redaction_signal_is_case_insensitive():
    result = path_matches_redaction_signal(Path("src/LOGO.png"), {})
    assert result is True


def test_path_matches_redaction_signal_returns_false_when_nothing_matches():
    result = path_matches_redaction_signal(
        Path("src/photos/vacation.png"), {"BDR": "namespace1"}
    )
    assert result is False


def test_path_matches_redaction_signal_only_checks_filename_and_immediate_parent():
    # A match further up the ancestor chain than the immediate parent
    # must NOT trigger redaction -- only the file's own name and its
    # direct containing folder are checked.
    result = path_matches_redaction_signal(
        Path("BDR/sub/unrelated/photo.png"), {"BDR": "namespace1"}
    )
    assert result is False


# ------------------------------------------------------------
# blackout_image
# ------------------------------------------------------------

def test_blackout_image_preserves_png_dimensions_all_black(tmp_path):
    from PIL import Image

    source = tmp_path / "logo.png"
    Image.new("RGB", (40, 20), color=(255, 0, 0)).save(source)

    destination = tmp_path / "out" / "logo.png"
    blackout_image(source, destination)

    with Image.open(destination) as result:
        assert result.size == (40, 20)
        assert result.convert("RGB").getextrema() == ((0, 0), (0, 0), (0, 0))


def test_blackout_image_preserves_jpeg_dimensions_all_black(tmp_path):
    from PIL import Image

    source = tmp_path / "brand.jpg"
    Image.new("RGB", (60, 30), color=(0, 255, 0)).save(source)

    destination = tmp_path / "out" / "brand.jpg"
    blackout_image(source, destination)

    with Image.open(destination) as result:
        assert result.size == (60, 30)
        # JPEG is lossy -- allow a small tolerance instead of exact zero.
        for lo, hi in result.convert("RGB").getextrema():
            assert hi < 10


def test_blackout_image_preserves_bmp_dimensions_all_black(tmp_path):
    from PIL import Image

    source = tmp_path / "icon.bmp"
    Image.new("RGB", (16, 16), color=(0, 0, 255)).save(source)

    destination = tmp_path / "out" / "icon.bmp"
    blackout_image(source, destination)

    with Image.open(destination) as result:
        assert result.size == (16, 16)
        assert result.convert("RGB").getextrema() == ((0, 0), (0, 0), (0, 0))


def test_blackout_image_svg_uses_width_height_attributes(tmp_path):
    source = tmp_path / "icon.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="32">'
        '<circle cx="10" cy="10" r="5" fill="red"/></svg>',
        encoding="utf-8",
    )

    destination = tmp_path / "out" / "icon.svg"
    blackout_image(source, destination)

    content = destination.read_text(encoding="utf-8")
    assert 'width="64"' in content
    assert 'height="32"' in content
    assert 'fill="black"' in content
    assert "red" not in content
    assert "circle" not in content


def test_blackout_image_svg_falls_back_to_viewbox(tmp_path):
    source = tmp_path / "logo.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">'
        '<rect width="100" height="50" fill="blue"/></svg>',
        encoding="utf-8",
    )

    destination = tmp_path / "out" / "logo.svg"
    blackout_image(source, destination)

    content = destination.read_text(encoding="utf-8")
    assert 'width="100"' in content
    assert 'height="50"' in content
    assert "blue" not in content


def test_blackout_image_svg_falls_back_to_default_dimensions_when_unparseable(
    tmp_path,
):
    source = tmp_path / "broken_logo.svg"
    source.write_text("<svg>not really valid</svg>", encoding="utf-8")

    destination = tmp_path / "out" / "broken_logo.svg"
    blackout_image(source, destination)

    content = destination.read_text(encoding="utf-8")
    assert 'fill="black"' in content
    assert "width=" in content
    assert "height=" in content
