"""Run configuration, platform-aware path discovery, and data locations.

Reference game data (ships/sectors/wares/...) ships inside the package;
`extract-gamedata` writes regenerated copies into a per-user data directory
which, when present, overrides the packaged files. The analysis database always
lives in the user data directory (the package may be installed read-only,
e.g. via uvx).
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


GAME_DIR_ENV = "X4_GAME_DIR"

GAME_DIR_NAME = "X4 Foundations"

# Non-default Steam library roots ("path" in the modern libraryfolders.vdf)
# and the legacy pre-2021 form, where each numbered key IS the path
# (`"1"  "D:\\SteamLibrary"`) with no "path" key at all.
_VDF_PATH_RE = re.compile(r'"path"\s+"([^"]+)"')
_VDF_LEGACY_RE = re.compile(r'"\d+"\s+"([^"]{2,})"')


def _steam_roots() -> list[Path]:
    """Places a Steam installation root may live, most likely first."""
    home = Path.home()
    if sys.platform == "win32":
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        return [Path(pf86) / "Steam", Path(pf) / "Steam", Path(r"C:\Steam")]
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "Steam"]
    xdg = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return [
        home / ".local" / "share" / "Steam",
        home / ".steam" / "steam",
        home / ".steam" / "root",
        xdg / "Steam",
        # Flatpak and Snap keep their own private HOME.
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".local"
        / "share" / "Steam",
        home / "snap" / "steam" / "common" / ".local" / "share" / "Steam",
    ]


def _steam_libraries(root: Path) -> list[Path]:
    """Library roots listed by a Steam root's libraryfolders.vdf.

    Includes the Steam root itself (it is always library 0, and older
    installs have no vdf at all). Tolerates a missing or malformed file:
    anything unparseable simply contributes no extra libraries.
    """
    libs = [root]
    for name in ("steamapps", "SteamApps", "steam/steamapps"):
        vdf = root / name / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = _VDF_PATH_RE.findall(text) or _VDF_LEGACY_RE.findall(text)
        for raw in found:
            # Windows paths are escaped in the vdf ("D:\\SteamLibrary").
            libs.append(Path(raw.replace("\\\\", "\\")))
    return libs


def _game_dir_in(library: Path) -> Path | None:
    """The X4 install inside one Steam library root, if present."""
    for apps in ("steamapps", "SteamApps"):
        common = library / apps / "common"
        candidate = common / GAME_DIR_NAME
        if candidate.is_dir():
            return candidate
        # Case-insensitive fallback (cf. the capital-S EgoSoft trap).
        try:
            for d in common.iterdir():
                if d.name.lower() == GAME_DIR_NAME.lower() and d.is_dir():
                    return d
        except OSError:
            continue
    return None


def find_game_dir() -> Path | None:
    """Locate the X4 installation: $X4_GAME_DIR, else Steam libraries.

    Returns None when nothing is found — Steam being absent entirely is
    the normal case for a wheel/uvx install, where `extract-gamedata` is
    simply not usable.
    """
    env = os.environ.get(GAME_DIR_ENV)
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p

    seen: set[Path] = set()
    libraries: list[Path] = []
    for root in _steam_roots():
        for lib in _steam_libraries(root):
            try:
                key = lib.resolve()
            except OSError:
                key = lib
            if key in seen:
                continue
            seen.add(key)
            libraries.append(lib)

    for lib in libraries:
        found = _game_dir_in(lib)
        if found is not None:
            return found
    return None


@dataclass
class Config:
    # X4 user folder (the one containing <player-id>/save/). None = search
    # the platform-standard locations.
    x4_user_dir: Path | None = None

    # X4 installation (for `extract-gamedata`). Left unset it is filled in
    # by detection (`$X4_GAME_DIR`, else the Steam libraries) at construction
    # time, and stays None only when no install could be found.
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

    # Hours of history for the sunbursts and earnings tables.
    history_hours: float = 3.0

    # Hours of history for the map's police/pirate overlays.
    overlay_hours: float = 24.0

    # Open the dashboard in the default browser when done.
    open_browser: bool = True

    def __post_init__(self) -> None:
        # Resolve the game install eagerly so plain attribute access
        # (`Config().game_dir`) yields a usable path instead of a None that
        # only surfaces later as an AttributeError. Detection is a handful
        # of stats plus one small vdf read, and must never be fatal.
        if self.game_dir is None:
            try:
                self.game_dir = find_game_dir()
            except Exception:  # pragma: no cover - detection is best-effort
                self.game_dir = None

    def find_all_savegames(self) -> list:
        """Every discoverable savegame file (first user dir with any)."""
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
        return saves

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
        saves = self.find_all_savegames()
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
            searched = "\n  ".join(str(r) for r in _steam_roots())
            raise FileNotFoundError(
                "Could not locate the X4 installation. Looked for a Steam "
                f"library holding 'steamapps/common/{GAME_DIR_NAME}' under:"
                f"\n  {searched}\n"
                f"Set {GAME_DIR_ENV}=/path/to/'{GAME_DIR_NAME}' or pass "
                "--game-dir to point at the installation directory."
            )
        return found
