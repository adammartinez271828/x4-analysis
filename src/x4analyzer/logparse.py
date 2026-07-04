"""Parsers for English log entry text (ported verbatim from the R script).

These depend on game localization and log wording; each returns an empty
DataFrame when nothing matches so downstream stages can skip gracefully.
The save text encodes newlines as the literal sequence `[\\012]`.
"""

from __future__ import annotations

import re

import pandas as pd

CODE_RE = r"[A-Z]{3}-[0-9]{3}"
# splits "...[\012]..." (with optional sentence-ending dot) like the R pattern
_NEWLINE_SPLIT = r"[.]?.\\012."


def _empty(cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=cols)


SALE_COLS = ["time", "money", "seller.name", "seller.code", "amount",
             "commodity", "buyer.faction", "buyer.name", "buyer.code"]


def parse_ship_services(df_log: pd.DataFrame, title: str, split_text: str,
                        commodity: str) -> pd.DataFrame:
    """Ship construction / repair / resupply sales from upkeep log entries.

    Text shape: "<FAC> <ship> (<CODE>) finished <verb> at station: <station>
    (<CODE>). They have paid <N> Cr."
    """
    df = df_log[(df_log["category"] == "upkeep") & (df_log["title"] == title)]
    if df.empty:
        return _empty(SALE_COLS)
    df = df.copy()
    # resupply entries carry the details in the title in some versions; the
    # R script parsed title for resupply and text otherwise
    source = df["title"] if commodity == "Ship resupply" else df["text"]
    source = source.fillna("")

    parts = source.str.split(re.escape(split_text), n=1, expand=True, regex=True)
    wares, parse2 = parts[0], parts[1] if 1 in parts else ""
    seller = parse2.str.split(r"\. They have paid", n=1, expand=True, regex=True)[0]

    out = pd.DataFrame({
        "time": df["time"].values,
        "money": (df["money"].fillna(0) / 100.0).floordiv(1).values,
        "seller.name": seller.str.split(rf" [(]{CODE_RE}[)]", n=1, regex=True)
                             .str[0].values,
        "seller.code": seller.str.extract(rf"({CODE_RE})", expand=False).values,
        "amount": 1,
        "commodity": commodity,
    })
    buyer_parts = wares.str.split(" ", n=1, expand=True)
    buyer_name = buyer_parts[1] if 1 in buyer_parts else pd.Series("", index=wares.index)
    out["buyer.faction"] = buyer_parts[0].values
    out["buyer.code"] = buyer_name.str.extract(rf"({CODE_RE})", expand=False).values
    out["buyer.name"] = buyer_name.str.split(
        rf" [(]*{CODE_RE}[)]*", n=1, regex=True).str[0].values
    return out[SALE_COLS]


def parse_destroyed(df_log: pd.DataFrame) -> pd.DataFrame:
    cols = ["time", "object", "location", "killer"]
    df = df_log[
        (df_log["category"] == "upkeep")
        & df_log["title"].str.contains("was destroyed by", na=False)
    ]
    if df.empty:
        return _empty(cols)
    df = df.copy()
    p1 = df["title"].str.split(" in sector ", n=1, expand=True)
    p2 = p1[1].str.split(" was destroyed by ", n=1, expand=True)
    p3 = p2[1].str.split(".", n=1, expand=True)
    return pd.DataFrame({
        "time": df["time"].values, "object": p1[0].values,
        "location": p2[0].values, "killer": p3[0].values,
    })


def parse_transfers(df_log: pd.DataFrame, df_npcs: pd.DataFrame | None,
                    df_stations: pd.DataFrame | None) -> pd.DataFrame:
    """Station manager surplus transfers; two wordings (changed ~v4 -> v5)."""
    cols = ["time", "money", "station.id", "station.code", "station.name"]
    frames = []

    df = df_log[
        (df_log["category"] == "upkeep")
        & df_log["title"].str.contains("Received surplus of", na=False)
    ]
    if not df.empty and df_npcs is not None and df_stations is not None:
        parts = df["title"].str.split("( of )|( Credits from )", n=2, regex=True,
                                      expand=True)
        # str.split with capture groups interleaves them; keep text fields
        text_cols = [c for c in parts.columns if parts[c].notna().any()]
        money = parts[text_cols[1]].str.replace(",", "", regex=False)
        manager = parts[text_cols[-1]].str.rstrip(".")
        t = pd.DataFrame({
            "time": df["time"].values,
            "money": pd.to_numeric(money, errors="coerce").values,
            "manager.name": manager.values,
        })
        managers = df_npcs[df_npcs["role"] == "manager (station)"][["name", "id"]]
        t = t.merge(managers, left_on="manager.name", right_on="name", how="left")
        t = t.merge(
            df_stations[["manager.id", "code", "name"]].rename(
                columns={"code": "station.code", "name": "station.name"}),
            left_on="id", right_on="manager.id", how="left",
        )
        t["station.id"] = t["manager.id"]
        frames.append(t[cols])

    df = df_log[
        (df_log["category"] == "upkeep")
        & df_log["title"].str.contains("Received surplus from", na=False)
    ]
    if not df.empty and df_stations is not None:
        station = df["title"].str.split("( surplus from )|( in )", n=2, regex=True,
                                        expand=True)
        text_cols = [c for c in station.columns if station[c].notna().any()]
        t = pd.DataFrame({
            "time": df["time"].values,
            "money": (pd.to_numeric(df["money"], errors="coerce") / 100).values,
            "station.name": station[text_cols[1]].values,
        })
        t = t.merge(
            df_stations[["id", "code", "name"]].rename(
                columns={"id": "station.id", "code": "station.code"}),
            left_on="station.name", right_on="name", how="left",
        )
        frames.append(t[cols])

    if not frames:
        return _empty(cols)
    return pd.concat(frames, ignore_index=True)


def parse_pirates(df_log: pd.DataFrame, df_sectors: pd.DataFrame) -> pd.DataFrame:
    """Text: "<ship> <CODE> in <sector>[\\012]Accosted by <faction> pirate ship
    [\\012]<FAC> <pirate> <CODE>.[\\012]Response: <response>" """
    cols = ["time", "ship.name", "ship.code", "sector.macro", "sector.name",
            "pirate.name", "pirate.code", "pirate.faction", "response"]
    df = df_log[df_log["title"].str.contains("Pirate Harassment", na=False,
                                             regex=False)]
    if df.empty:
        return _empty(cols)
    parts = df["text"].fillna("").str.split(
        rf" in |{_NEWLINE_SPLIT}", regex=True, expand=True
    ).reindex(columns=range(6))
    out = pd.DataFrame({
        "time": df["time"].values,
        "ship": parts[0].values, "sector.name": parts[1].values,
        "pirate": parts[3].values, "response": parts[4].values,
    })
    out = out.merge(
        df_sectors[["name", "sector.macro"]].drop_duplicates("name"),
        left_on="sector.name", right_on="name", how="left",
    )
    out["ship.code"] = out["ship"].str.extract(rf"({CODE_RE})$", expand=False)
    out["ship.name"] = out["ship"].str.replace(rf" {CODE_RE}$", "", regex=True)
    out["pirate.code"] = out["pirate"].str.extract(rf"({CODE_RE})$", expand=False)
    out["pirate.faction"] = out["pirate"].str.extract(r"^([A-Z]{3})", expand=False)
    out["pirate.name"] = (out["pirate"].str.replace(rf" {CODE_RE}$", "", regex=True)
                          .str.replace(r"^[A-Z]{3} ", "", regex=True))
    out["response"] = out["response"].str.replace(r"^Response: ", "", regex=True)
    return out[cols]


def parse_police(df_log: pd.DataFrame, df_sectors: pd.DataFrame,
                 name_to_short: dict) -> pd.DataFrame:
    """Text: "<ship> <CODE> in <sector>[\\012]Ordered by <faction> police to stop
    ...[\\012]Response: <response>" """
    cols = ["time", "ship.name", "ship.code", "sector.macro", "sector.name",
            "police.faction", "response"]
    df = df_log[df_log["title"].str.contains("Police Interdiction", na=False,
                                             regex=False)]
    if df.empty:
        return _empty(cols)
    parts = df["text"].fillna("").str.split(
        rf" in | by | police to stop |{_NEWLINE_SPLIT}", regex=True, expand=True
    ).reindex(columns=range(7))
    out = pd.DataFrame({
        "time": df["time"].values,
        "ship": parts[0].values, "sector.name": parts[1].values,
        "faction.name": parts[3].values, "response": parts[5].values,
    })
    out = out.merge(
        df_sectors[["name", "sector.macro"]].drop_duplicates("name"),
        left_on="sector.name", right_on="name", how="left",
    )
    out["police.faction"] = out["faction.name"].map(name_to_short)
    out["ship.code"] = out["ship"].str.extract(rf"({CODE_RE})$", expand=False)
    out["ship.name"] = out["ship"].str.replace(rf" {CODE_RE}$", "", regex=True)
    out["response"] = out["response"].str.replace(r"^Response: ", "", regex=True)
    return out[cols]
