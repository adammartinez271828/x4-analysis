"""Sortable data tables (R lines 1506-1631), rendered with DataTables from
CDN — the same JS library R's DT package wraps."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..cli import log
from ..config import Config
from ..analysis.frames import Frames
from ..gamedata.refdata import RefData
from .common import DARK_BG, DARK_FG

_DT_CSS = "lib/datatables.min.css"
_DT_JS = "lib/datatables.min.js"
_JQ_JS = "lib/jquery.min.js"


_PAGE_CSS = f"""
body{{font-family:sans-serif;margin:8px;background:{DARK_BG};color:{DARK_FG};}}
caption{{caption-side:top;text-align:left;padding:4px 0;color:{DARK_FG};
         font-weight:bold;}}
table.dataTable, table.dataTable th, table.dataTable td{{color:{DARK_FG};}}
table.dataTable thead th{{border-bottom:1px solid #555;}}
table.dataTable.display tbody tr{{background:{DARK_BG};}}
table.dataTable.display tbody tr.odd{{background:#252525;}}
table.dataTable.display tbody tr:hover{{background:#333;}}
table.dataTable.no-footer{{border-bottom:1px solid #555;}}
.dataTables_wrapper .dataTables_length, .dataTables_wrapper .dataTables_filter,
.dataTables_wrapper .dataTables_info, .dataTables_wrapper .dataTables_paginate,
.dataTables_wrapper .dataTables_paginate .paginate_button{{color:{DARK_FG} !important;}}
.dataTables_wrapper .dataTables_paginate .paginate_button.current,
.dataTables_wrapper .dataTables_paginate .paginate_button:hover{{
  color:#fff !important;background:#3a3a3a;border-color:#555;}}
.dataTables_wrapper .dataTables_paginate .paginate_button.disabled{{
  color:#666 !important;}}
.dataTables_wrapper input, .dataTables_wrapper select{{
  background:#2a2a2a;color:{DARK_FG};border:1px solid #555;}}
.x4opt{{margin:4px 0 8px;font-size:0.9em;color:{DARK_FG};}}
.x4opt label{{cursor:pointer;}}
.x4hidden{{display:none;}}
"""


def _table_html(df: pd.DataFrame, table_id: str, title: str) -> str:
    html = df.to_html(index=False, border=0, table_id=table_id,
                      classes="display nowrap", justify="left",
                      float_format=lambda v: f"{v:,.2f}")
    return html.replace('<thead>', f'<caption>{title}</caption><thead>', 1)


def save_table(df: pd.DataFrame, files_dir: Path, title: str, guid: str) -> str:
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<link rel='stylesheet' href='{_DT_CSS}'>
<script src='{_JQ_JS}'></script><script src='{_DT_JS}'></script>
<style>{_PAGE_CSS}</style>
</head><body>
{_table_html(df, "tbl", title)}
<script>
$(function() {{
  const t = $('#tbl').DataTable({{order: [], pageLength: 10}});
  // size the dashboard iframe to the content (page length changes too)
  const post = () =>
    parent.postMessage({{x4h: document.body.scrollHeight + 8}}, '*');
  t.on('draw', post);
  post();
}});
</script></body></html>"""
    name = f"{title}_{guid}.html"
    (files_dir / name).write_text(html, encoding="utf-8")
    return f"files/{name}"


_INTERNAL_LABEL = ("include internal trades &mdash; your own stations and "
                   "ships trading with each other")


def save_table_variants(df_ext: pd.DataFrame, df_all: pd.DataFrame,
                        files_dir: Path, title: str, guid: str) -> str:
    """Two pre-rendered variants of the same table on one page, swapped by a
    checkbox (default OFF = the external-only numbers)."""
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<link rel='stylesheet' href='{_DT_CSS}'>
<script src='{_JQ_JS}'></script><script src='{_DT_JS}'></script>
<style>{_PAGE_CSS}</style>
</head><body>
<div class='x4opt'><label><input type='checkbox' id='x4internal'>
{_INTERNAL_LABEL}</label></div>
<div id='wrap_ext'>
{_table_html(df_ext, "tbl", title)}
</div>
<div id='wrap_all' class='x4hidden'>
{_table_html(df_all, "tbl_all", title + " (incl. internal)")}
</div>
<script>
$(function() {{
  const opts = {{order: [], pageLength: 10}};
  const ext = $('#tbl').DataTable(opts);
  const all = $('#tbl_all').DataTable(opts);
  // size the dashboard iframe to the content (page length / toggle change it)
  const post = () =>
    parent.postMessage({{x4h: document.body.scrollHeight + 8}}, '*');
  ext.on('draw', post);
  all.on('draw', post);
  $('#x4internal').on('change', function() {{
    const on = this.checked;
    $('#wrap_ext').toggleClass('x4hidden', on);
    $('#wrap_all').toggleClass('x4hidden', !on);
    (on ? all : ext).columns.adjust();
    post();
  }});
  post();
}});
</script></body></html>"""
    name = f"{title}_{guid}.html"
    (files_dir / name).write_text(html, encoding="utf-8")
    return f"files/{name}"


def _earnings_table(df: pd.DataFrame, group: pd.Series | pd.DataFrame,
                    window_hours: float) -> pd.DataFrame:
    keys = group if isinstance(group, pd.DataFrame) else group.to_frame()
    agg = (pd.concat([keys.reset_index(drop=True),
                      df[["money", "amount"]].reset_index(drop=True)], axis=1)
           .assign(count=1)
           .groupby(list(keys.columns), observed=True)
           .agg(Earnings=("money", "sum"), Trades=("count", "sum"),
                Items=("amount", "sum"))
           .reset_index())
    agg["Cr/Trade"] = (agg["Earnings"] / agg["Trades"]).round()
    agg["Cr/Item"] = (agg["Earnings"] / agg["Items"]).round()
    agg["Items/Trade"] = (agg["Items"] / agg["Trades"]).round()
    agg["Cr/Hour"] = (agg["Earnings"] / window_hours).round()
    agg["Trades/Hour"] = (agg["Trades"] / window_hours).round(2)
    return agg.sort_values("Cr/Hour", ascending=False, ignore_index=True)


#: the tradelog columns an internal sale contributes to the earnings tables
_INTERNAL_COLS = ["time", "money", "amount", "commodity",
                  "seller.name", "seller.code"]


def internal_sales(tradelog: pd.DataFrame, time_limit: float) -> pd.DataFrame:
    """Player->player trades in the window: excluded from `frames.sales`
    (external-only by definition) but real earnings for the supplying
    commander under the "Executed by" attribution already baked into the
    tradelog. Defensive: anything missing yields an empty frame."""
    empty = pd.DataFrame(columns=_INTERNAL_COLS)
    if tradelog is None or tradelog.empty:
        return empty
    if any(c not in tradelog.columns
           for c in _INTERNAL_COLS + ["seller.faction", "buyer.faction"]):
        log("warning: tradelog is missing columns; no internal trades")
        return empty
    df = tradelog[(tradelog["seller.faction"] == "PLA")
                  & (tradelog["buyer.faction"] == "PLA")]
    df = df[(df["time"] > time_limit) & (df["money"] > 0)]
    return df[_INTERNAL_COLS].copy() if not df.empty else empty


def _seller_keys(df: pd.DataFrame) -> pd.Series:
    return (df["seller.name"].astype(str) + " ("
            + df["seller.code"].astype(str) + ")").rename("Seller")


def _commodity_keys(df: pd.DataFrame) -> pd.Series:
    return df["commodity"].rename("Commodity")


def earnings_variants(external: pd.DataFrame, internal: pd.DataFrame,
                      keys_for, window_hours: float,
                      ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(external-only, external+internal) aggregates of the same table."""
    ext = _earnings_table(external, keys_for(external), window_hours)
    if internal is None or internal.empty:
        return ext, ext
    combined = pd.concat([external, internal], ignore_index=True)
    return ext, _earnings_table(combined, keys_for(combined), window_hours)


def build_tables(frames: Frames, ref: RefData, cfg: Config, files_dir: Path,
                 guid: str) -> list[str]:
    out: list[str] = []
    time_limit = frames.time_now - 3600 * cfg.history_hours
    window = (frames.time_now - time_limit) / 3600.0
    hh = f"{cfg.history_hours:g}h"

    sales = frames.sales
    recent = sales[(sales["time"] > time_limit) & (sales["money"] > 0)]
    # intra-empire trades, hidden by default behind the earnings toggle
    internal = internal_sales(frames.tradelog, time_limit)
    if not recent.empty:
        title = f"Gross Earnings per Seller - {hh}"
        log("->", title)
        out.append(save_table_variants(
            *earnings_variants(recent, internal, _seller_keys, window),
            files_dir=files_dir, title=title, guid=guid))

        title = f"Gross Earnings per Ware or Service - {hh}"
        log("->", title)
        out.append(save_table_variants(
            *earnings_variants(recent, internal, _commodity_keys, window),
            files_dir=files_dir, title=title, guid=guid))
    else:
        log(f"-> No sales in the past {hh}")

    ships_sold = recent[recent["commodity"] == "Ship construction"]
    if not ships_sold.empty:
        title = f"Gross Earnings per Constructed Ship Type - {hh}"
        log("->", title)
        keys = pd.DataFrame({
            "Faction": ships_sold["buyer.faction"].astype(str),
            "Ship": ships_sold["buyer.name"].astype(str),
        })
        out.append(save_table(_earnings_table(ships_sold, keys, window),
                              files_dir, title, guid))

    if not frames.destroyed.empty:
        title = "Last 50 Destroyed Objects"
        log("->", title)
        df = (frames.destroyed.sort_values("HoursAgo").head(50)
              [["HoursAgo", "object", "location", "killer", "time"]])
        df["HoursAgo"] = df["HoursAgo"].round(1)
        df.columns = ["Hours Ago", "Object", "Location", "Killer", "Timestamp"]
        out.append(save_table(df, files_dir, title, guid))

    contested = frames.sectors[frames.sectors["contested"] == 1]
    if cfg.spoilers_hide:
        contested = contested[contested["knownto"] == "player"]
    if not contested.empty:
        title = "Contested Sectors"
        log("->", title)
        df = contested[["owner", "name"]].copy()
        df["not_player"] = df["owner"] != "player"
        df = df.sort_values(["not_player", "owner", "name"]).drop(
            columns="not_player")
        df["owner"] = df["owner"].map(ref.faction_name).fillna(df["owner"])
        df.columns = ["Owner", "Sector"]
        out.append(save_table(df, files_dir, title, guid))
    return out
