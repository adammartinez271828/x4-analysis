"""Run configuration, platform-aware path discovery, and data locations.

Reference game data (ships/sectors/wares/...) ships inside the package;
`extract-gamedata` writes regenerated copies into a per-user data directory
which, when present, overrides the packaged files. Caches always live in the
user data directory (the package may be installed read-only, e.g. via uvx).
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

PACKAGE_DATA = Path(str(resources.files("x4analyzer") / "data"))


def user_data_dir() -> Path:
    """Writable per-user directory for caches and regenerated game data."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA",
                                   Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME",
                                   Path.home() / ".local" / "share"))
    return base / "x4analyzer"


def _documents_dirs() -> list[Path]:
    home = Path.home()
    dirs = [home / "Documents"]
    onedrive = os.environ.get("OneDrive")
    if onedrive:
        dirs.append(Path(onedrive) / "Documents")
    return dirs


def x4_user_dir_candidates() -> list[Path]:
    """Places the X4 user folder (holding <player-id>/save/) may live."""
    home = Path.home()
    if sys.platform == "win32":
        return [d / "Egosoft" / "X4" for d in _documents_dirs()]
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "EgoSoft" / "X4",
                home / "Documents" / "Egosoft" / "X4"]
    return [home / ".config" / "EgoSoft" / "X4",
            home / "Documents" / "Egosoft" / "X4"]


def _steam_roots() -> list[Path]:
    home = Path.home()
    if sys.platform == "win32":
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        return [Path(pf86) / "Steam"]
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "Steam"]
    return [home / ".local" / "share" / "Steam", home / ".steam" / "steam",
            Path(os.environ.get("XDG_DATA_HOME",
                                home / ".local" / "share")) / "Steam"]


def find_game_dir() -> Path | None:
    """Locate the X4 installation via Steam library folders."""
    libraries: list[Path] = []
    for root in _steam_roots():
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        libraries.append(root)
        try:
            for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(
                    encoding="utf-8", errors="replace")):
                libraries.append(Path(m.group(1).replace("\\\\", "\\")))
        except OSError:
            continue
    for lib in libraries:
        candidate = lib / "steamapps" / "common" / "X4 Foundations"
        if candidate.is_dir():
            return candidate
    return None


@dataclass
class Config:
    # X4 user folder (the one containing <player-id>/save/). None = search
    # the platform-standard locations.
    x4_user_dir: Path | None = None

    # X4 installation (for `extract-gamedata`). None = detect via Steam.
    game_dir: Path | None = None

    # Writable dir for caches and regenerated reference data; packaged data
    # is the fallback for reference CSVs.
    data_dir: Path = field(default_factory=user_data_dir)

    # Dashboard and widget output.
    output_dir: Path = field(default_factory=lambda: Path.cwd() / "output")

    # Analyze this savegame instead of the most recent one.
    savegame_override: Path | None = None

    # Hide undiscovered sectors/ships/stations and resource detail plots.
    spoilers_hide: bool = False

    # Rebuild caches from scratch (kept for compatibility; resources are
    # always recomputed).
    cache_force_refresh: bool = False

    # gzip the cache files.
    cache_compress: bool = True

    # Hours of history for the sunbursts and earnings tables.
    history_hours: float = 3.0

    # Hours of history for the map's police/pirate overlays.
    overlay_hours: float = 24.0

    # Open the dashboard in the default browser when done.
    open_browser: bool = True

    def find_savegame(self) -> Path:
        """Return the savegame to analyze (override, or newest by mtime)."""
        if self.savegame_override is not None:
            if not self.savegame_override.exists():
                raise FileNotFoundError(
                    f"savegame override does not exist: {self.savegame_override}"
                )
            return self.savegame_override

        candidates = [self.x4_user_dir] if self.x4_user_dir \
            else x4_user_dir_candidates()
        saves: list[Path] = []
        for root in candidates:
            if root is None or not root.is_dir():
                continue
            for d in root.rglob("save"):
                if not (d.is_dir()
                        and re.search(r"/[0-9]+/save$", d.as_posix())):
                    continue
                saves.extend(
                    f for f in d.iterdir()
                    if re.search(r"\.xml(\.gz)?$", f.name)
                )
            if saves:
                break
        if not saves:
            searched = "\n  ".join(str(c) for c in candidates if c)
            raise FileNotFoundError(
                "No savegames found. Searched:\n  " + searched
                + "\nUse --x4-user-dir to point at your Egosoft/X4 folder, "
                  "or --save for a specific file."
            )
        if any("temp" in f.name for f in saves):
            raise RuntimeError("Game is saving, try again in a minute.")
        return max(saves, key=lambda f: f.stat().st_mtime)

    def resolve_game_dir(self) -> Path:
        if self.game_dir is not None:
            if not self.game_dir.is_dir():
                raise FileNotFoundError(
                    f"game directory not found: {self.game_dir}")
            return self.game_dir
        found = find_game_dir()
        if found is None:
            raise FileNotFoundError(
                "Could not locate the X4 installation via Steam libraries. "
                "Use --game-dir to point at the 'X4 Foundations' folder."
            )
        return found
