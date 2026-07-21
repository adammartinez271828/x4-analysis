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


def save_table(df: pd.DataFrame, files_dir: Path, title: str, guid: str) -> str:
    table_html = df.to_html(index=False, border=0, table_id="tbl",
                            classes="display nowrap", justify="left",
                            float_format=lambda v: f"{v:,.2f}")
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<link rel='stylesheet' href='{_DT_CSS}'>
<script src='{_JQ_JS}'></script><script src='{_DT_JS}'></script>
<style>
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
</style>
</head><body>
{table_html.replace('<thead>', f'<caption>{title}</caption><thead>', 1)}
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


def build_tables(frames: Frames, ref: RefData, cfg: Config, files_dir: Path,
                 guid: str) -> list[str]:
    out: list[str] = []
    time_limit = frames.time_now - 3600 * cfg.history_hours
    window = (frames.time_now - time_limit) / 3600.0
    hh = f"{cfg.history_hours:g}h"

    sales = frames.sales
    recent = sales[(sales["time"] > time_limit) & (sales["money"] > 0)]
    if not recent.empty:
        title = f"Gross Earnings per Seller - {hh}"
        log("->", title)
        seller = (recent["seller.name"].astype(str) + " ("
                  + recent["seller.code"].astype(str) + ")").rename("Seller")
        out.append(save_table(_earnings_table(recent, seller, window),
                              files_dir, title, guid))

        title = f"Gross Earnings per Ware or Service - {hh}"
        log("->", title)
        out.append(save_table(
            _earnings_table(recent, recent["commodity"].rename("Commodity"),
                            window),
            files_dir, title, guid))
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
