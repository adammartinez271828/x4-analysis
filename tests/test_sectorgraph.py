from types import SimpleNamespace

import pandas as pd

from x4analyzer.gamedata.extract import _SECTOR_IN_PATH
from x4analyzer.analysis.sectorgraph import build_adjacency, bfs_distances


def _ref(gates, sectors):
    return SimpleNamespace(
        gates=pd.DataFrame(gates, columns=["sector_a", "sector_b", "source"]),
        sectors=pd.DataFrame(sectors, columns=["cluster", "macro"]),
    )


def test_sector_path_regex():
    m = _SECTOR_IN_PATH.search(
        "../Cluster_01_connection/Cluster_01_Sector001_connection/"
        "Zone003_Cluster_01_Sector001_connection/connection_G001")
    assert m.group(1) == "Cluster_01_Sector001"


def test_adjacency_gates_and_cluster():
    ref = _ref(
        [["s_a1", "s_b1", ""]],
        # cluster A has two sectors -> internal superhighway link
        [["cl_a", "s_a1"], ["cl_a", "s_a2"], ["cl_b", "s_b1"]],
    )
    adj = build_adjacency(ref)
    assert adj["s_a1"] == {"s_b1", "s_a2"}
    assert adj["s_b1"] == {"s_a1"}


def test_bfs_distances_and_cap():
    ref = _ref(
        [["s1", "s2", ""], ["s2", "s3", ""], ["s3", "s4", ""]],
        [["c1", "s1"], ["c2", "s2"], ["c3", "s3"], ["c4", "s4"]],
    )
    adj = build_adjacency(ref)
    d = bfs_distances(adj, "s1")
    assert d == {"s1": 0, "s2": 1, "s3": 2, "s4": 3}
    assert bfs_distances(adj, "s1", max_dist=2) == {"s1": 0, "s2": 1, "s3": 2}
