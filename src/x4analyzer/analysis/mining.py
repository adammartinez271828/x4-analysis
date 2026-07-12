"""Raw resource inflow per player station.

For each player station and each mineable ware (identified by the "minable"
tag in wares.csv — ore, silicon, ice, the gases, plus whatever mods add),
compare:

- observed inflow: units/h arriving at the station in the trade history.
  Assigned-miner deliveries appear as ordinary intra-empire trades with the
  station as buyer (verified against the reference save: seller = the miner,
  seller commander = the station), so own-miner deliveries and external
  purchases both count. Deliveries executed by the station's own fleet are
  additionally tracked separately ("own") to measure the fleet's real
  delivery rate.
- theoretical inflow: the mining subordinates assigned at save time, their
  hold volume (ships.csv `cargo`, resolved from the game's storage macros)
  times an assumed round-trip rate. The save has no historical assignments,
  so like the Trade History proxy logic this reflects the fleet NOW.
- consumption capacity: the station's module recipe inputs, reused from the
  Market tab's _station_rates result (passed in, never recomputed here).

Units: ship holds are measured in m³, not units — an 8,800 m³ hold carries
880 ore at 10 m³/unit — so every capacity-to-rate conversion goes through
the ware's volume. "measured" is the fleet's real full-load rate: own
deliveries in m³/h divided by the fleet's total hold m³ = full loads per
miner per hour. Theoretical inflow and "more miners" use that measured
rate directly; fleets without delivery history borrow the empire-wide
measured median, and only when nothing was measured anywhere does the
MINER_TRIPS_PER_H assumption apply.
"""

from __future__ import annotations

import math

import pandas as pd

# Fallback full-cargo deliveries per miner per hour, used only when no
# fleet has any measured delivery history: fly to the field, mine a full
# hold, return, dock. In-sector M miners over short hops in the reference
# save sustained 3-4 loads/h; long hauls run well below 1.
MINER_TRIPS_PER_H = 2.0

# Observed inflow is a rolling rate over this window, clamped down to the
# time since the first delivery of that ware to that station — a mining
# operation started mid-window would otherwise look diluted.
OBSERVED_WINDOW_H = 6.0

_COLS = ["id", "ware", "class", "observed", "own", "theoretical",
         "per_trip", "cons", "balance", "miners", "share", "class_cap",
         "class_cons", "avg_cap", "measured", "rate", "more_miners",
         "deliveries", "window_h"]
# own        units/h delivered by the station's currently assigned miners
# per_trip   units of this ware per fleet-wide trip cycle (every miner one
#            full load, the class pool split by `share`)
# share      the ware's slice of its class pool (volume-weighted Σ = 1)
# class_cap  total hold volume (m³) of the station's miners of the class
# class_cons Σ consumption of the class's wares at the station, in m³/h
# avg_cap    hold volume of "one more miner": the class fleet's mean,
#            falling back to typical_miner_capacity for stations with none
# measured   the fleet's real full-load rate (own m³/h ÷ class_cap);
#            0 when the fleet has no delivery history
# rate       loads/miner/h actually used: measured, else the empire-wide
#            measured median, else MINER_TRIPS_PER_H
# theoretical per_trip x rate (units/h)
# more_miners additional miners of the class needed so class_cap x rate
#            covers class_cons; shared across the class's wares
# deliveries own-fleet delivery count inside the window (per ware)
# window_h   the rolling window actually used for this ware


def _miner_class(macro: str, cargo_tags: str) -> str:
    """solid vs liquid hold, from the ship's cargo tags (game data), the
    macro name as fallback (modded ships missing from ships.csv), solid as
    the default (the more common miner type)."""
    for cls in ("liquid", "solid"):
        if cls in cargo_tags.split() or cls in macro:
            return cls
    return "solid"


def typical_miner_capacity(frames, ref) -> dict[str, float]:
    """Median miner hold volume (m³) per class — the player's own miner
    models when they have any, any game miner otherwise. Sizes "one more
    miner" for a station with no assigned miners at all."""
    rs = ref.ships
    caps = pd.to_numeric(rs.get("cargo", pd.Series(dtype=float)),
                         errors="coerce")
    tags = rs.get("cargo_tags", pd.Series(dtype=str)).fillna("").astype(str)
    purpose = rs.get("purpose", pd.Series(dtype=str)).fillna("")
    own = set(frames.ships["macro"]) if not frames.ships.empty else set()
    out: dict[str, float] = {}
    for cls in ("solid", "liquid"):
        pool = [(m, float(c)) for m, p, c, t
                in zip(rs["macro"], purpose, caps, tags)
                if (p == "mine" or "miner" in str(m)) and pd.notna(c)
                and c > 0 and _miner_class(str(m), t) == cls]
        mine = [c for m, c in pool if m in own]
        vals = mine or [c for _m, c in pool]
        out[cls] = float(pd.Series(vals).median()) if vals else 0.0
    return out


def raw_inflow(frames, ref, rates: pd.DataFrame) -> pd.DataFrame:
    """Per (player station, mineable ware): observed/theoretical inflow,
    consumption capacity (units/h) and the assigned fleet's measured
    delivery rate. `rates` is _station_rates(...) output (id, faction,
    ware, prod, cons)."""
    empty = pd.DataFrame(columns=_COLS)
    stations = frames.stations
    if stations.empty:
        return empty

    wares = ref.wares
    minable = wares[wares["tags"].fillna("").str.contains("minable")]
    if minable.empty:
        return empty
    transport = dict(zip(minable["id"], minable["transport"].fillna("")))
    vol = {w: (float(v) if pd.notna(v) and float(v) > 0 else 1.0)
           for w, v in zip(minable["id"],
                           pd.to_numeric(minable.get("volume",
                                                     pd.Series(dtype=float)),
                                         errors="coerce"))}
    # tradelog carries display names; map back to ware ids (a ware missing
    # from the localization falls through as its raw id)
    name_to_id = {ref.ware_name.get(w, w): w for w in minable["id"]}
    for w in minable["id"]:
        name_to_id.setdefault(w, w)

    tl = frames.tradelog
    raw = (tl[tl["commodity"].isin(name_to_id)].copy()
           if not tl.empty else pd.DataFrame(
               columns=["time", "commodity", "amount", "buyer.code",
                        "seller.code", "seller.proxy.code"]))
    if not raw.empty:
        raw["ware"] = raw["commodity"].map(name_to_id)
        raw["amount"] = pd.to_numeric(raw["amount"],
                                      errors="coerce").fillna(0.0)
        # the executing ship: proxy code when the trade was redirected to a
        # commander (same "Executed by" convention as the Trade History tab)
        raw["exec.code"] = (raw["seller.proxy.code"]
                            .fillna(raw["seller.code"]))
        raw["m3"] = raw["amount"] * raw["ware"].map(vol).fillna(1.0)
    max_load_m3 = (raw.groupby("exec.code")["m3"].max()
                   if not raw.empty else pd.Series(dtype=float))

    ships = frames.ships
    rs = ref.ships
    purpose = dict(zip(rs["macro"], rs.get("purpose", pd.Series(dtype=str))
                       .fillna("")))
    cap_map = dict(zip(rs["macro"],
                       pd.to_numeric(rs.get("cargo",
                                            pd.Series(dtype=float)),
                                     errors="coerce")))
    tags_map = dict(zip(rs["macro"], rs.get("cargo_tags",
                                            pd.Series(dtype=str))
                        .fillna("").astype(str)))
    ship_info = (ships.set_index("id")[["macro", "code"]]
                 if not ships.empty
                 else pd.DataFrame(columns=["macro", "code"]))
    sc = frames.station_cargo
    cargo_m3 = (sc.assign(m3=sc["amount"] * sc["ware"].map(vol).fillna(1.0))
                .groupby("id")["m3"].sum()
                if not sc.empty else pd.Series(dtype=float))
    typical = typical_miner_capacity(frames, ref)

    wings = frames.wings
    time_now = frames.time_now
    rates = rates[rates["ware"].isin(transport)] if not rates.empty else rates

    rows: list[dict] = []
    for _, st in stations.iterrows():
        sid, code = st["id"], str(st["code"])

        # assigned mining subordinates, bucketed by hold class
        class_cap: dict[str, float] = {}
        class_n: dict[str, int] = {}
        fleet_codes: set[str] = set()
        followers = wings[wings["leader"] == sid]["follower"] \
            if not wings.empty else ()
        for fid in followers:
            if fid not in ship_info.index:
                continue
            macro = str(ship_info.at[fid, "macro"])
            if purpose.get(macro, "") != "mine" and "miner" not in macro:
                continue
            cls = _miner_class(macro, tags_map.get(macro, ""))
            cap = cap_map.get(macro)
            if pd.isna(cap) or not cap:
                # modded ship without game data: its biggest observed
                # delivery, else whatever it carries right now (both m³)
                cap = float(max_load_m3.get(str(ship_info.at[fid, "code"]),
                                            0.0)) \
                    or float(cargo_m3.get(fid, 0.0))
            class_cap[cls] = class_cap.get(cls, 0.0) + float(cap)
            class_n[cls] = class_n.get(cls, 0) + 1
            fleet_codes.add(str(ship_info.at[fid, "code"]))

        deliveries = raw[raw["buyer.code"] == code] if not raw.empty else raw
        observed: dict[str, float] = {}
        own: dict[str, float] = {}
        n_deliv: dict[str, int] = {}
        window: dict[str, float] = {}
        for ware, grp in (deliveries.groupby("ware")
                          if not deliveries.empty else ()):
            window_h = max(0.5, min(
                OBSERVED_WINDOW_H,
                (time_now - float(grp["time"].min())) / 3600.0))
            recent = grp[grp["time"] >= time_now - window_h * 3600.0]
            mine_own = recent[recent["exec.code"].isin(fleet_codes)]
            observed[ware] = float(recent["amount"].sum()) / window_h
            own[ware] = float(mine_own["amount"].sum()) / window_h
            n_deliv[ware] = int(len(mine_own))
            window[ware] = window_h

        mine = rates[(rates["id"] == sid) & (rates["cons"] > 0)] \
            if not rates.empty else rates
        cons = (dict(zip(mine["ware"], mine["cons"]))
                if not mine.empty else {})

        ware_set = sorted(set(observed) | set(cons))
        for cls in sorted(set(class_cap) | {transport.get(w, "")
                                            for w in ware_set}):
            cls_wares = [w for w in ware_set if transport.get(w) == cls]
            if not cls_wares:
                continue
            cap_total = class_cap.get(cls, 0.0)
            n = class_n.get(cls, 0)
            # a class's miners are a shared pool: split their haul across
            # the class's wares by consumption VOLUME (evenly when the
            # station consumes none of them)
            cons_m3 = sum(cons.get(w, 0.0) * vol.get(w, 1.0)
                          for w in cls_wares)
            own_m3 = sum(own.get(w, 0.0) * vol.get(w, 1.0)
                         for w in cls_wares)
            measured = own_m3 / cap_total if cap_total > 0 else 0.0
            avg = cap_total / n if n and cap_total > 0 \
                else typical.get(cls, 0.0)
            for w in cls_wares:
                share = (cons.get(w, 0.0) * vol.get(w, 1.0) / cons_m3
                         if cons_m3 > 0 else 1.0 / len(cls_wares))
                per_trip = cap_total * share / vol.get(w, 1.0)
                obs = observed.get(w, 0.0)
                need = cons.get(w, 0.0)
                rows.append({
                    "id": sid, "ware": w, "class": cls,
                    "observed": obs, "own": own.get(w, 0.0),
                    "per_trip": per_trip,
                    "cons": need, "balance": obs - need,
                    "miners": n, "share": share,
                    "class_cap": cap_total, "class_cons": cons_m3,
                    "avg_cap": avg, "measured": measured,
                    "deliveries": n_deliv.get(w, 0),
                    "window_h": window.get(w, 0.0),
                })

    if not rows:
        return empty
    df = pd.DataFrame(rows)
    # fleets without delivery history borrow the empire-wide measured
    # median; the hardcoded assumption is a last resort
    med = df.loc[df["measured"] > 0, "measured"].median()
    fallback = float(med) if pd.notna(med) else MINER_TRIPS_PER_H
    df["rate"] = df["measured"].where(df["measured"] > 0, fallback)
    df["theoretical"] = df["per_trip"] * df["rate"]

    def _more(r) -> float:
        gap = r["class_cons"] - r["class_cap"] * r["rate"]
        if gap <= 0:
            return 0
        per = r["avg_cap"] * r["rate"]
        return math.ceil(gap / per) if per > 0 else math.nan

    df["more_miners"] = df.apply(_more, axis=1)
    return df[_COLS].sort_values(["balance", "id", "ware"],
                                 ignore_index=True)
