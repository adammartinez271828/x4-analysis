"""Reader for X4's .cat/.dat archive pairs.

A .cat file is a text index, one entry per line:

    <path with possible spaces> <size> <mtime> <md5>

The paired .dat holds the file payloads concatenated in index order, so each
entry's offset is the running sum of the sizes before it.

Files are looked up in reverse load order: extensions override the base game,
higher-numbered cats override lower-numbered ones, and loose files on disk
override everything (X4's own precedence rules).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CatEntry:
    path: str          # virtual path inside the archive, e.g. "libraries/wares.xml"
    size: int
    offset: int        # byte offset in the .dat file
    dat: Path
    source: str        # "" for base game, extension folder name otherwise


def _parse_cat(cat_path: Path, source: str) -> list[CatEntry]:
    dat_path = cat_path.with_suffix(".dat")
    entries: list[CatEntry] = []
    offset = 0
    with open(cat_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            # path may contain spaces: size/mtime/md5 are the last three fields
            parts = line.rsplit(" ", 3)
            if len(parts) != 4:
                continue
            path, size_s, _mtime, _md5 = parts
            size = int(size_s)
            entries.append(CatEntry(path, size, offset, dat_path, source))
            offset += size
    return entries


def _numbered_cats(directory: Path, pattern: str) -> list[Path]:
    """Non-signature cats in a directory, in load order (01, 02, ...)."""
    return sorted(
        p for p in directory.glob(pattern)
        if re.fullmatch(r"(ext_)?\d+\.cat", p.name) and p.with_suffix(".dat").exists()
    )


class GameFiles:
    """Merged view of the game's virtual file system (base + extensions)."""

    def __init__(self, game_dir: Path, extensions: list[str] | None = None):
        """`extensions`: folder names under extensions/ to load, in load order.
        None loads only official DLC (ego_dlc_*)."""
        self.game_dir = game_dir
        if not game_dir.is_dir():
            raise FileNotFoundError(f"game directory not found: {game_dir}")

        ext_root = game_dir / "extensions"
        if extensions is None:
            extensions = sorted(
                d.name for d in ext_root.iterdir()
                if d.is_dir() and d.name.startswith("ego_dlc_")
            ) if ext_root.is_dir() else []
        self.extensions = extensions

        # later additions win: base cats in order, then each extension's cats
        self._index: dict[str, CatEntry] = {}
        for cat in _numbered_cats(game_dir, "*.cat"):
            for e in _parse_cat(cat, ""):
                self._index[e.path] = e
        for ext in extensions:
            ext_dir = ext_root / ext
            if not ext_dir.is_dir():
                continue
            for cat in _numbered_cats(ext_dir, "ext_*.cat"):
                # extension-internal paths are relative to the extension root;
                # expose them both bare and under extensions/<name>/
                for e in _parse_cat(cat, ext):
                    self._index[f"extensions/{ext}/{e.path}"] = e

    def __contains__(self, path: str) -> bool:
        return (self.game_dir / path).is_file() or path in self._index

    def entry(self, path: str) -> CatEntry | None:
        return self._index.get(path)

    def read_bytes(self, path: str) -> bytes:
        loose = self.game_dir / path
        if loose.is_file():
            return loose.read_bytes()
        e = self._index.get(path)
        if e is None:
            raise FileNotFoundError(f"not in catalogs or loose files: {path}")
        with open(e.dat, "rb") as fh:
            fh.seek(e.offset)
            data = fh.read(e.size)
        if len(data) != e.size:
            raise IOError(f"short read for {path} from {e.dat}")
        return data

    def glob(self, regex: str) -> list[str]:
        """All indexed virtual paths matching a regex (loose files not included)."""
        rx = re.compile(regex)
        return sorted(p for p in self._index if rx.match(p))

    def source_of(self, path: str) -> str:
        e = self._index.get(path)
        return e.source if e else ""
