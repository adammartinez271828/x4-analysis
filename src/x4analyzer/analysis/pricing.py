"""Station ware-price model — the reverse-engineered price book, in code.

Implementation of [docs/models/station-pricing-model.md] as refined by the
2026-07-30 Phase-2 reports (`docs/reports/`: `supplies-midpoint`,
`value-cap-solve`, `offset-family`, `cap-scope-scavenger`, `build-demand`).
Research-grade: it classifies every trade offer in an analysis-DB snapshot
into its **price book**, predicts the price where a confirmed law exists, and
scores the result under the project's mandatory bin-median discipline. No
widget, no pipeline wiring — nothing else in the package imports this.

The main sequence, in one line — `avg` / `min` / `max` are the ware's band:

    price = avg + s·(max − avg)   if s ≥ 0,   avg + s·(avg − min)   if s < 0
    s     = cos(π · clamp((net/T + a) / 1.095, 0, 1))
    net   = stock + undelivered inbound − committed outbound

`T` is the price target: the storage allocation on the consumer side, and on
the supplier side the allocation **capped at a fixed credit value**,
`T = min(allocation, V / price_avg)`. `a` is an additive offset on the fill
axis, selected by the population the offer belongs to.

**Populations that are NOT the main sequence** (each measured, not assumed):

| book | rule | what is predicted |
|---|---|---|
| `player` | owner is the player, or a manual `price_setting`/`ware_limit` | nothing — off-model by design |
| `lockavgprice` | the (station, ware) is on the station's own whitelist | sell = avg exactly, buy = avg − 1 |
| `supplies` | the `supplies` offer flag | the band midpoint, `s = +0.5` exactly |
| `shady` | the `shady` offer flag | two tiers, 1.042 × max or 2.750 × avg |
| `buildstorage` | the offer's host is a build storage | descriptive flat-then-fall only |
| `yard` | the host carries a built `buildmodule*` | the closed form, with the yard's own consumer offset |
| `main` | everything else | the closed form above |

**The yard book is not a separate family** (NEW, unregistered — this module's
own result, `score_yard_forms()`). E-028 carried a clamped power
`band = clamp(1 − fill^2.62)` on the offer-derived proxy after its build-demand
*mechanism* was falsified. Scored like for like — one fitted parameter each,
whole yard buy population, bin medians on a rule-independent x — the ordinary
cosine on the storage allocation with the yard station constant −0.2026 beats
it by 27× on bin-median RMSE (0.0054 against 0.1483), 40× on MAD (0.0020
against 0.0777) and 16× on the tail (1.5 % against 23.9 %). It also *explains*
the ~0.17 band floor at full that the build-demand report recorded as real and
unexplained: at fill 1 the shifted cosine reaches only `s = cos(0.728π)`, i.e.
band position 0.18, where a power curve must go to zero. Two conditions matter
and both are structural, not tuning: a yard's rations take the ordinary +0.006
role offset (they are 121 of 675 buys and carry the power form's worst
residuals), and its 22 sell offers take the ordinary supplier offset +0.053
(MAD 0.015). What is left is one cohort constant, −0.2026, whose cause is the
same open question as every other station's input constant.

Honest edges, carried deliberately:

- **`V` is not settled.** E-116 is PENDING between 5.00 M and 5.05 M Cr: `V`
  and the supplier offset `a` trade off along an exact ridge (≈ +0.0009 in `a`
  per +1 % in `V`), and 13 epochs of corpus trajectories do not break it
  (`docs/reports/value-cap-solve-2026-07-30.md`). `(V, a) = (5.00 M, 0.048)`
  and `(5.05 M, 0.053)` are indistinguishable from save data. The defaults
  here are `V = 5,000,000` with `a = 0.053` — the model doc's pair, not the
  jointly optimal one; both are parameters.
- **The buy-only production-input offset is a per-station constant whose cause
  is unknown.** −0.039 is only the population default; the real number ranges
  over roughly 0 to −0.8 and is shared by all of a station's inputs
  (E-011's "per-module reserve" reading is FALSIFIED). Fitted per-station
  overrides are available and are used by default for the self-consumption
  exemption, where the hypothesis names that constant explicitly.
- **Build storages hold no allocation at all** (0 of 1,771), so no fill
  coordinate exists and there is no confident closed form. They are classified
  and scored against the *descriptive* flat-then-fall shape E-118 measured;
  the prediction is labelled `descriptive`, never `law`.
- **Shady tier is mutable station state.** It correlates with zero workforce
  but is not derivable from the save, so the tier is read off the observed
  price — a classification, not a prediction — and the workforce correlate is
  reported by `shady_tier_census()`.
"""

from __future__ import annotations

import math
import sqlite3

import pandas as pd

# ---------------------------------------------------------------------------
# constants — every one of these is a measured quantity, sourced in the docs
# ---------------------------------------------------------------------------

#: span of the cosine in fill units. Global; fitted on 5,428 buy offers over
#: 40 bins and independently on 2,369 ration offers at 1.085.
SPAN = 1.095

#: the supplier-side price target's credit cap. **E-116 is PENDING**: the
#: binding population optimises at 5.05–5.10 M with `a` held at 0.053, while
#: the two in-game-anchored solar plants return 5,001,8xx Cr at `a = 0.048`.
#: `V` and `a` are not separable from save data, so this is 5.00 M by
#: convention, matching the model doc.
VALUE_CAP_CR = 5_000_000.0

#: offsets on the fill axis, selected by population (model doc § The offset a)
A_SUPPLIER = 0.053     # the station posts a sell offer for the ware
A_RATION = 0.006       # buy-only ration           (MAD 0.0015, the tightest)
A_INPUT = -0.039       # buy-only production input (a PER-STATION constant)
A_YARD = -0.202        # host carries a built buildmodule (median −0.2019)

#: yard clamped-power exponent, refitted on snapshot 71 (k = 2.62 against the
#: registered 2.60) on the `stock + inbound + open buy` proxy denominator.
YARD_K = 2.62

#: the `supplies` self-supply book is a fixed point on the same cosine
SUPPLIES_S = 0.5

#: `lockavgprice`: sell at the band average exactly, buy one credit under
LOCKAVG_BUY_DISCOUNT_CR = 1.0

#: the two `shady` tiers, disjoint by station
SHADY_CONTINUUM = 1.042    # × band max
SHADY_FIXED = 2.750        # × band average

#: E-118's descriptive flat-then-fall for build storages: band position holds
#: at the ceiling to a knee, then falls over `width`. NOT a law — the free fit
#: reads knee 0.41 / 0.50 / 0.57 on three different denominators.
BUILD_STORAGE_KNEE = 0.50
BUILD_STORAGE_WIDTH = 0.65

#: which yard description the predictor uses. "cosine" WINS by 23× on
#: bin-median RMSE — see `score_yard_forms()`; "power" is kept so the losing
#: candidate stays scoreable rather than becoming folklore.
YARD_FORM = "cosine"       # "cosine" | "power"

BOOKS = ("player", "lockavgprice", "supplies", "shady", "buildstorage",
         "yard", "main")

_WORKUNIT = "workunit_busy"
_BUILDMODULE = "buildmodule"
_NAN = float("nan")


# ---------------------------------------------------------------------------
# the closed form — scalar, dependency-free, directly testable
# ---------------------------------------------------------------------------

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def s_of_u(u: float, span: float = SPAN) -> float:
    """Normalised price coordinate from the fill coordinate: +1 = band max,
    0 = band average, −1 = band min."""
    return math.cos(math.pi * clamp(u / span))


def u_of_s(s: float, span: float = SPAN) -> float:
    """Inverse of `s_of_u`. Flat at the clamps — an offer with |s| ≥ 1 carries
    no information about `u` and must be excluded from any offset fit."""
    return span * math.acos(clamp(s, -1.0, 1.0)) / math.pi


def price_of_s(s: float, price_min: float, price_avg: float,
               price_max: float) -> float:
    """Interpolate from the band average out to whichever edge `s` points at.
    Two branches because 40 of 1,891 wares have asymmetric bands (ore is
    −14 %/+16 %) and kink at avg on the band-position axis."""
    return (price_avg + s * (price_max - price_avg) if s >= 0
            else price_avg + s * (price_avg - price_min))


def s_of_price(price: float, price_min: float, price_avg: float,
               price_max: float) -> float:
    """Observed price → `s`, on the half-spread of the observed side. A
    degenerate band (min == avg == max) yields 0 rather than dividing by 0."""
    half = (price_max - price_avg) if price >= price_avg \
        else (price_avg - price_min)
    return 0.0 if not half else (price - price_avg) / half


def capped_target(allocation: float, price_avg: float,
                  value_cap: float = VALUE_CAP_CR) -> float:
    """The supplier-side price target: whichever runs out first, the storage
    allocation or `value_cap` credits of the ware (E-113/E-114)."""
    if not price_avg or price_avg <= 0 or not _finite(price_avg):
        return allocation
    return min(allocation, value_cap / price_avg)


def main_sequence_price(net: float, target: float, price_min: float,
                        price_avg: float, price_max: float,
                        a: float, span: float = SPAN) -> float:
    """The main-sequence closed form. `target` is `T`, the price target."""
    if not target or target <= 0 or not _finite(target):
        return _NAN
    return price_of_s(s_of_u(net / target + a, span),
                      price_min, price_avg, price_max)


def supplies_price(price_avg: float, price_max: float) -> float:
    """The `supplies` self-supply book: the band midpoint, `s = +0.5` exactly.
    15,345 offers over 13 saves, 19 factions, maximum deviation 0.00 Cr."""
    return price_avg + SUPPLIES_S * (price_max - price_avg)


def lockavgprice_price(price_avg: float, side: str) -> float:
    """The `lockavgprice` whitelist: pegged at the band average regardless of
    stock, the buy side one credit under (E-025). Membership is per (station,
    ware) — `station_trade_setting`, setting `lockavgprice` — not a property
    of the faction or the station design."""
    return price_avg if side == "sell" else price_avg - LOCKAVG_BUY_DISCOUNT_CR


def shady_price(tier: str, price_avg: float, price_max: float) -> float:
    """The black-market book. Two tiers, disjoint by station, no fill
    dependence either way; which tier a station is on is mutable state."""
    return (SHADY_FIXED * price_avg if tier == "fixed"
            else SHADY_CONTINUUM * price_max)


def shady_tier_of_price(price: float, price_avg: float,
                        price_max: float) -> str:
    """Read a station's shady tier off the observation — the tier is not
    derivable from the save. Correlated with zero workforce (see
    `shady_tier_census`), but that is a correlate, not a rule."""
    return ("fixed" if abs(price - SHADY_FIXED * price_avg)
            <= abs(price - SHADY_CONTINUUM * price_max) else "continuum")


def build_storage_band(fill: float, knee: float = BUILD_STORAGE_KNEE,
                       width: float = BUILD_STORAGE_WIDTH) -> float:
    """DESCRIPTIVE ONLY. Band position (0 = min, 1 = max) of a build-storage
    offer: flat at the ceiling to a knee, then falling. Build storages hold no
    allocation, so the denominator is the self-referential `stock + inbound +
    open buy amount` and no closed form is claimed. The cosine family is
    rejected here on two independent denominators (bin RMSE 0.31 / 0.24
    against flat-then-line's 0.073 / 0.028)."""
    if fill <= knee:
        return 1.0
    return clamp(1.0 - (fill - knee) / width) if width > 0 else 0.0


def yard_band(fill: float, k: float = YARD_K) -> float:
    """The yard/wharf/dock book as a clamped power on the proxy denominator,
    `band = clamp(1 − fill^k)`. E-028's *mechanism* — outstanding build demand
    as the denominator — is falsified (the BOM is a median 0 % of the derived
    allocation and swings at CV 0.51 while the allocation holds at CV 0.011);
    the shape it carried survives."""
    return clamp(1.0 - max(fill, 0.0) ** k)


def price_of_band(band: float, price_min: float, price_max: float) -> float:
    """Band position → price. Only the yard and build-storage books work on
    this axis; everything else works on `s`."""
    return price_min + band * (price_max - price_min)


def _finite(x) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _f(x, default=_NAN) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


# ---------------------------------------------------------------------------
# DB layer
# ---------------------------------------------------------------------------

def current_save_id(conn: sqlite3.Connection) -> int:
    """The snapshot every world-state table is keyed on. Never hardcode it —
    the DB rotates snapshots as saves are imported."""
    row = conn.execute("SELECT save_id FROM current_save").fetchone()
    if row is None or row[0] is None:
        raise ValueError("no snapshot in this database (current_save is empty)")
    return int(row[0])


def _read(conn, sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)


def _num(series, fill=0.0):
    return pd.to_numeric(series, errors="coerce").fillna(fill)


def _bands(conn, bands: pd.DataFrame | None) -> pd.DataFrame:
    """Ware bands. The analysis DB's `ware` table is loaded from RefData;
    pass `bands` to score against a different (e.g. mod-patched) table.
    Bands are NOT mod-patched today — `gamedata/modpatch.py` patches recipes."""
    if bands is None:
        bands = _read(conn, "SELECT id AS ware, price_min, price_avg, "
                            "price_max, tags FROM ware")
    out = bands.copy()
    if "ware" not in out.columns and "id" in out.columns:
        out = out.rename(columns={"id": "ware"})
    for col in ("price_min", "price_avg", "price_max"):
        out[col] = _num(out.get(col), _NAN) if col in out.columns \
            else pd.Series(_NAN, index=out.index)
    if "tags" not in out.columns:
        out["tags"] = ""
    return out[["ware", "price_min", "price_avg", "price_max", "tags"]]


def net_positions(conn: sqlite3.Connection, save_id: int) -> pd.DataFrame:
    """`stock + undelivered inbound − committed outbound` per (station, ware).

    `trade_pending` is keyed `(save_id, trade_id)` in the analysis DB, so it
    is deduplicated by construction — unlike the Phase-1 scratch corpus, which
    stores every trade twice (`source='order'` and `'reservation'`) and
    doubles both pending terms when summed naively. Verified here rather than
    assumed. The per-trade remainder is floored at zero: a purged trade can
    read `amount = 0, transferred = 5166`, which would otherwise *add* stock.
    """
    dup = conn.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT trade_id) FROM trade_pending "
        "WHERE save_id = ?", (save_id,)).fetchone()[0]
    if dup:
        raise ValueError(f"trade_pending holds {dup} duplicate trade_ids on "
                         f"save {save_id}: net positions would double-count")

    stock = _read(conn, "SELECT object_id AS station_id, ware, amount AS stock "
                        "FROM cargo WHERE save_id = ?", (save_id,))
    pend = _read(conn, """
        SELECT buyer_id, seller_id, ware,
               MAX(COALESCE(amount, 0) - COALESCE(transferred, 0), 0) AS rest
        FROM trade_pending WHERE save_id = ?""", (save_id,))
    inb = (pend.groupby(["buyer_id", "ware"])["rest"].sum().rename("inbound")
           .reset_index().rename(columns={"buyer_id": "station_id"}))
    outb = (pend.groupby(["seller_id", "ware"])["rest"].sum().rename("outbound")
            .reset_index().rename(columns={"seller_id": "station_id"}))
    net = (stock.merge(inb, on=["station_id", "ware"], how="outer")
                .merge(outb, on=["station_id", "ware"], how="outer"))
    for col in ("stock", "inbound", "outbound"):
        net[col] = _num(net[col])
    net["net"] = net["stock"] + net["inbound"] - net["outbound"]
    return net


def _recipe_inputs(conn) -> tuple[dict, dict]:
    """(ware, method) -> input wares, and ware -> input wares (any method)."""
    rec = _read(conn, "SELECT ware, method, input_ware FROM recipe "
                      "WHERE input_ware IS NOT NULL AND input_ware != ''")
    by_key: dict = {}
    by_ware: dict = {}
    for ware, method, inw in zip(rec["ware"], rec["method"], rec["input_ware"]):
        by_key.setdefault((ware, method), set()).add(inw)
        by_ware.setdefault(ware, set()).add(inw)
    return by_key, by_ware


def ration_pairs(conn: sqlite3.Connection, save_id: int) -> set:
    """(station, ware) pairs that are rations *for that station*: which wares
    count is set by the races actually present in its workforce (E-120), not
    by the ware's role in the economy."""
    by_key, _ = _recipe_inputs(conn)
    by_race = {method: ins for (ware, method), ins in by_key.items()
               if ware == _WORKUNIT}
    wf = _read(conn, "SELECT station_id, race FROM workforce "
                     "WHERE save_id = ? AND COALESCE(amount, 0) > 0",
               (save_id,))
    out = set()
    for sid, race in zip(wf["station_id"], wf["race"]):
        for ware in by_race.get(race, by_race.get("default", ())):
            out.add((sid, ware))
    return out


def self_consumed_pairs(conn: sqlite3.Connection, save_id: int,
                        bands: pd.DataFrame | None = None) -> set:
    """(station, ware) pairs the station itself eats — the predicate of the
    cap's self-consumption exemption (cap-scope report § 3):

    * an input to one of its own production recipes (built module → recipe),
    * a build resource while it carries a built `buildmodule*`,
    * a ration of a race present in its workforce.

    On snapshot 71 this splits the 49 saturated supplier offers perfectly:
    0/19 self-consumed sit at the band minimum, 30/30 non-self-consumed do.
    Defensive throughout — a modded module macro with no `module_ref` row, or
    a ware absent from the reference CSVs, contributes nothing rather than
    raising.
    """
    band = _bands(conn, bands)
    by_key, by_ware = _recipe_inputs(conn)
    pairs: set = set()

    mods = _read(conn, "SELECT DISTINCT host_id AS station_id, macro "
                       "FROM build_entry WHERE save_id = ? AND built = 1",
                 (save_id,))
    mref = _read(conn, "SELECT macro, ware, method FROM module_ref "
                       "WHERE ware IS NOT NULL AND ware != ''")
    macro_inputs: dict = {}
    for macro, ware, method in zip(mref["macro"], mref["ware"], mref["method"]):
        ins = (by_key.get((ware, method)) or by_key.get((ware, "default"))
               or by_ware.get(ware) or ())
        if ins:
            macro_inputs.setdefault(macro, set()).update(ins)
    for sid, macro in zip(mods["station_id"], mods["macro"]):
        for w in macro_inputs.get(macro, ()):
            pairs.add((sid, w))

    # build resources: the `stationbuilding`-tagged wares, with a recipe-based
    # fallback for reference data carrying no tags column
    build_wares = {w for w, t in zip(band["ware"], band["tags"].fillna(""))
                   if "stationbuilding" in str(t)}
    if not build_wares:
        economy = set(band["ware"])
        build_wares = {i for ins in by_ware.values() for i in ins
                       if i in economy}
    for sid, macro in zip(mods["station_id"], mods["macro"]):
        if str(macro).startswith(_BUILDMODULE):
            for w in build_wares:
                pairs.add((sid, w))

    pairs |= ration_pairs(conn, save_id)
    return pairs


# ---------------------------------------------------------------------------
# the price book
# ---------------------------------------------------------------------------

def price_book(conn: sqlite3.Connection, save_id: int | None = None, *,
               bands: pd.DataFrame | None = None,
               value_cap: float = VALUE_CAP_CR,
               a_supplier: float = A_SUPPLIER,
               a_ration: float = A_RATION,
               a_input: float = A_INPUT,
               a_yard: float = A_YARD,
               yard_k: float = YARD_K,
               yard_form: str = YARD_FORM,
               self_consumed_exemption: bool = True,
               fitted_input_offsets: bool = False,
               span: float = SPAN) -> pd.DataFrame:
    """Every trade offer in the snapshot, classified, predicted and scored.

    One row per offer. Key columns: `book` (which price book), `population`
    (the sub-book the offset came from), `net`, `allocation`, `target`, `a`,
    `fill`, `s_obs`, `s_pred`, `price_pred`, `res` — the residual in **band
    units**, `(observed − predicted) / half-spread on the observed side` —
    and `clamped` (|s_obs| ≥ 1: the offer sits on a band edge and carries no
    information about the fill coordinate).

    Scoring is in band units, never in `u`: `u = 1.095·acos(s)/π` is flat near
    the clamps, so a four-cent price difference at the band minimum
    manufactures a `u` residual of 2–5.

    `price_pred` is NaN where no law is claimed (player-owned offers, and any
    offer whose denominator is missing). `confidence` labels every row `law`,
    `descriptive` or `none`, so E-118's measured shape cannot be mistaken for
    a confirmed rule.
    """
    if save_id is None:
        save_id = current_save_id(conn)
    band = _bands(conn, bands)

    off = _read(conn, """
        SELECT o.object_id AS station_id, o.side, o.ware,
               COALESCE(o.amount, 0) AS amount, o.price_cr,
               COALESCE(o.flags, '') AS flags, o.desired,
               c.class AS host_class, c.owner, c.code AS station_code,
               c.name AS station_name, c.macro AS station_macro
        FROM trade_offer o
        LEFT JOIN component c
               ON c.id = o.object_id AND c.save_id = o.save_id
        WHERE o.save_id = ?""", (save_id,))
    if off.empty:
        return off.assign(book=pd.Series(dtype=str))
    off["flags"] = off["flags"].fillna("")
    off = off.merge(band, on="ware", how="left")
    off = off.merge(net_positions(conn, save_id)[
        ["station_id", "ware", "stock", "inbound", "outbound", "net"]],
        on=["station_id", "ware"], how="left")

    # one allocation row per (station, ware): station_storage is keyed by role
    # as well, so aggregate rather than risk duplicating offers on the join
    alloc = _read(conn, """
        SELECT station_id, ware, MAX(max_units) AS allocation,
               MIN(role) AS role
        FROM station_storage WHERE save_id = ? AND role != 'supply'
        GROUP BY station_id, ware""", (save_id,))
    off = off.merge(alloc, on=["station_id", "ware"], how="left")
    for col in ("stock", "inbound", "outbound", "net", "amount"):
        off[col] = _num(off[col])

    # ---- book membership -------------------------------------------------
    lock = _read(conn, """
        SELECT object_id AS station_id, ware FROM station_trade_setting
        WHERE save_id = ? AND setting = 'lockavgprice'""", (save_id,))
    lock_pairs = set(zip(lock["station_id"], lock["ware"]))
    manual = _read(conn, """
        SELECT object_id AS station_id, ware FROM price_setting
        WHERE save_id = ? AND kind != 'reference'
        UNION
        SELECT object_id AS station_id, ware FROM ware_limit
        WHERE save_id = ?""", (save_id, save_id))
    manual_pairs = set(zip(manual["station_id"], manual["ware"]))
    yard_hosts = set(_read(conn, """
        SELECT DISTINCT host_id FROM build_entry
        WHERE save_id = ? AND built = 1 AND macro LIKE ?""",
        (save_id, _BUILDMODULE + "%"))["host_id"])

    rations = ration_pairs(conn, save_id)
    consumed = (self_consumed_pairs(conn, save_id, band)
                if self_consumed_exemption else set())
    # the supplier predicate is "the station posts a sell offer for the ware",
    # not the ware's role: an input a station also sells takes +0.053, and
    # buy = sell − 1 Cr on the same (station, ware), 704 of 706 pairs exactly
    sells = set(zip(*[off.loc[(off["side"] == "sell")
                              & ~off["flags"].str.contains("supplies|shady"),
                              col]
                      for col in ("station_id", "ware")])) or set()

    rows = []
    for r in off.itertuples(index=False):
        key = (r.station_id, r.ware)
        book = _classify(r, key, lock_pairs, manual_pairs, yard_hosts)
        rows.append({
            "book": book,
            "is_ration": key in rations or r.role == "food",
            "self_consumed": key in consumed,
            "has_sell": key in sells,
        })
    cls = pd.DataFrame(rows, index=off.index)
    off = pd.concat([off, cls], axis=1)
    off["population"] = [
        (("supplier" if sell else "ration" if ration else "input")
         if book in ("main", "yard") else book)
        for book, sell, ration in zip(off["book"], off["has_sell"],
                                      off["is_ration"])]

    # ---- the per-station input constant ----------------------------------
    # Measured from the station's OWN buy-only production-input offers, never
    # from the offer being predicted. The blanket −0.039 is a population
    # median only (within-station sd 0.0114 vs between-station 0.0542).
    fitted = station_input_offsets(off, span=span)

    out = []
    for r in off.itertuples(index=False):
        out.append(_predict(r, fitted=fitted, value_cap=value_cap,
                            a_supplier=a_supplier, a_ration=a_ration,
                            a_input=a_input, a_yard=a_yard, yard_k=yard_k,
                            yard_form=yard_form, span=span,
                            exemption=self_consumed_exemption,
                            use_fitted=fitted_input_offsets))
    off = pd.concat([off, pd.DataFrame(out, index=off.index)], axis=1)
    # a fill coordinate that exists for EVERY book, so bins stay comparable:
    # build storages hold no allocation, so they fall back on the offer-derived
    # proxy `(stock + inbound) / (stock + inbound + open buy)`
    denom = off["stock"] + off["inbound"] + off["amount"]
    off["fill_proxy"] = ((off["stock"] + off["inbound"]) / denom).where(
        denom > 0)
    off["fill_x"] = off["fill"].fillna(off["fill_proxy"])
    off["abs_res"] = off["res"].abs()
    off["clamped"] = off["s_obs"].abs() >= 1.0
    off["save_id"] = save_id
    return off


def _classify(r, key, lock_pairs, manual_pairs, yard_hosts) -> str:
    """Book precedence: a manual price setting beats everything (it is not a
    price book at all), then the offer's own flags, then the station's
    whitelist, then the host's kind.

    Flags MUST outrank the whitelist. 13 offers on snapshot 71 are both
    `supplies`-flagged and on their station's `lockavgprice` list, and every
    one of them prices at the band MIDPOINT (hullparts 240.5, smartchips 63,
    missilecomponents 11) — the self-supply book — not at `avg − 1`. Booking
    the whitelist first puts those 13 in the wrong book with a residual of
    0.5–0.75 band units.
    """
    if r.owner == "player" or key in manual_pairs:
        return "player"
    flags = str(r.flags)
    if "supplies" in flags:
        return "supplies"
    if "shady" in flags:
        return "shady"
    if key in lock_pairs:
        return "lockavgprice"
    if r.host_class == "buildstorage":
        return "buildstorage"
    if r.station_id in yard_hosts:
        return "yard"
    return "main"


def _predict(r, *, fitted, value_cap, a_supplier, a_ration, a_input, a_yard,
             yard_k, yard_form, span, exemption, use_fitted) -> dict:
    """One offer's prediction and residual. Scalar by design: the closed-form
    functions above ARE the implementation, so testing them tests this."""
    pmin, pavg, pmax = _f(r.price_min), _f(r.price_avg), _f(r.price_max)
    obs = _f(r.price_cr)
    alloc = _f(r.allocation)
    net = _f(r.net, 0.0)
    a_st = fitted.get(r.station_id, a_input)

    a = _NAN
    target = _NAN
    exempt = False
    pred = _NAN
    conf = "none"
    tier = ""

    if r.book in ("main", "yard"):
        # Yards are NOT a separate family: they are the main sequence with a
        # distinctive per-station consumer offset (−0.2026, MAD 0.0007 over 61
        # yards). See `score_yard_forms` — the clamped power k ≈ 2.6 that
        # E-028 carried is a shape artifact, and it is the alternative here.
        conf = "law"
        a_consumer = a_yard if r.book == "yard" else a_input
        if use_fitted or r.book == "yard":
            a_consumer = fitted.get(r.station_id, a_consumer)
        if r.population == "supplier":
            a = a_supplier
            target = capped_target(alloc, pavg, value_cap)
            # the self-consumption exemption (cap-scope report § 3): a supplier
            # offer already above its capped target, for a ware the station
            # itself eats, does not clamp at the band minimum — it leaves the
            # supplier book for the consumer book (target = allocation, offset
            # = the station's own input constant). HYPOTHESIS (strong): 19/19
            # and 30/30 on snapshot 71, and it is neutral below the target.
            if (exemption and r.self_consumed and _finite(target)
                    and net > target):
                exempt, target, a = True, alloc, a_consumer
        elif r.population == "ration":
            # role/predicate-keyed, never the station's own constant: the same
            # stations whose inputs run −0.97…+0.54 hold their rations at
            # +0.006 (E-015 CONFIRMED). That includes yards.
            a, target = a_ration, alloc
        else:
            a, target = a_consumer, alloc
        if r.book == "yard" and yard_form == "power":
            denom = _f(r.stock, 0.0) + _f(r.inbound, 0.0) + _f(r.amount, 0.0)
            pred = (price_of_band(yard_band(net / denom, yard_k), pmin, pmax)
                    if denom > 0 else _NAN)
        else:
            pred = main_sequence_price(net, target, pmin, pavg, pmax, a, span)
    elif r.book == "lockavgprice":
        conf, pred = "law", lockavgprice_price(pavg, r.side)
    elif r.book == "supplies":
        conf, pred = "law", supplies_price(pavg, pmax)
    elif r.book == "shady":
        conf = "descriptive"
        tier = shady_tier_of_price(obs, pavg, pmax)
        pred = shady_price(tier, pavg, pmax)
    elif r.book == "buildstorage":
        conf = "descriptive"
        denom = _f(r.stock, 0.0) + _f(r.inbound, 0.0) + _f(r.amount, 0.0)
        if denom > 0:
            fill = (_f(r.stock, 0.0) + _f(r.inbound, 0.0)) / denom
            pred = price_of_band(build_storage_band(fill), pmin, pmax)

    half = (pmax - pavg) if obs >= pavg else (pavg - pmin)
    half = half if _finite(half) and half > 0 else _NAN
    return {
        "a": a, "target": target, "exempt": exempt,
        "fill": net / alloc if _finite(alloc) and alloc else _NAN,
        "u": net / target + a if _finite(target) and target else _NAN,
        "price_pred": pred, "confidence": conf, "shady_tier": tier,
        "s_obs": (obs - pavg) / half if _finite(half) else _NAN,
        "s_pred": (pred - pavg) / half if _finite(half) else _NAN,
        "res": (obs - pred) / half if _finite(half) else _NAN,
    }


def station_input_offsets(book: pd.DataFrame, *, min_offers: int = 2,
                          span: float = SPAN) -> dict:
    """Per-station input constant `a`, measured from that station's unclamped
    buy-only production-input offers (median implied `a`).

    E-011's "per-module input reserve" reading is FALSIFIED: the offset is a
    fill *fraction* shared across inputs whose allocations differ by up to
    1,764×, it is flat to a median 0.006 across 13 epochs while stock moves
    10–50 % of allocation, and 169 of 909 stations carry a positive one, which
    no reserve can produce. What sets it is still unknown, so this is a
    measurement, not a model.
    """
    need = {"book", "population", "side", "price_cr", "price_avg", "net",
            "allocation"}
    if book.empty or not need <= set(book.columns):
        return {}
    sub = book[book["book"].isin(("main", "yard"))
               & (book["population"] == "input") & (book["side"] == "buy")]
    if sub.empty:
        return {}
    acc: dict = {}
    for r in sub.itertuples(index=False):
        pmin, pavg, pmax = _f(r.price_min), _f(r.price_avg), _f(r.price_max)
        obs, alloc = _f(r.price_cr), _f(r.allocation)
        if not (_finite(pavg) and _finite(alloc) and alloc):
            continue
        s = s_of_price(obs, pmin, pavg, pmax)
        if abs(s) >= 1.0:                     # clamped: carries no information
            continue
        implied = u_of_s(s, span) - _f(r.net, 0.0) / alloc
        if _finite(implied):
            acc.setdefault(r.station_id, []).append(implied)
    return {sid: float(pd.Series(vs).median())
            for sid, vs in acc.items() if len(vs) >= min_offers}


# ---------------------------------------------------------------------------
# scoring — the mandatory discipline, in code
# ---------------------------------------------------------------------------

def bin_median_rmse(frame: pd.DataFrame, *, by: str = "fill",
                    value: str = "abs_res", bins: int = 20,
                    lo: float = 0.0, hi: float = 1.2,
                    equal_count: bool = False) -> float:
    """RMS over per-bin MEDIAN |residual|, equal weight per bin.

    Fit shapes on bin medians, never on per-offer MAE: per-offer error is
    dominated by the crowded middle of the curve, where a clamped line and a
    cosine are indistinguishable, and it will report a clamped line as a good
    fit. The ends discriminate and they hold few offers. That mistake produced
    a "piecewise linear with knees" conclusion that had to be retracted.

    Binning is rule-INDEPENDENT by default — fixed edges on `fill` — so the
    bins do not move when the rule under test moves.

    `value` selects which residual is aggregated, and the two answer different
    questions. `abs_res` (the default) measures how wrong a typical offer is;
    `res` takes the per-bin median of the SIGNED residual first and so
    measures bias — whether the curve is in the right place — cancelling
    symmetric scatter. The figures published in the model doc and the
    value-cap report are the signed variant (that is how `main: all` reads
    0.0066 while its `input` sub-population sits at MAD 0.072), so both are
    reported by `population_scores` and neither is allowed to stand alone.
    """
    if frame.empty or by not in frame.columns or value not in frame.columns:
        return _NAN
    sub = frame[frame[by].apply(_finite) & frame[value].apply(_finite)]
    if sub.empty:
        return _NAN
    if equal_count:
        try:
            cut = pd.qcut(sub[by], bins, duplicates="drop")
        except ValueError:
            return _NAN
    else:
        edges = [lo + (hi - lo) * i / bins for i in range(bins + 1)]
        cut = pd.cut(sub[by].clip(lo, hi), edges, include_lowest=True)
    med = sub.groupby(cut, observed=True)[value].median().dropna()
    if med.empty:
        return _NAN
    return math.sqrt(float((med ** 2).mean()))


def population_scores(book: pd.DataFrame, *, bins: int = 20,
                      eqcount_bins: int = 24, by: str = "fill_x",
                      tail: float = 0.25) -> pd.DataFrame:
    """The documented population metrics — n, bin-median RMSE, MAD (the MEDIAN
    absolute residual) and the `|res| > tail` fraction — per population.

    Score every candidate on the WHOLE population as well as on the cohort it
    was derived from: a rule that reproduces one station and degrades the
    save-wide fit is over-fitting. The save-wide bin median is by itself blind
    to a small badly-wrong cohort (399 capped offers hid inside 24 bins of
    ~300), which is why the tail fraction is reported alongside it.
    """
    rows = []

    def add(label, sub):
        sub = sub[sub["res"].apply(_finite)] if "res" in sub.columns else sub
        if sub.empty:
            rows.append({"population": label, "n": 0, "bin_rmse": _NAN,
                         "bin_rmse_eqcount": _NAN, "mad": _NAN, "tail": _NAN})
            return
        rows.append({"population": label, "n": int(len(sub)),
                     "bin_rmse": bin_median_rmse(sub, by=by, bins=bins),
                     "bin_rmse_eqcount": bin_median_rmse(
                         sub, by=by, bins=eqcount_bins, equal_count=True),
                     "bin_rmse_signed": bin_median_rmse(
                         sub, by=by, value="res", bins=eqcount_bins,
                         equal_count=True),
                     "mad": float(sub["abs_res"].median()),
                     "tail": float((sub["abs_res"] > tail).mean())})

    main = book[book["book"] == "main"]
    add("main: ration", main[main["population"] == "ration"])
    add("main: supplier", main[main["population"] == "supplier"])
    add("main: supplier, cap binds",
        main[(main["population"] == "supplier")
             & (main["target"] < main["allocation"] - 1e-9)])
    add("main: input", main[main["population"] == "input"])
    add("main: all", main)
    for bk in BOOKS:
        if bk != "main":
            add(f"book: {bk}", book[book["book"] == bk])
    add("all offers", book)
    return pd.DataFrame(rows)


def score_yard_forms(book: pd.DataFrame, *, k: float = YARD_K,
                     a_yard: float = A_YARD, a_ration: float = A_RATION,
                     a_supplier: float = A_SUPPLIER, span: float = SPAN,
                     bins: int = 16, buy_only: bool = True) -> pd.DataFrame:
    """Score the two live descriptions of the yard book against each other.

    (i) **power** — `band = clamp(1 − fill^k)` on the offer-derived proxy
        denominator `stock + inbound + open buy amount` (build-demand report,
        k = 2.62 refitted on snapshot 71 against E-028's registered 2.60).
    (ii) **cosine** — the ordinary main-sequence cosine on the storage
        allocation, with the yard station constant `a = −0.202` on the input
        population (offset-family report: 41/41 stations within ±0.005 of
        −0.2026, all carrying a built `buildmodule`; ULG-519 in the cap-scope
        report) and the ordinary role offsets on the other populations.

    One free parameter each (`k` vs `a`), both fitted on this same population,
    so the comparison is like for like. Both are scored on the WHOLE yard
    population, in band units, with bin medians and equal weight per bin on a
    rule-independent x (the proxy fill), and both are reported — the loser is
    evidence, not noise. `buy_only` matches the build-demand report's
    population; the 22 yard SELL offers take the ordinary supplier offset and
    are scored separately by `population_scores`.
    """
    yard = book[book["book"] == "yard"]
    if buy_only:
        yard = yard[yard["side"] == "buy"]
    if yard.empty:
        return pd.DataFrame(columns=["form", "n", "bin_rmse", "mad", "tail"])
    fitted = station_input_offsets(book, span=span)
    rows = []
    for name, form in (("power (proxy, k=%.2f)" % k, "power"),
                       ("cosine (allocation, flat a=%.4f)" % a_yard, "flat"),
                       ("cosine (allocation, per-station a)", "fitted")):
        recs = []
        for r in yard.itertuples(index=False):
            pmin, pavg, pmax = _f(r.price_min), _f(r.price_avg), _f(r.price_max)
            obs, alloc, net = _f(r.price_cr), _f(r.allocation), _f(r.net, 0.0)
            denom = _f(r.stock, 0.0) + _f(r.inbound, 0.0) + _f(r.amount, 0.0)
            fill = net / denom if denom > 0 else _NAN
            if form == "power":
                pred = (price_of_band(yard_band(fill, k), pmin, pmax)
                        if _finite(fill) else _NAN)
            else:
                a = (a_supplier if r.population == "supplier" else
                     a_ration if r.population == "ration" else
                     fitted.get(r.station_id, a_yard) if form == "fitted"
                     else a_yard)
                pred = main_sequence_price(net, alloc, pmin, pavg, pmax, a,
                                           span)
            half = (pmax - pavg) if obs >= pavg else (pavg - pmin)
            if not (_finite(half) and half > 0 and _finite(pred)):
                continue
            res = (obs - pred) / half
            recs.append({"fill": fill, "res": res, "abs_res": abs(res),
                         "population": r.population})
        sub = pd.DataFrame(recs)
        if sub.empty:
            continue
        rows.append({"form": name, "n": int(len(sub)),
                     "bin_rmse": bin_median_rmse(sub, bins=bins),
                     "bin_rmse_eqcount": bin_median_rmse(sub, bins=bins,
                                                         equal_count=True),
                     "mad": float(sub["abs_res"].median()),
                     "tail": float((sub["abs_res"] > 0.25).mean())})
    return pd.DataFrame(rows)


def shady_tier_census(conn: sqlite3.Connection, book: pd.DataFrame,
                      save_id: int | None = None) -> pd.DataFrame:
    """Per-station `shady` tier against the station's workforce.

    E-112's open half: which tier a station is on is mutable state, and the
    only correlate found is zero workforce. This reports the cross-tab rather
    than pretending the tier is predictable from the save.
    """
    if save_id is None:
        save_id = current_save_id(conn)
    shady = book[book["book"] == "shady"]
    if shady.empty:
        return pd.DataFrame(columns=["tier", "stations", "offers",
                                     "zero_workforce"])
    wf = _read(conn, "SELECT station_id, SUM(amount) AS workforce FROM "
                     "workforce WHERE save_id = ? GROUP BY station_id",
               (save_id,))
    per = (shady.groupby(["station_id", "shady_tier"]).size().rename("offers")
           .reset_index().merge(wf, on="station_id", how="left"))
    per["workforce"] = _num(per["workforce"])
    return (per.groupby("shady_tier")
            .agg(stations=("station_id", "nunique"), offers=("offers", "sum"),
                 zero_workforce=("workforce", lambda s: float((s == 0).mean())))
            .reset_index().rename(columns={"shady_tier": "tier"}))
