"""Raw resource inflow per player station.

For each player station and each mineable ware (identified by the "minable"
tag in wares.csv — ore, silicon, ice, the gases, plus whatever mods add),
compare:

- observed inflow: units/h arriving at the station in the trade history.
  Assigned-miner deliveries appear as ordinary intra-empire trades with the
  station as buyer (verified against the reference save: seller = the miner,
  seller commander = the station), so own-miner deliveries and external
  purchases both count.
- theoretical inflow: the mining subordinates assigned at save time, their
  cargo capacity (ships.csv, resolved from the game's storage macros) times
  an assumed round-trip rate. The save has no historical assignments, so
  like the Trade History proxy logic this reflects the fleet NOW.
- consumption capacity: the station's module recipe inputs, reused from the
  Market tab's _station_rates result (passed in, never recomputed here).

A station whose observed inflow is below its consumption capacity is
under-supplied; the theoretical column says whether more miners are needed
(theoretical < consumption too) or the assigned ones underperform.
"""

from __future__ import annotations

import pandas as pd

# Assumed full-cargo deliveries per miner per hour for the theoretical
# inflow: one round trip (fly to the field, mine a full hold, return, dock)
# per hour. In-sector M miners in the reference save completed roughly half
# that, so read the column as an optimistic ceiling, not a promise.
MINER_TRIPS_PER_H = 1.0

# Observed inflow is a rolling rate over this window, clamped down to the
# time since the first delivery of that ware to that station — a mining
# operation started mid-window would otherwise look diluted.
OBSERVED_WINDOW_H = 6.0

_COLS = ["id", "ware", "class", "observed", "theoretical", "cons",
         "balance", "miners"]


def _miner_class(macro: str, cargo_tags: str) -> str:
    """solid vs liquid hold, from the ship's cargo tags (game data), the
    macro name as fallback (modded ships missing from ships.csv), solid as
    the default (the more common miner type)."""
    for cls in ("liquid", "solid"):
        if cls in cargo_tags.split() or cls in macro:
            return cls
    return "solid"


def raw_inflow(frames, ref, rates: pd.DataFrame) -> pd.DataFrame:
    """Per (player station, mineable ware): observed/theoretical inflow and
    consumption capacity, all in units/h. `rates` is _station_rates(...)
    output (id, faction, ware, prod, cons)."""
    empty = pd.DataFrame(columns=_COLS)
    stations = frames.stations
    if stations.empty:
        return empty

    wares = ref.wares
    minable = wares[wares["tags"].fillna("").str.contains("minable")]
    if minable.empty:
        return empty
    transport = dict(zip(minable["id"], minable["transport"].fillna("")))
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
    max_load = (raw.groupby("exec.code")["amount"].max()
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
    cargo_by_id = (frames.station_cargo.groupby("id")["amount"].sum()
                   if not frames.station_cargo.empty
                   else pd.Series(dtype=float))

    wings = frames.wings
    time_now = frames.time_now
    rates = rates[rates["ware"].isin(transport)] if not rates.empty else rates

    rows: list[dict] = []
    for _, st in stations.iterrows():
        sid, code = st["id"], str(st["code"])

        deliveries = raw[raw["buyer.code"] == code] if not raw.empty else raw
        observed: dict[str, float] = {}
        for ware, grp in (deliveries.groupby("ware")
                          if not deliveries.empty else ()):
            window_h = max(0.5, min(
                OBSERVED_WINDOW_H,
                (time_now - float(grp["time"].min())) / 3600.0))
            recent = grp[grp["time"] >= time_now - window_h * 3600.0]
            observed[ware] = float(recent["amount"].sum()) / window_h

        mine = rates[(rates["id"] == sid) & (rates["cons"] > 0)] \
            if not rates.empty else rates
        cons = (dict(zip(mine["ware"], mine["cons"]))
                if not mine.empty else {})

        # assigned mining subordinates, bucketed by hold class
        class_cap: dict[str, float] = {}
        class_n: dict[str, int] = {}
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
                # delivery, else whatever it carries right now
                cap = float(max_load.get(str(ship_info.at[fid, "code"]),
                                         0.0)) \
                    or float(cargo_by_id.get(fid, 0.0))
            class_cap[cls] = class_cap.get(cls, 0.0) + float(cap)
            class_n[cls] = class_n.get(cls, 0) + 1

        ware_set = sorted(set(observed) | set(cons))
        for cls in sorted(set(class_cap) | {transport.get(w, "")
                                            for w in ware_set}):
            cls_wares = [w for w in ware_set if transport.get(w) == cls]
            if not cls_wares:
                continue
            # a class's miners are a shared pool: split their theoretical
            # rate across the class's wares in proportion to consumption
            # (evenly when the station consumes none of them)
            total = class_cap.get(cls, 0.0) * MINER_TRIPS_PER_H
            cons_sum = sum(cons.get(w, 0.0) for w in cls_wares)
            for w in cls_wares:
                share = (cons.get(w, 0.0) / cons_sum if cons_sum > 0
                         else 1.0 / len(cls_wares))
                obs = observed.get(w, 0.0)
                need = cons.get(w, 0.0)
                rows.append({
                    "id": sid, "ware": w, "class": cls,
                    "observed": obs, "theoretical": total * share,
                    "cons": need, "balance": obs - need,
                    "miners": class_n.get(cls, 0),
                })

    if not rows:
        return empty
    return pd.DataFrame(rows).sort_values(
        ["balance", "id", "ware"], ignore_index=True)
