"""Parsers for English log entry text (ported verbatim from the R script).

These depend on game localization and log wording; each returns an empty
DataFrame when nothing matches so downstream stages can skip gracefully.
Rows whose title matches a parser but whose text does not fit the expected
wording (version/localization drift) are skipped with a warning that dumps
sample strings — report those so the parser can be fixed.
The save text encodes newlines as the literal sequence `[\\012]`.
"""

from __future__ import annotations

import re

import pandas as pd

from ..cli import log

CODE_RE = r"[A-Z]{3}-[0-9]{3}"
# splits "...[\012]..." (with optional sentence-ending dot) like the R pattern
_NEWLINE_SPLIT = r"[.]?.\\012."


def _empty(cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=cols)


def _dump_unparsed(kind: str, bad: pd.Series) -> None:
    """Warn about strings that matched a parser's entry filter but not its
    expected wording, and show samples so they can be reported upstream."""
    if bad.empty:
        return
    log(f"WARNING: {len(bad)} {kind} did not match the expected wording "
        "and were skipped; sample:")
    for s in bad.astype(str).drop_duplicates().head(3):
        log("  " + repr(s[:220]))


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
    # resupply entries carried the details in the title in older game
    # versions but in the text in v9 — use whichever matches per row
    title_src = df["title"].fillna("")
    text_src = (df["text"] if "text" in df
                else pd.Series("", index=df.index)).fillna("")
    source = text_src.where(
        text_src.str.contains(split_text, regex=False), title_src)

    ok = source.str.contains(split_text, regex=False)
    _dump_unparsed(f"'{title}' log entries",
                   (title_src + " :: " + text_src)[~ok])
    df, source = df[ok], source[ok]
    if df.empty:
        return _empty(SALE_COLS)

    parts = source.str.split(re.escape(split_text), n=1, expand=True, regex=True)
    wares, parse2 = parts[0], parts[1]
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
    """v9 wording (harvested from both playthroughs' archived history,
    2026-07-24; 323/323 rows): title "<name> (<CODE>) was destroyed.",
    text "Location: <sector>" plus optional "[\\012]Commander: <name>
    (<CODE>)" and "[\\012]Destroyed by: <killer> (<CODE>)" lines (12/323
    rows carry no killer). The v5.10 one-line title form ("<object> in
    sector <s> was destroyed by <k>.") has zero archived instances and
    is no longer parsed."""
    cols = ["time", "object", "location", "killer"]
    df = df_log[
        (df_log["category"] == "upkeep")
        & df_log["title"].str.endswith(" was destroyed.", na=False)
    ]
    if df.empty:
        return _empty(cols)
    df = df.copy()
    text = (df["text"] if "text" in df
            else pd.Series("", index=df.index)).fillna("")
    ok = text.str.contains("Location: ", regex=False)
    _dump_unparsed("destroyed-object log entries",
                   (df["title"].fillna("") + " :: " + text)[~ok])
    df, text = df[ok], text[ok]
    if df.empty:
        return _empty(cols)
    # "[" opens the [\012] newline token, so a line's payload is [^[]*
    return pd.DataFrame({
        "time": df["time"].values,
        "object": df["title"].str.replace(
            r" was destroyed\.$", "", regex=True).values,
        "location": text.str.extract(
            r"Location: ([^[]+)", expand=False).str.strip().values,
        "killer": text.str.extract(
            r"Destroyed by: ([^[]+)", expand=False).str.strip().values,
    })


COMBAT_REWARD_COLS = ["time", "reward", "faction", "station", "sector",
                      "kind", "ship.name", "ship.code", "bounty_cr",
                      "reputation"]


def parse_combat_rewards(df_log: pd.DataFrame) -> pd.DataFrame:
    """Faction bounty payouts — the ONLY per-ship kill attribution the log
    carries (the game logs no general kill feed).

    v9 wording (harvested 2026-07-31 from the reference playthrough's
    merged history, 259/259 rows; category is absent): title
    `Combat Reward`, text lines joined by `[\\012]`:
    `Faction: <faction name>`, `Station: <station> (<CODE>)` — the paying
    station, sometimes with a trailing role suffix like
    `(Police Representative)` —, `Sector: <sector>`,
    `Credited To: Ships: <name> (<CODE>)[, <name> (<CODE>)…]` (253 rows)
    or `Credited To: Stations: <name> (<CODE>)` (6 rows), then the
    optional `Bounty: <N,NNN> Cr` (7 rows have none) and the optional
    `Reputation: +<N>` / `+<1` (19 rows have none).

    One row per CREDITED ship (a shared kill credits several), with
    `reward` the log row's ordinal so a consumer can count distinct
    rewards — `bounty_cr` repeats the whole payout on every credited row,
    so summing it across ships double-counts shared kills. `kind` is
    'ship' or 'station' after the `Credited To:` label. `bounty_cr` comes
    from the entry's `money` (cents, like every other money field), which
    carries the exact amount the rounded text does not. `reputation`
    records `+<1` — the game's "less than one rank point" — as **0.5**, a
    placeholder that must not be summed into a rank total.

    Credited names are matched as `<name> (<CODE>)` pairs; a ship whose
    NAME contains a comma loses the part before it (no such name is
    observed) rather than breaking the row.
    """
    df = df_log[df_log["title"].fillna("") == "Combat Reward"]
    if df.empty:
        return _empty(COMBAT_REWARD_COLS)
    df = df.copy()
    text = (df["text"] if "text" in df
            else pd.Series("", index=df.index)).fillna("")
    ok = text.str.contains("Credited To: ", regex=False)
    _dump_unparsed("combat-reward log entries", text[~ok])
    df, text = df[ok], text[ok]
    if df.empty:
        return _empty(COMBAT_REWARD_COLS)

    money = (pd.to_numeric(df["money"], errors="coerce") if "money" in df
             else pd.Series(float("nan"), index=df.index))
    rep_raw = text.str.extract(r"Reputation: \+([^[]+)", expand=False)
    rep = pd.to_numeric(rep_raw, errors="coerce").where(
        rep_raw.fillna("").str.strip() != "<1", 0.5)
    # "[" opens the [\012] newline token, so a line's payload is [^[]*
    base = pd.DataFrame({
        "time": df["time"].values,
        "reward": range(len(df)),
        "faction": text.str.extract(r"Faction: ([^[]+)", expand=False)
                       .str.strip().values,
        "station": text.str.extract(r"Station: ([^[]+)", expand=False)
                       .str.strip().values,
        "sector": text.str.extract(r"Sector: ([^[]+)", expand=False)
                      .str.strip().values,
        "credited": text.str.extract(r"Credited To: ([^[]+)", expand=False)
                        .str.strip().values,
        "bounty_cr": (money / 100.0).values,
        "reputation": rep.values,
    })
    rows = []
    for _i, r in base.iterrows():
        credited = str(r["credited"] or "")
        kind = ("station" if credited.startswith("Stations:")
                else "ship" if credited.startswith("Ships:") else "")
        who = credited.split(":", 1)[1] if ":" in credited else credited
        for name, code in re.findall(rf"([^,]*?)\s*\(({CODE_RE})\)", who):
            rows.append({
                "time": r["time"], "reward": r["reward"],
                "faction": r["faction"], "station": r["station"],
                "sector": r["sector"], "kind": kind,
                "ship.name": name.strip(), "ship.code": code,
                "bounty_cr": r["bounty_cr"], "reputation": r["reputation"],
            })
    if not rows:
        return _empty(COMBAT_REWARD_COLS)
    return pd.DataFrame(rows)[COMBAT_REWARD_COLS]


SHIP_CLAIM_COLS = ["time", "finder", "finder.code", "sector", "claimed",
                   "claimed.code"]


def parse_ship_claims(df_log: pd.DataFrame) -> pd.DataFrame:
    """Abandoned ships one of your ships spotted and was told to claim.

    v9 wording (harvested 2026-07-31; 39/39 rows in the reference
    playthrough, 21/21 in the second; category is absent): title
    `Found Abandoned Ship`, text
    `<finder> <CODE> in <sector>[\\012]Found abandoned ship <name>
    <CODE>.[\\012]Response: Claim if possible`.

    The entry records the SIGHTING and the standing response, not the
    outcome: whether the claim succeeded is not in the log (the save's
    `ships_claimed` counter is the only total).
    """
    df = df_log[df_log["title"].fillna("") == "Found Abandoned Ship"]
    if df.empty:
        return _empty(SHIP_CLAIM_COLS)
    df = df.copy()
    text = (df["text"] if "text" in df
            else pd.Series("", index=df.index)).fillna("")
    finder = text.str.extract(rf"^(.*?)\s+({CODE_RE})\s+in\s+([^[]+)")
    claimed = text.str.extract(
        rf"Found abandoned ship\s+(.*?)\s+({CODE_RE})")
    ok = finder[0].notna() & claimed[0].notna()
    _dump_unparsed("abandoned-ship log entries", text[~ok])
    df, finder, claimed = df[ok], finder[ok], claimed[ok]
    if df.empty:
        return _empty(SHIP_CLAIM_COLS)
    return pd.DataFrame({
        "time": df["time"].values,
        "finder": finder[0].str.strip().values,
        "finder.code": finder[1].values,
        "sector": finder[2].str.strip().values,
        "claimed": claimed[0].str.strip().values,
        "claimed.code": claimed[1].values,
    })


PILOT_BAIL_COLS = ["time", "ship", "sector"]


def parse_pilot_bails(df_log: pd.DataFrame) -> pd.DataFrame:
    """Enemy pilots forced out of their ship by your attack or boarding.

    v9 wording (harvested 2026-07-31; 45 rows in the reference
    playthrough, 64 in the second, all `category="upkeep"` — NOT
    `alerts`): the whole record is in the title,
    `Forced pilot to leave ship <ship> in sector <sector>.`, and the text
    is empty. No actor is recorded: the log does not say WHICH of your
    ships made the pilot bail, so these events cannot be attributed per
    ship.
    """
    title = df_log["title"].fillna("")
    df = df_log[title.str.startswith("Forced pilot to leave ship ")]
    if df.empty:
        return _empty(PILOT_BAIL_COLS)
    parts = df["title"].fillna("").str.extract(
        r"^Forced pilot to leave ship (.+) in sector (.+?)\.?$")
    ok = parts[0].notna()
    _dump_unparsed("forced-bail log entries", df.loc[~ok, "title"])
    df, parts = df[ok], parts[ok]
    if df.empty:
        return _empty(PILOT_BAIL_COLS)
    return pd.DataFrame({
        "time": df["time"].values,
        "ship": parts[0].str.strip().values,
        "sector": parts[1].str.strip().values,
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
        ok = df["title"].str.contains(r"Received surplus of .+ Credits from .+",
                                      regex=True)
        _dump_unparsed("surplus-transfer log entries", df.loc[~ok, "title"])
        df = df[ok]
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
        ok = df["title"].str.contains(r"Received surplus from .+ in .+",
                                      regex=True)
        _dump_unparsed("surplus-transfer log entries", df.loc[~ok, "title"])
        df = df[ok]
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
    ok = parts[[1, 3, 4]].notna().all(axis=1)
    _dump_unparsed("pirate-harassment log entries", df.loc[~ok, "text"])
    df, parts = df[ok], parts[ok]
    if df.empty:
        return _empty(cols)
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
    ok = parts[[1, 3, 5]].notna().all(axis=1)
    _dump_unparsed("police-interdiction log entries", df.loc[~ok, "text"])
    df, parts = df[ok], parts[ok]
    if df.empty:
        return _empty(cols)
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
