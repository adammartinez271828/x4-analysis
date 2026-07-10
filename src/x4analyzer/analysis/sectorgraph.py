"""Sector connectivity graph (analytics-ideas.md infrastructure item 1).

Adjacency = gate/accelerator pairs from game data (gates.csv) plus
same-cluster sector pairs (multi-sector clusters are linked by internal
superhighways). Distances are gate hops via BFS.
"""

from __future__ import annotations

from collections import deque

from ..gamedata.refdata import RefData


def build_adjacency(ref: RefData) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {}

    def link(a: str, b: str) -> None:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)

    for r in ref.gates.itertuples(index=False):
        link(str(r.sector_a), str(r.sector_b))
    # sectors of one cluster are mutually reachable via superhighways
    for _cl, grp in ref.sectors.groupby("cluster"):
        macros = list(grp["macro"])
        for i, a in enumerate(macros):
            for b in macros[i + 1:]:
                link(a, b)
    return adj


def bfs_distances(adj: dict[str, set[str]], start: str,
                  max_dist: int | None = None) -> dict[str, int]:
    """Gate hops from `start` to every reachable sector (optionally capped)."""
    dist = {start: 0}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        d = dist[cur]
        if max_dist is not None and d >= max_dist:
            continue
        for nxt in adj.get(cur, ()):
            if nxt not in dist:
                dist[nxt] = d + 1
                queue.append(nxt)
    return dist
