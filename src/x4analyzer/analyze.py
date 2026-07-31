"""Top-level analysis pipeline: savegame -> dataframes -> dashboard."""

from __future__ import annotations

from pathlib import Path

from .db import store
from .db.schema import AGGREGATE_TABLES
from .cli import log
from .config import Config
from .analysis.frames import build_frames, station_types_from_db
from .analysis.storage import station_storage
from .analysis.drones import station_munition
from .gamedata.modpatch import patch_reference
from .gamedata.refdata import load_refdata
from .save.parser import parse_savegame, peek_save_info


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
    # Mods that rewrite production recipes are applied to THIS RUN's reference
    # data only -- the bundled CSVs stay stock (gamedata/modpatch.py).
    ref = patch_reference(save, ref, log=log)

    conn = store.open_db(cfg, save.guid)
    try:
        log("Database:", store.db_path(cfg, save.guid))
        store.write_reference(conn, ref)
        store.import_legacy_caches(conn, cfg, save.guid, ref)
        # registry first: its component->entity mapping stamps both the
        # snapshot (component.entity_id) and the merged event rows
        entities = store.update_entity_registry(conn, save, ref)
        save_id = store.write_snapshot(conn, save, ref, save_file, entities)
        # trend layer: per-snapshot aggregates, appended once per distinct
        # snapshot (reruns add nothing)
        store.write_aggregates(conn, save_id)
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

        _scrub_frozen_ld_library_path()
        webbrowser.open(out.as_uri())
    return 0


def _scrub_frozen_ld_library_path() -> None:
    """Restore the pre-bootloader LD_LIBRARY_PATH in frozen Linux builds.

    PyInstaller's one-file bootloader points LD_LIBRARY_PATH at its
    extraction dir so the bundled Python finds the bundled shared libs --
    built on an old distro for glibc compatibility. Child processes
    inherit it, so xdg-open/kde-open pick up the bundled (older)
    libstdc++.so.6 and abort with GLIBCXX version errors on newer
    systems. Nothing runs after the browser launch, so restoring the
    original environment here is safe.
    """
    import os
    import sys

    if not (getattr(sys, "frozen", False) and sys.platform.startswith("linux")):
        return
    orig = os.environ.get("LD_LIBRARY_PATH_ORIG")
    if orig is not None:
        os.environ["LD_LIBRARY_PATH"] = orig
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)


def run_seed(cfg: Config, files: list[Path] | None = None) -> int:
    """Seed the trend layer (A tables) from archived saves.

    Imports each given save file (default: every save the config can
    discover) in game-time order through the normal snapshot path. Per
    save that adds: a `save` provenance row and the per-snapshot A rows.
    The guards make history safe around it — the entity registry
    resolves historic saves read-only (no lifecycle edits), the
    stale-save merge guard keeps their shorter event windows out of the
    E tables, and snapshots that already have trend rows are skipped
    without a parse. Because imports run oldest→newest, the W tables end
    at the newest world state; the command refuses a batch that would
    leave them older than the stored head."""
    files = [f for f in (files or cfg.find_all_savegames())
             if "temp" not in f.name]
    if not files:
        log("No save files to seed from")
        return 1
    infos = []
    for f in files:
        guid, gtime, sdate = peek_save_info(f)
        if not guid:
            log(f"WARNING: {f} has no <info> header; skipped")
            continue
        infos.append((guid, gtime, sdate or None, f))

    log("Loading reference data from", cfg.data_dir)
    ref = load_refdata(cfg.data_dir)
    rc = 0
    for guid in sorted({i[0] for i in infos}):
        batch = sorted((i for i in infos if i[0] == guid),
                       key=lambda i: i[1])
        conn = store.open_db(cfg, guid)
        try:
            head = conn.execute(
                "SELECT MAX(game_time) FROM v_snapshot").fetchone()[0]
            todo = []
            for _g, gtime, sdate, f in batch:
                snap = conn.execute(
                    "SELECT MIN(save_id) FROM save WHERE guid IS ?"
                    " AND game_time IS ? AND save_date IS ?",
                    (guid, gtime, sdate)).fetchone()[0]
                if snap is None or not conn.execute(
                        "SELECT 1 FROM sector_presence WHERE save_id = ?"
                        " LIMIT 1", (snap,)).fetchone():
                    todo.append((gtime, f))
            if not todo:
                log(f"{guid}: trend layer already covers all "
                    f"{len(batch)} saves; nothing to do")
                continue
            # the last import decides the W tables' world state: it must
            # be at least as new as the stored head. If the newest known
            # file is the head itself but already has trend rows, rerun
            # it anyway (A appends skip, the W rebuild restores state).
            newest = batch[-1]
            if head is not None and todo[-1][0] < head:
                if newest[1] >= head:
                    todo.append((newest[1], newest[3]))
                else:
                    log(f"ERROR: seeding {guid} would leave the world "
                        f"state at game time {todo[-1][0]:.0f}, older "
                        f"than the stored head ({head:.0f}); include the "
                        "newest save in the input set")
                    rc = 1
                    continue
            store.write_reference(conn, ref)
            for gtime, f in todo:
                log(f"Seeding {guid} from {f.name} "
                    f"(game time {gtime:.0f})")
                save = parse_savegame(f, progress=log)
                entities = store.update_entity_registry(conn, save, ref)
                save_id = store.write_snapshot(conn, save, ref, f,
                                               entities)
                store.write_aggregates(conn, save_id)
                store.merge_events(conn, save, ref,
                                   station_types_from_db(conn, ref),
                                   entities)
            n_snap = conn.execute(
                "SELECT COUNT(*) FROM v_snapshot").fetchone()[0]
            counts = ", ".join(
                f"{t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}"
                f" rows / "
                f"{conn.execute(f'SELECT COUNT(DISTINCT save_id) FROM {t}').fetchone()[0]}"
                " snapshots" for t in AGGREGATE_TABLES)
            log(f"{guid}: {n_snap} distinct snapshots; {counts}")
        finally:
            conn.close()
    return rc
