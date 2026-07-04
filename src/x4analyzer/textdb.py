"""X4 localization text database.

Game data refers to display strings as `{page,id}` references into the
language t-files (t/0001-l044.xml = English). Values may contain nested
references and `(comments)` that the game strips at render time; literal
parentheses are escaped as `\\(` `\\)`.
"""

from __future__ import annotations

import csv
import gzip
import re
from pathlib import Path

from lxml import etree

_REF = re.compile(r"\{\s*(\d+)\s*,\s*(\d+)\s*\}")
_COMMENT = re.compile(r"(?<!\\)\((?:[^()\\]|\\.)*?(?<!\\)\)")


class TextDB:
    def __init__(self) -> None:
        self._pages: dict[int, dict[int, str]] = {}

    def load_xml(self, data: bytes) -> None:
        """Merge a t-file (plain `<language>` or extension `<diff>` form)."""
        root = etree.fromstring(data, etree.XMLParser(recover=True, huge_tree=True))
        if root is None:
            return
        for page in root.iter("page"):
            try:
                page_id = int(page.get("id", ""))
            except ValueError:
                continue
            entries = self._pages.setdefault(page_id, {})
            for t in page.iter("t"):
                try:
                    entries[int(t.get("id", ""))] = t.text or ""
                except ValueError:
                    continue

    def raw(self, page: int, tid: int) -> str | None:
        return self._pages.get(page, {}).get(tid)

    def resolve(self, text: str, _depth: int = 0) -> str:
        """Resolve `{page,id}` refs, strip comments, unescape parentheses."""
        if _depth > 8:
            return text

        def sub(m: re.Match) -> str:
            raw = self.raw(int(m.group(1)), int(m.group(2)))
            if raw is None:
                return m.group(0)  # keep unresolvable refs visible
            return self.resolve(raw, _depth + 1)

        text = _REF.sub(sub, text)
        if _depth == 0:
            while True:
                stripped = _COMMENT.sub("", text)
                if stripped == text:
                    break
                text = stripped
            text = text.replace(r"\(", "(").replace(r"\)", ")")
        return text

    # -- persistence (so analysis runs don't need the game install) ---------

    def dump_csv(self, path: Path) -> int:
        rows = sorted(
            (page, tid) for page, entries in self._pages.items() for tid in entries
        )
        with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["page", "id", "text"])
            for page, tid in rows:
                w.writerow([page, tid, self._pages[page][tid]])
        return len(rows)

    @classmethod
    def from_csv(cls, path: Path) -> "TextDB":
        db = cls()
        with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                db._pages.setdefault(int(row["page"]), {})[int(row["id"])] = row["text"]
        return db
