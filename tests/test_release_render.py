import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "release"))

import render  # noqa: E402
import versioning  # noqa: E402

REPO = "https://github.com/kgorczowski/anonimize"


def _sums(version):
    """A fake SHA-256 per archive, distinct so mix-ups show."""
    return {
        versioning.archive_name(version, platform): f"{index:x}" * 64
        for index, platform in enumerate(versioning.PLATFORMS, start=10)
    }


def _url(version, platform):
    asset = versioning.archive_name(version, platform)
    return f"{REPO}/releases/download/v{version}/{asset}"


def test_parse_sums_reads_sha256sum_output():
    text = (
        f"{'a' * 64}  anonimize-1.2.3-windows-x64.zip\n"
        f"{'B' * 64} *anonimize_1.2.3_amd64.deb\n"
    )

    assert render.parse_sums(text) == {
        "anonimize-1.2.3-windows-x64.zip": "a" * 64,
        "anonimize_1.2.3_amd64.deb": "b" * 64,
    }


def test_formula_points_each_cpu_at_its_asset():
    sums = _sums("1.2.3")
    formula = render.render_formula("1.2.3", sums)

    for platform in ("macos-arm64", "macos-x64"):
        assert _url("1.2.3", platform) in formula
        assert sums[versioning.archive_name("1.2.3", platform)] in formula
    assert formula.index("on_arm") < formula.index(_url("1.2.3", "macos-arm64"))
    assert formula.index("on_intel") < formula.index(_url("1.2.3", "macos-x64"))
    assert 'version "1.2.3"' in formula
    assert 'depends_on "tesseract" => :recommended' in formula
    assert 'depends_on "unar" => :recommended' in formula
    assert "--check-tools" in formula


def test_formula_writes_the_launcher_into_bin():
    # Pathname#write_exec_script is called on a directory and writes one
    # script per target into it; called on bin/"anonimize" it turned that
    # path into a folder ("bin/anonimize: is a directory" in v1.0.0-rc.1).
    formula = render.render_formula("1.2.3", _sums("1.2.3"))

    assert 'bin.write_exec_script libexec/"anonimize"' in formula
    assert '(bin/"anonimize").write_exec_script' not in formula


def test_scoop_manifest():
    sums = _sums("1.2.3")
    manifest = json.loads(render.render_scoop("1.2.3", sums))

    assert manifest["version"] == "1.2.3"
    assert manifest["architecture"]["64bit"] == {
        "url": _url("1.2.3", "windows-x64"),
        "hash": sums["anonimize-1.2.3-windows-x64.zip"],
    }
    assert manifest["bin"] == "anonimize.exe"
    assert sorted(manifest["suggest"].values()) == ["main/7zip", "main/tesseract"]
    assert "--check-tools" in manifest["notes"]


def test_winget_manifests():
    sums = _sums("1.2.3")
    files = render.render_winget("1.2.3", sums)

    assert sorted(files) == [
        "kgorczowski.anonimize.installer.yaml",
        "kgorczowski.anonimize.locale.en-US.yaml",
        "kgorczowski.anonimize.yaml",
    ]
    for content in files.values():
        assert "PackageIdentifier: kgorczowski.anonimize" in content
        assert "PackageVersion: 1.2.3" in content
        assert "ManifestVersion: 1.10.0" in content

    installer = files["kgorczowski.anonimize.installer.yaml"]
    assert "InstallerType: zip" in installer
    assert "NestedInstallerType: portable" in installer
    assert "RelativeFilePath: anonimize.exe" in installer
    assert "PortableCommandAlias: anonimize" in installer
    assert _url("1.2.3", "windows-x64") in installer
    assert sums["anonimize-1.2.3-windows-x64.zip"].upper() in installer


def test_write_manifests_keeps_only_the_current_winget_version(tmp_path):
    winget = tmp_path / "release/winget/manifests/k/kgorczowski/anonimize"
    (winget / "0.9.0").mkdir(parents=True)
    (winget / "0.9.0" / "old.yaml").write_text("old", encoding="utf-8")

    render.write_manifests("1.2.3", _sums("1.2.3"), tmp_path)

    assert [p.name for p in winget.iterdir()] == ["1.2.3"]
    assert len(list((winget / "1.2.3").iterdir())) == 3
    assert (tmp_path / "Formula" / "anonimize.rb").is_file()
    assert (tmp_path / "bucket" / "anonimize.json").is_file()


def test_write_manifests_rejects_sums_missing_an_archive(tmp_path):
    sums = _sums("1.2.3")
    del sums["anonimize-1.2.3-macos-x64.tar.gz"]

    with pytest.raises(ValueError) as raised:
        render.write_manifests("1.2.3", sums, tmp_path)

    assert "anonimize-1.2.3-macos-x64.tar.gz" in str(raised.value)


@pytest.mark.parametrize(
    "tags, current, expected",
    [
        (["v0.9.0", "v1.0.0-rc.1", "v1.0.0", "v1.1.0"], "v1.1.0", "v1.0.0"),
        (["v1.0.0-rc.1"], "v1.0.0", None),
        (["v1.0.0", "v1.0.0-rc.2"], "v1.0.0-rc.2", None),
        (["v1.0.0", "v1.0.1-rc.1"], "v1.0.1-rc.1", "v1.0.0"),
        (["v1.0.0", "v1.10.0", "v1.9.0"], "v1.11.0", "v1.10.0"),
    ],
)
def test_previous_final_tag(tags, current, expected):
    assert render.previous_final_tag(tags, current) == expected


def test_release_notes_for_a_prerelease():
    notes = render.render_release_notes("1.0.0-rc.1", None)

    assert f"brew tap kgorczowski/anonimize {REPO}" in notes
    assert f"scoop bucket add anonimize {REPO}" in notes
    assert "sudo apt install ./anonimize_1.0.0-rc.1_amd64.deb" in notes
    assert (
        f"{REPO}/releases/download/v1.0.0-rc.1/anonimize_1.0.0-rc.1_amd64.deb"
        in notes
    )
    assert "anonimize --check-tools" in notes
    assert "SHA256SUMS" in notes
    assert "First packaged release." in notes


def test_release_notes_list_changes():
    notes = render.render_release_notes("1.2.3", ["fix: a", "feat: b"])

    assert "- fix: a\n" in notes
    assert "- feat: b\n" in notes
    assert "First packaged release." not in notes
