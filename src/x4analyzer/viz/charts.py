"""Time-series charts (R lines 1007-1211), rendered as interactive plotly
instead of static ggplot images."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from ..cli import log
from ..frames import Frames
from ..refdata import RefData
from .common import hourly_average, hourly_series, mixed_rainbow, save_widget

SHIP_SERVICES = ["Ship construction", "Ship repair", "Ship resupply"]


def _by_volume(series: pd.DataFrame) -> list:
    """Group keys ordered by total money, largest first (legend order)."""
    totals = series.groupby("group", observed=True)["money"].sum()
    return list(totals.sort_values(ascending=False).index)


def _bar_figure(series: pd.DataFrame, avg: pd.DataFrame, title: str,
                legend_title: str, colours: dict[str, str]) -> go.Figure:
    fig = go.Figure()
    for group in _by_volume(series):
        gdf = series[series["group"] == group]
        fig.add_bar(x=gdf["time"], y=gdf["money"] / 1e6, name=str(group),
                    marker_color=colours.get(str(group)))
    if not avg.empty:
        fig.add_scatter(x=avg["time"], y=avg["money"] / 1e6, mode="lines",
                        line={"dash": "dash", "color": "#e8e8e8"},
                        name="hourly avg", showlegend=False)
    fig.update_layout(
        barmode="relative", title=title,
        xaxis_title="Hours until Now", yaxis_title="Credits/hour (millions)",
        legend={"orientation": "h", "y": -0.15, "title": legend_title,
                "traceorder": "normal"},
        margin={"t": 50},
    )
    return fig


def _area_figure(series: pd.DataFrame, title: str, legend_title: str,
                 colours: dict[str, str]) -> go.Figure:
    fig = go.Figure()
    for group in _by_volume(series):
        gdf = series[series["group"] == group].sort_values("time")
        fig.add_scatter(x=gdf["time"], y=gdf["money"].cumsum() / 1e6,
                        mode="lines", stackgroup="one", name=str(group),
                        line={"width": 0.5, "color": colours.get(str(group))})
    fig.update_layout(
        title=title, xaxis_title="Hours until Now",
        yaxis_title="Credits (millions)",
        legend={"orientation": "h", "y": -0.15, "title": legend_title,
                "traceorder": "normal"},
        margin={"t": 50},
    )
    return fig


def _named_party(df: pd.DataFrame, name_col: str, code_col: str,
                 station_codes: set) -> pd.Series:
    """R 1078-1081: append '(CODE)' to names of non-station sellers/buyers."""
    name = df[name_col].astype(str)
    keep = df[code_col].isin(station_codes)
    return name.where(keep, name + " (" + df[code_col].astype(str) + ")")


def _faction_colours(groups: pd.Series, ref: RefData) -> dict[str, str]:
    return {g: ref.colour_of_short(g) for g in groups.astype(str).unique()}


def _rainbow_colours(groups: pd.Series) -> dict[str, str]:
    uniq = list(dict.fromkeys(groups.astype(str)))
    return dict(zip(uniq, mixed_rainbow(len(uniq))))


def build_charts(frames: Frames, ref: RefData, files_dir: Path,
                 guid: str) -> list[str]:
    """Returns dashboard-relative widget paths in display order."""
    out: list[str] = []
    sales, buys = frames.sales, frames.buys
    if sales.empty:
        return out
    maxtime = float(sales["time"].max())
    station_codes = set(frames.stations["code"]) if not frames.stations.empty \
        else set()

    def emit(df, group_col, title, legend_title, colours, value_col="money",
             avg_df=None):
        if df.empty:
            return
        log("->", title)
        series = hourly_series(df, group_col, maxtime, value_col)
        avg = hourly_average(avg_df if avg_df is not None else df, maxtime,
                             value_col=value_col)
        out.append(save_widget(
            _bar_figure(series, avg, title, legend_title, colours),
            files_dir, title, guid))
        title2 = f"{title} (cumulative)"
        log("->", title2)
        out.append(save_widget(
            _area_figure(series, title2, legend_title, colours),
            files_dir, title2, guid))

    # Ship Construction per Faction (R 1015-1043)
    df = sales[(sales["money"] > 0)
               & (sales["commodity"] == "Ship construction")].copy()
    df["buyer.faction"] = df["buyer.faction"].astype(str).replace("nan", "NIL")
    emit(df, "buyer.faction", "Ship Construction per Faction", "Faction",
         _faction_colours(df["buyer.faction"], ref))

    # Commodity Sales per Faction (R 1045-1072)
    df = sales[(sales["money"] > 0) & sales["buyer.faction"].notna()
               & ~sales["commodity"].isin(SHIP_SERVICES)]
    emit(df, "buyer.faction", "Commodity Sales per Faction", "Faction",
         _faction_colours(df["buyer.faction"], ref))

    # Commodity Sales per Seller (R 1074-1106)
    df = sales[(sales["money"] > 0)
               & ~sales["commodity"].isin(SHIP_SERVICES)].copy()
    if not df.empty:
        df["seller"] = _named_party(df, "seller.name", "seller.code",
                                    station_codes)
        emit(df, "seller", "Commodity Sales per Seller", "Seller",
             _rainbow_colours(df["seller"]))

    # Commodity Buys per Buyer (R 1109-1141); buys money is negative
    df = buys[buys["money"] < 0].copy()
    if not df.empty:
        df["buyer"] = _named_party(df, "buyer.name", "buyer.code", station_codes)
        df["money"] = -df["money"]
        emit(df, "buyer", "Commodity Buys per Buyer", "Buyer",
             _rainbow_colours(df["buyer"]))

    # Costs vs Profits (R 1143-1187)
    tl = max(frames.tradelog["time"].min() if not frames.tradelog.empty else 0,
             frames.log["time"].min() if not frames.log.empty else 0)
    df_in = sales[(sales["money"] > 0) & (sales["time"] > tl)]
    df_out = buys[(buys["money"] < 0) & (buys["time"] > tl)]
    if not df_in.empty:
        title = "Costs vs Profits"
        log("->", title)
        s_in = hourly_series(df_in.assign(group="in"), "group", maxtime)
        s_out = hourly_series(df_out.assign(group="out"), "group", maxtime) \
            if not df_out.empty else pd.DataFrame(columns=["time", "money"])
        merged = (s_in.rename(columns={"money": "money.in"})[["time", "money.in"]]
                  .merge(s_out.rename(columns={"money": "money.out"})
                         [["time", "money.out"]], on="time", how="outer")
                  .fillna(0).sort_values("time"))
        net = merged.assign(money=merged["money.in"] + merged["money.out"])
        avg = hourly_average(
            pd.DataFrame({"time": (net["time"] * 3600.0) + maxtime,
                          "money": net["money"]}), maxtime)
        fig = go.Figure()
        fig.add_bar(x=merged["time"], y=merged["money.out"] / 1e6, name="Costs",
                    marker_color="#FF4040")
        fig.add_bar(x=merged["time"], y=net["money"] / 1e6, name="Profits",
                    marker_color="#b0b0b0")
        if not avg.empty:
            fig.add_scatter(x=avg["time"], y=avg["money"] / 1e6, mode="lines",
                            line={"dash": "dash", "color": "#e8e8e8"},
                            showlegend=False)
        fig.update_layout(barmode="overlay", title=title,
                          xaxis_title="Hours until Now",
                          yaxis_title="Credits/hour (millions)",
                          legend={"orientation": "h", "y": -0.15},
                          margin={"t": 50})
        out.append(save_widget(fig, files_dir, title, guid))

        title2 = f"{title} (cumulative)"
        log("->", title2)
        fig = go.Figure()
        fig.add_scatter(x=merged["time"], y=merged["money.out"].cumsum() / 1e6,
                        mode="lines", fill="tozeroy", name="Costs",
                        line={"color": "#FF4040"})
        fig.add_scatter(x=merged["time"], y=net["money"].cumsum() / 1e6,
                        mode="lines", fill="tozeroy", name="Profits",
                        line={"color": "#b0b0b0"})
        fig.update_layout(title=title2, xaxis_title="Hours until Now",
                          yaxis_title="Credits (millions)",
                          legend={"orientation": "h", "y": -0.15},
                          margin={"t": 50})
        out.append(save_widget(fig, files_dir, title2, guid))

    # Account Transfers per Station (cumulative) (R 1191-1211)
    transfers = frames.transfers
    if not transfers.empty:
        title = "Account Transfers per Station (cumulative)"
        log("->", title)
        df = transfers.copy()
        df["station"] = df["station.name"].fillna(df["station.code"]).astype(str)
        series = hourly_series(df, "station", frames.time_now)
        out.append(save_widget(
            _area_figure(series, title, "Station",
                         _rainbow_colours(series["group"])),
            files_dir, title, guid))
    return out
