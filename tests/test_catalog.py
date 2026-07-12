from pathlib import Path

import pytest

from x4analyzer.gamedata.catalog import GameFiles


def make_cat(directory: Path, name: str, files: dict[str, bytes]) -> None:
    lines = []
    blob = b""
    for path, content in files.items():
        lines.append(f"{path} {len(content)} 1700000000 " + "0" * 32)
        blob += content
    (directory / f"{name}.cat").write_text("\n".join(lines) + "\n")
    (directory / f"{name}.dat").write_bytes(blob)


@pytest.fixture
def game_dir(tmp_path: Path) -> Path:
    make_cat(tmp_path, "01", {
        "libraries/wares.xml": b"<wares>base</wares>",
        "t/0001-l044.xml": b"<language id='44'/>",
    })
    make_cat(tmp_path, "02", {
        "libraries/wares.xml": b"<wares>patched by 02</wares>",
    })
    ext = tmp_path / "extensions" / "ego_dlc_test"
    ext.mkdir(parents=True)
    make_cat(ext, "ext_01", {
        "libraries/wares.xml": b"<diff>dlc wares</diff>",
        "maps/galaxy.xml": b"<diff/>",
    })
    # signature cats must be ignored
    make_cat(tmp_path, "01_sig", {"libraries/wares.xml": b"BOGUS"})
    return tmp_path


def test_higher_cat_wins(game_dir: Path) -> None:
    gf = GameFiles(game_dir, extensions=[])
    assert gf.read_bytes("libraries/wares.xml") == b"<wares>patched by 02</wares>"


def test_extension_paths_are_namespaced(game_dir: Path) -> None:
    gf = GameFiles(game_dir, extensions=["ego_dlc_test"])
    assert gf.read_bytes("extensions/ego_dlc_test/libraries/wares.xml") \
        == b"<diff>dlc wares</diff>"
    # base file untouched by extension
    assert gf.read_bytes("libraries/wares.xml") == b"<wares>patched by 02</wares>"
    assert gf.source_of("extensions/ego_dlc_test/maps/galaxy.xml") == "ego_dlc_test"


def test_official_dlc_autodetected(game_dir: Path) -> None:
    gf = GameFiles(game_dir)
    assert gf.extensions == ["ego_dlc_test"]


def test_loose_file_overrides_catalog(game_dir: Path) -> None:
    loose = game_dir / "libraries" / "wares.xml"
    loose.parent.mkdir(parents=True)
    loose.write_bytes(b"<wares>loose</wares>")
    gf = GameFiles(game_dir, extensions=[])
    assert gf.read_bytes("libraries/wares.xml") == b"<wares>loose</wares>"


def test_glob(game_dir: Path) -> None:
    gf = GameFiles(game_dir, extensions=["ego_dlc_test"])
    assert gf.glob(r".*wares\.xml$") == [
        "extensions/ego_dlc_test/libraries/wares.xml",
        "libraries/wares.xml",
    ]
