import pytest

import anonymize


def _no_tools(monkeypatch):
    monkeypatch.setattr(anonymize.shutil, "which", lambda name: None)
    monkeypatch.setattr(anonymize, "locate_tesseract", lambda: None)
    monkeypatch.setattr(anonymize, "locate_rar_tool", lambda: None)


def test_report_optional_tools_lists_what_is_on_path(monkeypatch, capsys):
    monkeypatch.setattr(
        anonymize.shutil, "which", lambda name: f"/usr/bin/{name}"
    )
    monkeypatch.setattr(anonymize, "locate_tesseract", lambda: None)
    monkeypatch.setattr(anonymize, "locate_rar_tool", lambda: None)

    anonymize.report_optional_tools()

    out = capsys.readouterr().out

    assert "Optional system tools:" in out
    assert (
        "[ok]      Tesseract OCR (scanned PDF pages): /usr/bin/tesseract"
        in out
    )
    assert "[ok]      RAR extraction (.rar archives): /usr/bin/unar" in out
    assert "[missing]" not in out


def test_report_optional_tools_counts_default_folder_installs_as_found(
    monkeypatch, capsys
):
    monkeypatch.setattr(anonymize.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        anonymize,
        "locate_tesseract",
        lambda: r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    )
    monkeypatch.setattr(
        anonymize,
        "locate_rar_tool",
        lambda: ("SEVENZIP_TOOL", r"C:\Program Files\7-Zip\7z.exe"),
    )

    anonymize.report_optional_tools()

    out = capsys.readouterr().out

    assert (
        r"[ok]      Tesseract OCR (scanned PDF pages): "
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    ) in out
    assert (
        r"[ok]      RAR extraction (.rar archives): "
        r"C:\Program Files\7-Zip\7z.exe"
    ) in out
    assert "[missing]" not in out


@pytest.mark.parametrize(
    "platform,tesseract_hint,rar_hint",
    [
        ("darwin", "brew install tesseract", "brew install unar"),
        (
            "linux",
            "sudo apt install tesseract-ocr",
            "sudo apt install unar",
        ),
        (
            "win32",
            "winget install UB-Mannheim.TesseractOCR",
            "winget install 7zip.7zip",
        ),
    ],
)
def test_report_optional_tools_shows_the_install_hint_for_this_os(
    monkeypatch, capsys, platform, tesseract_hint, rar_hint
):
    _no_tools(monkeypatch)
    monkeypatch.setattr(anonymize.sys, "platform", platform)

    anonymize.report_optional_tools()

    out = capsys.readouterr().out

    assert (
        "[missing] Tesseract OCR (scanned PDF pages) - install with: "
        f"{tesseract_hint}"
    ) in out
    assert (
        "[missing] RAR extraction (.rar archives) - install with: "
        f"{rar_hint}"
    ) in out


def test_report_optional_tools_reports_each_tool_independently(
    monkeypatch, capsys
):
    _no_tools(monkeypatch)
    monkeypatch.setattr(
        anonymize, "locate_tesseract", lambda: "/opt/tesseract"
    )

    anonymize.report_optional_tools()

    out = capsys.readouterr().out

    assert "[ok]      Tesseract OCR (scanned PDF pages): /opt/tesseract" in out
    assert "[missing] RAR extraction (.rar archives)" in out
