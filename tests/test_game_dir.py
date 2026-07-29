"""Steam-library detection of the X4 installation (config.find_game_dir)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from x4analyzer import config
from x4analyzer.config import Config, find_game_dir
from x4analyzer.gamedata.catalog import GameFiles

MODERN_VDF = """"libraryfolders"
{
\t"0"
\t{
\t\t"path"\t\t"@STEAM@"
\t\t"label"\t\t""
\t\t"apps"
\t\t{
\t\t\t"228980"\t\t"610088130"
\t\t}
\t}
\t"1"
\t{
\t\t"path"\t\t"@EXTRA@"
\t\t"label"\t\t""
\t\t"apps"
\t\t{
\t\t\t"392160"\t\t"34930397255"
\t\t}
\t}
}
"""

# Pre-2021 Steam: the numbered key IS the path, there is no "path" key.
LEGACY_VDF = """"LibraryFolders"
{
\t"TimeNextStatsReport"\t\t"1500000000"
\t"ContentStatsID"\t\t"123456789"
\t"1"\t\t"@EXTRA@"
}
"""


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Pretend to be a Linux machine with an empty home and no override."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv(config.GAME_DIR_ENV, raising=False)
    return home


def make_steam(home: Path) -> Path:
    root = home / ".local" / "share" / "Steam"
    (root / "steamapps").mkdir(parents=True)
    return root


def install(library: Path, name: str = "X4 Foundations") -> Path:
    game = library / "steamapps" / "common" / name
    game.mkdir(parents=True)
    return game


def vdf(template: str, steam: Path, extra: object) -> str:
    return template.replace("@STEAM@", str(steam)).replace("@EXTRA@", str(extra))


def write_vdf(steam: Path, text: str) -> None:
    (steam / "steamapps" / "libraryfolders.vdf").write_text(text)


def test_finds_install_in_non_default_library(isolated_home, tmp_path):
    """The real-world case: the library lives outside the Steam root."""
    steam = make_steam(isolated_home)
    extra = tmp_path / "games" / "SteamLibrary"
    game = install(extra)
    write_vdf(steam, vdf(MODERN_VDF, steam, extra))
    assert find_game_dir() == game


def test_finds_install_in_steam_root_library(isolated_home, tmp_path):
    steam = make_steam(isolated_home)
    extra = tmp_path / "games" / "SteamLibrary"
    extra.mkdir(parents=True)
    game = install(steam)
    write_vdf(steam, vdf(MODERN_VDF, steam, extra))
    assert find_game_dir() == game


def test_legacy_vdf_format(isolated_home, tmp_path):
    steam = make_steam(isolated_home)
    extra = tmp_path / "games" / "SteamLibrary"
    game = install(extra)
    write_vdf(steam, vdf(LEGACY_VDF, steam, extra))
    assert find_game_dir() == game


def test_malformed_vdf_does_not_crash(isolated_home):
    steam = make_steam(isolated_home)
    write_vdf(steam, '"libraryfolders" {{{ "path" not even close\x00')
    assert find_game_dir() is None
    # ... and the install under the Steam root itself is still found.
    game = install(steam)
    assert find_game_dir() == game


def test_no_vdf_at_all(isolated_home):
    steam = make_steam(isolated_home)
    game = install(steam)
    assert find_game_dir() == game


def test_no_steam_at_all(isolated_home):
    assert find_game_dir() is None


def test_case_insensitive_directory_name(isolated_home):
    steam = make_steam(isolated_home)
    game = install(steam, "x4 foundations")
    assert find_game_dir() == game


def test_env_override_wins(isolated_home, tmp_path, monkeypatch):
    steam = make_steam(isolated_home)
    install(steam)
    elsewhere = tmp_path / "manual" / "X4 Foundations"
    elsewhere.mkdir(parents=True)
    monkeypatch.setenv(config.GAME_DIR_ENV, str(elsewhere))
    assert find_game_dir() == elsewhere


def test_env_override_ignored_when_missing(isolated_home, monkeypatch):
    steam = make_steam(isolated_home)
    game = install(steam)
    monkeypatch.setenv(config.GAME_DIR_ENV, "/definitely/not/here")
    assert find_game_dir() == game


def test_windows_escaped_paths_are_unescaped(isolated_home):
    steam = make_steam(isolated_home)
    write_vdf(steam, vdf(MODERN_VDF, steam, "D:\\\\SteamLibrary"))
    libs = [str(p) for p in config._steam_libraries(steam)]
    assert "D:\\SteamLibrary" in libs


def test_config_autodetects_on_construction(isolated_home):
    steam = make_steam(isolated_home)
    game = install(steam)
    cfg = Config()
    assert cfg.game_dir == game
    assert cfg.resolve_game_dir() == game


def test_config_keeps_explicit_game_dir(isolated_home, tmp_path):
    steam = make_steam(isolated_home)
    install(steam)
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    assert Config(game_dir=explicit).game_dir == explicit


def test_config_game_dir_none_without_steam(isolated_home):
    assert Config().game_dir is None


def test_resolve_game_dir_error_is_actionable(isolated_home):
    with pytest.raises(FileNotFoundError) as exc:
        Config().resolve_game_dir()
    msg = str(exc.value)
    assert config.GAME_DIR_ENV in msg and "--game-dir" in msg


def test_gamefiles_rejects_none_clearly():
    """A None install must not die on None.is_dir() inside GameFiles."""
    with pytest.raises(FileNotFoundError) as exc:
        GameFiles(None)  # type: ignore[arg-type]
    assert config.GAME_DIR_ENV in str(exc.value)


# Probed before any monkeypatching, so it reflects the real machine.
REAL_GAME_DIR = find_game_dir()


@pytest.mark.skipif(REAL_GAME_DIR is None,
                    reason="no X4 installation on this machine")
def test_detects_the_real_install(monkeypatch):
    """On a machine with X4, detection must find it with no help."""
    monkeypatch.undo()  # drop the fake-home fixture's patches
    monkeypatch.delenv(config.GAME_DIR_ENV, raising=False)
    cfg = Config()
    assert cfg.game_dir is not None
    assert (cfg.game_dir / "extensions").is_dir()
