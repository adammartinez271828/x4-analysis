"""Top-level analysis pipeline: savegame -> dataframes -> dashboard."""

from __future__ import annotations

from .cli import log
from .config import Config
from .frames import build_frames
from .refdata import load_refdata
from .saveparser import parse_savegame


def run_analysis(cfg: Config) -> int:
    save_file = cfg.find_savegame()
    log("Loading reference data from", cfg.data_dir)
    ref = load_refdata(cfg.data_dir)

    log("Parsing savegame:", save_file)
    save = parse_savegame(save_file, progress=log)
    log(f"Game version {save.game_version}, GUID {save.guid}")
    log(f"Player: {save.player_name} ({save.player_faction_name or 'Player'})")
    if save.modified:
        log("NOTE: savegame is flagged as modified (mods active)")

    frames = build_frames(save, ref, cfg)

    log(f"Log spans {frames.logged_hours:.1f} hours "
        f"({len(frames.log)} entries incl. cache)")
    log(f"Player assets: {len(frames.stations)} stations, "
        f"{len(frames.ships)} ships, {len(frames.npcs)} NPCs")
    log(f"Trades: {len(frames.tradelog)} (sales {len(frames.sales)}, "
        f"buys {len(frames.buys)})")

    from .dashboard import build_dashboard

    out = build_dashboard(cfg, save, ref, frames)
    log("Dashboard:", out)
    if cfg.open_browser:
        import webbrowser

        webbrowser.open(out.as_uri())
    return 0
