"""Top-level analysis pipeline: savegame -> dataframes -> dashboard."""

from __future__ import annotations

from .db import store
from .cli import log
from .config import Config
from .analysis.frames import build_frames, station_types_from_db
from .analysis.storage import station_storage
from .analysis.drones import station_munition
from .gamedata.refdata import load_refdata
from .save.parser import parse_savegame


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

    conn = store.open_db(cfg, save.guid)
    try:
        log("Database:", store.db_path(cfg, save.guid))
        store.write_reference(conn, ref)
        store.import_legacy_caches(conn, cfg, save.guid, ref)
        save_id = store.write_snapshot(conn, save, ref, save_file)
        entities = store.update_entity_registry(conn, save, ref)
        store.merge_events(conn, save, ref,
                           station_types_from_db(conn, ref), entities)

        frames = build_frames(save, ref, conn)
        store.write_derived(conn, frames)
        frames.station_storage = station_storage(frames, ref)
        store.write_station_storage(conn, save_id, frames.station_storage)
        frames.station_munition = station_munition(save, frames, ref)
        store.write_station_munition(conn, save_id, frames.station_munition)
    finally:
        conn.close()

    log(f"Log spans {frames.logged_hours:.1f} hours "
        f"({len(frames.log)} entries incl. cache)")
    log(f"Player assets: {len(frames.stations)} stations, "
        f"{len(frames.ships)} ships, {len(frames.npcs)} NPCs")
    log(f"Trades: {len(frames.tradelog)} (sales {len(frames.sales)}, "
        f"buys {len(frames.buys)})")

    from .viz.dashboard import build_dashboard

    out = build_dashboard(cfg, save, ref, frames)
    log("Dashboard:", out)
    if cfg.open_browser:
        import webbrowser

        webbrowser.open(out.as_uri())
    return 0
