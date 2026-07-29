"""Structural invariants for the experiment register.

`docs/experiments/README.md` is the status of every falsifiable claim this
project has made. It is only worth trusting if its ids are stable, its
citations resolve and its summary table agrees with its own entries — all of
which are mechanical, and none of which a human reliably maintains by hand over
112 entries (the table drifted the first time it was edited).

What this file CANNOT check: whether a status is *true*, or whether the
reference/ and models/ docs actually agree with the register. That is the
cross-document half of the sync rule in CLAUDE.md and stays a human judgement.
A green run here means the register is internally coherent, not that the
documentation is correct.
"""
from __future__ import annotations

import collections
import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
REGISTER = DOCS / "experiments" / "README.md"

STATUSES = ("CONFIRMED", "FALSIFIED", "PENDING", "SUPERSEDED")

# Closed label sets. A new entry that invents a synonym fails here on purpose:
# the register degrades into prose if the same role appears under many labels.
EVIDENCE = ("*Killed by:*", "*Falsified by:*", "*Ruled out:*",
            "*Contradicted by:*", "*Killed by (")
REPLACEMENT = ("*Replaced by:*", "*Superseded by:*")
SETTLES = ("*Settles it:*", "*Needs:*", "*Blocked on:*", "*Settled by:*")

# Ratchet, not a hard rule: PENDING entries that do not yet say what would
# settle them. LOWER THIS as they are filled in; it must never rise. A new
# PENDING entry has no excuse — the maintenance rule requires the field.
PENDING_WITHOUT_SETTLES = 8

Entry = collections.namedtuple("Entry", "id status claim body section")


def _entries() -> list[Entry]:
    src = REGISTER.read_text()
    section = "(preamble)"
    out: list[Entry] = []
    heads = {m.start(): m.group(1)
             for m in re.finditer(r"^## (.+)$", src, re.M)}
    for m in re.finditer(r"^\*\*(E-\d{3})\s*·\s*(\w+)\*\*\s*—\s*(.+?)$",
                         src, re.M):
        for pos, name in heads.items():
            if pos < m.start():
                section = name
        end = src.find("\n\n", m.end())
        out.append(Entry(m.group(1), m.group(2), m.group(3),
                         src[m.end():end if end > 0 else len(src)], section))
    return out


@pytest.fixture(scope="module")
def entries() -> list[Entry]:
    got = _entries()
    assert len(got) > 50, f"only parsed {len(got)} entries — format drifted?"
    return got


def test_ids_are_unique(entries):
    dupes = [i for i, n in collections.Counter(e.id for e in entries).items()
             if n > 1]
    assert not dupes, f"ids are stable and never reused; duplicated: {dupes}"


def test_status_vocabulary_is_closed(entries):
    bad = [(e.id, e.status) for e in entries if e.status not in STATUSES]
    assert not bad, f"status must be one of {STATUSES}; got {bad}"


def test_every_entry_cites_a_source(entries):
    bad = [e.id for e in entries if "*Source:*" not in e.body]
    assert not bad, f"every entry needs a *Source:* citation; missing: {bad}"


def test_every_cited_file_exists():
    src = REGISTER.read_text()
    links = sorted(set(re.findall(r"\]\((\.\./[^)#]+)", src)))
    missing = [ln for ln in links
               if not (REGISTER.parent / ln).resolve().exists()]
    assert not missing, f"dead citation targets: {missing}"


def test_falsified_entries_keep_their_evidence(entries):
    """A killed hypothesis without its killing evidence gets re-tested. This
    repo has re-tested dead hypotheses more than once."""
    bad = [e.id for e in entries if e.status == "FALSIFIED"
           and not any(lbl in e.body for lbl in EVIDENCE)]
    assert not bad, (f"FALSIFIED entries must record what killed them, using "
                     f"one of {EVIDENCE}; missing on {bad}")


def test_superseded_entries_name_an_existing_replacement(entries):
    ids = {e.id for e in entries}
    missing, dangling = [], []
    for e in entries:
        if e.status != "SUPERSEDED":
            continue
        m = re.search(r"\*(?:Replaced|Superseded) by:\*\s*(E-\d{3})", e.body)
        if not m:
            missing.append(e.id)
        elif m.group(1) not in ids:
            dangling.append((e.id, m.group(1)))
    assert not missing, (f"SUPERSEDED entries must name their replacement "
                         f"using one of {REPLACEMENT}; missing on {missing}")
    assert not dangling, f"replacement id does not exist: {dangling}"


def test_pending_entries_say_what_would_settle_them(entries):
    bad = sorted(e.id for e in entries if e.status == "PENDING"
                 and not any(lbl in e.body for lbl in SETTLES))
    assert len(bad) <= PENDING_WITHOUT_SETTLES, (
        f"{len(bad)} PENDING entries do not say what would settle them "
        f"(ratchet is {PENDING_WITHOUT_SETTLES}): {bad}")


def test_summary_table_matches_the_entries(entries):
    """The hand-maintained table drifts. Recompute it and print the correct
    rows on failure so the fix is copy-paste."""
    src = REGISTER.read_text()
    per_section: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    for e in entries:
        per_section[e.section][e.status] += 1

    rows = re.findall(
        r"^\|\s*(?:\*\*)?([A-Za-z][^|]*?)(?:\*\*)?\s*\|"
        + r"\s*(?:\*\*)?(\d+)(?:\*\*)?\s*\|" * 5 + r"\s*$",
        src, re.M)
    stated = {name.split("(")[0].strip(): tuple(int(x) for x in nums)
              for name, *nums in rows if not name.lower().startswith("total")}
    total_row = [r for r in rows if r[0].lower().startswith("total")]

    problems = []
    for name, counts in sorted(per_section.items()):
        want = tuple(counts[s] for s in STATUSES) + (sum(counts.values()),)
        got = stated.get(name)
        if got != want:
            problems.append(f"  {name}: table says {got}, entries say {want}")
    grand = collections.Counter()
    for c in per_section.values():
        grand.update(c)
    want_total = tuple(grand[s] for s in STATUSES) + (sum(grand.values()),)
    if total_row:
        got_total = tuple(int(x) for x in total_row[0][1:])
        if got_total != want_total:
            problems.append(f"  TOTAL: table says {got_total}, "
                            f"entries say {want_total}")

    assert not problems, (
        "summary table is out of date (columns: "
        + ", ".join(STATUSES) + ", total)\n" + "\n".join(problems))
