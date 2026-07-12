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
  times their measured delivery rate. The save has no historical
  assignments, so like the Trade History proxy logic this reflects the
  fleet NOW.
- consumption capacity: the station's module recipe inputs, reused from the
  Market tab's _station_rates result (passed in, never recomputed here).

Miners bucket into POOLS per (hold class, ship size): one solid pool feeds
all mineral wares and one liquid pool all gases, but M and L miners cycle
at very different rates (an L fills a far bigger hold and travels/docks
slower), so each size keeps its own measured rate and the shortfall is
quoted in alternatives — "+32 M or +12 L miners".

Units: ship holds are measured in m³, not units — an 8,800 m³ hold carries
880 ore at 10 m³/unit — so every capacity-to-rate conversion goes through
the ware's volume. "measured" is a pool's real full-load rate: its own
deliveries in m³/h divided by the pool's total hold m³ = full loads per
miner per hour. Pools without delivery history borrow the empire-wide
measured median for their size, and only when nothing was measured
anywhere does the per-size assumption apply.
"""

from __future__ import annotations

import math
import re

import pandas as pd

# Fallback full-cargo deliveries per miner per hour by ship size, used
# only when no pool of that size has any measured delivery history:
# bigger miners spend longer filling their hold and travel/dock slower,
# so they complete fewer round trips. In-sector M miners over short hops
# in the reference save sustained 3-4 loads/h; long hauls run well below 1.
ASSUMED_TRIPS_PER_H = {"S": 3.0, "M": 2.0, "L": 1.0, "XL": 0.8}

# Observed inflow is a rolling rate over this window, clamped down to the
# time since the first delivery of that ware to that station — a mining
# operation started mid-window would otherwise look diluted.
OBSERVED_WINDOW_H = 6.0

# ship sizes offered as "you could assign N of these instead" even when
# the station has none (the assignable mining workhorses)
OPTION_SIZES = ("M", "L")

_SIZE_ORDER = {"S": 0, "M": 1, "L": 2, "XL": 3}

_COLS = ["id", "ware", "class", "observed", "own", "theoretical", "cons",
         "balance", "share", "class_cons", "class_obs", "deliveries",
         "window_h"]
# own        units/h delivered by the station's currently assigned miners
# share      the ware's slice of its class pools (volume-weighted Σ = 1)
# class_cons Σ consumption of the class's wares at the station, in m³/h
# class_obs  Σ observed inflow of the class's wares (all sources incl.
#            external purchases), in m³/h
# theoretical Σ over the class's pools of hold m³ x measured rate,
#            allocated by share and converted to units/h
# deliveries own-fleet delivery count inside the window (per ware)
# window_h   the rolling window actually used for this ware

_PCOLS = ["id", "class", "size", "miners", "cap", "avg_cap", "measured",
          "rate", "rate_src", "class_cons", "class_obs", "more_miners"]
# one row per (station, hold class, ship size) — assigned pools plus the
# OPTION_SIZES alternatives a player could assign instead:
# cap        total hold volume (m³) of the pool's assigned miners
# avg_cap    hold volume of "one more miner" of this size: the pool's
#            mean, falling back to typical_miner_capacity
# measured   the pool's real full-load rate (own m³/h ÷ cap); 0 = none
# rate       loads/miner/h actually used, by fallback chain:
# rate_src   "measured" (this pool) / "empire" (median of same-size pools
#            elsewhere) / "assumed" (ASSUMED_TRIPS_PER_H)
# more_miners miners of THIS size that would close the class shortfall
#            (class_cons - class_obs; external purchases count as supply)


def _miner_class(macro: str, cargo_tags: str) -> str:
    """solid vs liquid hold, from the ship's cargo tags (game data), the
    macro name as fallback (modded ships missing from ships.csv), solid as
    the default (the more common miner type)."""
    for cls in ("liquid", "solid"):
        if cls in cargo_tags.split() or cls in macro:
            return cls
    return "solid"


_MACRO_SIZE = re.compile(r"_(xs|s|m|l|xl)_")


def _miner_size(macro: str, size_map: dict) -> str:
    """Ship size (S/M/L/XL) from game data, the macro name as fallback."""
    size = str(size_map.get(macro, "") or "").upper()
    if size in _SIZE_ORDER:
        return size
    m = _MACRO_SIZE.search(macro)
    return m.group(1).upper() if m else "M"


def typical_miner_capacity(frames, ref) -> dict[tuple[str, str], float]:
    """(hold class, size) -> median miner hold volume (m³) — the player's
    own miner models when they have any, any game miner otherwise. Sizes
    "one more miner" for pools with none assigned."""
    rs = ref.ships
    caps = pd.to_numeric(rs.get("cargo", pd.Series(dtype=float)),
                         errors="coerce")
    tags = rs.get("cargo_tags", pd.Series(dtype=str)).fillna("").astype(str)
    purpose = rs.get("purpose", pd.Series(dtype=str)).fillna("")
    size_map = dict(zip(rs["macro"], rs.get("class", pd.Series(dtype=str))
                        .fillna("")))
    own = set(frames.ships["macro"]) if not frames.ships.empty else set()
    miners = [(str(m), _miner_class(str(m), t),
               _miner_size(str(m), size_map), float(c))
              for m, p, c, t in zip(rs["macro"], purpose, caps, tags)
              if (p == "mine" or "miner" in str(m))
              and pd.notna(c) and c > 0]
    out: dict[tuple[str, str], float] = {}
    for key in {(cls, size) for _m, cls, size, _c in miners}:
        pool = [(m, c) for m, cls, size, c in miners if (cls, size) == key]
        mine = [c for m, c in pool if m in own]
        vals = mine or [c for _m, c in pool]
        out[key] = float(pd.Series(vals).median())
    return out


def raw_inflow(frames, ref,
               rates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (per-ware frame, per-pool frame) — see _COLS/_PCOLS.
    `rates` is _station_rates(...) output (id, faction, ware, prod, cons).
    """
    empty = (pd.DataFrame(columns=_COLS), pd.DataFrame(columns=_PCOLS))
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
    size_map = dict(zip(rs["macro"], rs.get("class", pd.Series(dtype=str))
                        .fillna("")))
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

    wrows: list[dict] = []
    prows: list[dict] = []
    for _, st in stations.iterrows():
        sid, code = st["id"], str(st["code"])

        # assigned mining subordinates, bucketed into (class, size) pools
        pool_cap: dict[tuple, float] = {}
        pool_n: dict[tuple, int] = {}
        pool_own: dict[tuple, float] = {}   # m³/h delivered by the pool
        code_pool: dict[str, tuple] = {}    # miner code -> its pool
        followers = wings[wings["leader"] == sid]["follower"] \
            if not wings.empty else ()
        for fid in followers:
            if fid not in ship_info.index:
                continue
            macro = str(ship_info.at[fid, "macro"])
            if purpose.get(macro, "") != "mine" and "miner" not in macro:
                continue
            key = (_miner_class(macro, tags_map.get(macro, "")),
                   _miner_size(macro, size_map))
            cap = cap_map.get(macro)
            if pd.isna(cap) or not cap:
                # modded ship without game data: its biggest observed
                # delivery, else whatever it carries right now (both m³)
                cap = float(max_load_m3.get(str(ship_info.at[fid, "code"]),
                                            0.0)) \
                    or float(cargo_m3.get(fid, 0.0))
            pool_cap[key] = pool_cap.get(key, 0.0) + float(cap)
            pool_n[key] = pool_n.get(key, 0) + 1
            code_pool[str(ship_info.at[fid, "code"])] = key

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
            mine_own = recent[recent["exec.code"].isin(code_pool)]
            observed[ware] = float(recent["amount"].sum()) / window_h
            own[ware] = float(mine_own["amount"].sum()) / window_h
            n_deliv[ware] = int(len(mine_own))
            window[ware] = window_h
            for ecode, m3 in mine_own.groupby("exec.code")["m3"].sum() \
                    .items():
                key = code_pool[str(ecode)]
                pool_own[key] = pool_own.get(key, 0.0) \
                    + float(m3) / window_h

        mine = rates[(rates["id"] == sid) & (rates["cons"] > 0)] \
            if not rates.empty else rates
        cons = (dict(zip(mine["ware"], mine["cons"]))
                if not mine.empty else {})

        ware_set = sorted(set(observed) | set(cons))
        fleet_classes = {cls for cls, _size in pool_cap}
        for cls in sorted(fleet_classes | {transport.get(w, "")
                                           for w in ware_set}):
            cls_wares = [w for w in ware_set if transport.get(w) == cls]
            if not cls_wares:
                continue
            cons_m3 = sum(cons.get(w, 0.0) * vol.get(w, 1.0)
                          for w in cls_wares)
            obs_m3 = sum(observed.get(w, 0.0) * vol.get(w, 1.0)
                         for w in cls_wares)

            sizes = {s for c, s in pool_cap if c == cls} | set(OPTION_SIZES)
            for size in sorted(sizes, key=lambda s: _SIZE_ORDER.get(s, 9)):
                key = (cls, size)
                cap, n = pool_cap.get(key, 0.0), pool_n.get(key, 0)
                avg = cap / n if n and cap > 0 else typical.get(key, 0.0)
                if n == 0 and avg <= 0:
                    continue   # nothing assigned and no known model to size
                prows.append({
                    "id": sid, "class": cls, "size": size, "miners": n,
                    "cap": cap, "avg_cap": avg,
                    "measured": (pool_own.get(key, 0.0) / cap
                                 if cap > 0 else 0.0),
                    "class_cons": cons_m3, "class_obs": obs_m3,
                })

            for w in cls_wares:
                # the class's pools are shared: split their haul across
                # the class's wares by consumption VOLUME (evenly when the
                # station consumes none of them)
                share = (cons.get(w, 0.0) * vol.get(w, 1.0) / cons_m3
                         if cons_m3 > 0 else 1.0 / len(cls_wares))
                obs = observed.get(w, 0.0)
                need = cons.get(w, 0.0)
                wrows.append({
                    "id": sid, "ware": w, "class": cls,
                    "observed": obs, "own": own.get(w, 0.0),
                    "cons": need, "balance": obs - need,
                    "share": share, "_vol": vol.get(w, 1.0),
                    "class_cons": cons_m3, "class_obs": obs_m3,
                    "deliveries": n_deliv.get(w, 0),
                    "window_h": window.get(w, 0.0),
                })

    if not wrows:
        return empty
    pools = pd.DataFrame(prows)
    # rate fallback chain: this pool's measured rate, else the empire-wide
    # measured median for the same ship size, else the per-size assumption
    med = pools[pools["measured"] > 0].groupby("size")["measured"].median()
    rate, src = [], []
    for _, p in pools.iterrows():
        if p["measured"] > 0:
            rate.append(float(p["measured"]))
            src.append("measured")
        elif pd.notna(med.get(p["size"])):
            rate.append(float(med.get(p["size"])))
            src.append("empire")
        else:
            rate.append(ASSUMED_TRIPS_PER_H.get(p["size"], 1.0))
            src.append("assumed")
    pools["rate"] = rate
    pools["rate_src"] = src

    def _more(p) -> float:
        # the shortfall the player actually experiences: consumption not
        # covered by current inflow (external purchases count as supply),
        # closed by miners of THIS size hauling at the pool's rate
        gap = p["class_cons"] - p["class_obs"]
        if gap <= 0:
            return 0
        per = p["avg_cap"] * p["rate"]
        return math.ceil(gap / per) if per > 0 else math.nan

    pools["more_miners"] = pools.apply(_more, axis=1)

    df = pd.DataFrame(wrows)
    # theoretical inflow: every pool of the ware's class hauling at its
    # own rate, allocated by share and converted back to units
    supply = (pools["cap"] * pools["rate"]).groupby(
        [pools["id"], pools["class"]]).sum()
    key = list(zip(df["id"], df["class"]))
    df["theoretical"] = (supply.reindex(key).fillna(0.0).to_numpy()
                         * df["share"] / df["_vol"])
    df = df.drop(columns="_vol")
    return (df[_COLS].sort_values(["balance", "id", "ware"],
                                  ignore_index=True),
            pools[_PCOLS].reset_index(drop=True))
