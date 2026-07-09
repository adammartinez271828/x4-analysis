"""Persistent caches keyed by game GUID.

The savegame's log and economylog are rolling windows — the game drops old
entries — so each run merges the fresh window into a cache that preserves
history (same semantics as the R script):

- log cache: for each category present in the new data, cached entries at or
  after that category's oldest new timestamp are replaced by the new entries.
- tradelog cache: cached entries newer than the oldest new timestamp are
  replaced (the new window is authoritative from that point on).

Files are tab-separated CSV, gzipped when cache_compress is on, and live in
the data directory next to the reference CSVs.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import Config


def _cache_path(cfg: Config, kind: str, guid: str) -> Path:
    base = cfg.data_dir / f"cache_{kind}_{guid}.csv"
    return base.with_suffix(".csv.gz") if cfg.cache_compress else base


def _read(path: Path) -> pd.DataFrame | None:
    # accept both compressed and uncompressed leftovers of either setting
    for p in (path, path.with_suffix(".gz") if path.suffix == ".csv"
              else path.with_suffix("")):
        if p.exists():
            return pd.read_csv(p, sep="\t", dtype=str)
    return None


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, sep="\t", index=False)
    # remove a stale variant with the other compression setting
    other = path.with_suffix(".gz") if path.suffix == ".csv" else path.with_suffix("")
    if other != path:
        other.unlink(missing_ok=True)


def merge_log_cache(cfg: Config, guid: str, df_log: pd.DataFrame) -> pd.DataFrame:
    path = _cache_path(cfg, "log", guid)
    cached = _read(path)
    if cached is not None and not df_log.empty:
        cached = cached.reindex(columns=df_log.columns)
        cached["time"] = pd.to_numeric(cached["time"], errors="coerce")
        cached["money"] = pd.to_numeric(cached["money"], errors="coerce")
        cached["category"] = cached["category"].fillna("")
        # keep only entries the R filter would keep (in case rules changed)
        cached = cached[
            (cached["category"] == "")
            | ((cached["category"] == "upkeep") & (cached["title"] != "Trade Completed"))
        ]
        for category, mintime in df_log.groupby("category")["time"].min().items():
            drop = (cached["category"] == category) & (cached["time"] >= mintime)
            cached = cached[~drop]
        df_log = (
            pd.concat([cached, df_log], ignore_index=True)
            .drop_duplicates()
            .sort_values("time", kind="stable", ignore_index=True)
        )
    _write(df_log, path)
    return df_log


def merge_tradelog_cache(cfg: Config, guid: str, df_trade: pd.DataFrame) -> pd.DataFrame:
    path = _cache_path(cfg, "tradelog", guid)
    cached = _read(path)
    if cached is not None and not df_trade.empty:
        cached = cached.reindex(columns=df_trade.columns)
        for col in ("time", "price"):
            cached[col] = pd.to_numeric(cached[col], errors="coerce")
        for col in ("amount", "money"):
            cached[col] = pd.to_numeric(cached[col], errors="coerce").astype("Int64")
        mintime = df_trade["time"].min()
        cached = cached[cached["time"] <= mintime]
        # dedupe on save-stable identity only: component ids ([0x..]) are
        # runtime ids reassigned between saves, so the same trade parsed
        # from two saves differs in *.id — full-row dedup would keep both
        # (seen in the wild as repeated transactions in Trade History)
        stable = ["time", "commodity", "price", "amount", "money",
                  "seller.faction", "seller.name", "seller.code",
                  "buyer.faction", "buyer.name", "buyer.code"]
        df_trade = (
            pd.concat([cached, df_trade], ignore_index=True)
            .drop_duplicates(subset=stable, keep="last")
            .sort_values("time", kind="stable", ignore_index=True)
        )
    _write(df_trade, path)
    return df_trade
