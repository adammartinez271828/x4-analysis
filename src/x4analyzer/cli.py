"""Command-line entry point: `x4-analyzer [analyze|extract-gamedata]`."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .config import Config


def log(*parts: object) -> None:
    """Timestamped progress message, matching the R script's style."""
    print(time.strftime("%H:%M:%S"), *parts, file=sys.stderr, flush=True)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-dir", type=Path, help="reference CSV / cache directory")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="x4-analyzer",
        description="Analyze an X4: Foundations savegame into an HTML dashboard.",
    )
    sub = parser.add_subparsers(dest="command")

    p_an = sub.add_parser("analyze", help="analyze a savegame (default command)")
    p_an.add_argument("--save", type=Path, help="savegame file (default: most recent)")
    p_an.add_argument("--x4-user-dir", type=Path, help="X4 user dir with <id>/save/")
    p_an.add_argument("--output-dir", type=Path, help="dashboard output directory")
    p_an.add_argument("--spoilers-hide", action="store_true",
                      help="hide undiscovered sectors/objects and resource details")
    p_an.add_argument("--history-hours", type=float, default=3.0,
                      help="history window for sunbursts/tables (default: 3)")
    p_an.add_argument("--no-browser", action="store_true",
                      help="do not open the dashboard in a browser")
    _add_common_args(p_an)

    p_ex = sub.add_parser(
        "extract-gamedata",
        help="regenerate reference CSVs from the installed game (base + DLC)",
    )
    p_ex.add_argument("--game-dir", type=Path, help="X4 installation directory")
    p_ex.add_argument("--include-mods", action="store_true",
                      help="also scan non-DLC extensions for added ships")
    _add_common_args(p_ex)

    p_gd = sub.add_parser(
        "gamedata-dashboard",
        help="build the game-data analysis dashboard (weapon-mod comparison)",
    )
    p_gd.add_argument("--game-dir", type=Path, help="X4 installation directory")
    p_gd.add_argument("--output-dir", type=Path, help="dashboard output directory")
    _add_common_args(p_gd)

    p_fi = sub.add_parser(
        "find",
        help="locate objects in a savegame (default: the Erlking data vaults)",
    )
    p_fi.add_argument("--save", type=Path, help="savegame file (default: most recent)")
    p_fi.add_argument("--x4-user-dir", type=Path, help="X4 user dir with <id>/save/")
    p_fi.add_argument("--macro", help="macro regex to search for "
                                      "(default: landmarks_erlking_vault_*)")
    _add_common_args(p_fi)

    # default to `analyze` when no subcommand given
    if argv is None:
        argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        argv = ["analyze", *argv]
    args = parser.parse_args(argv)

    cfg = Config()
    if args.data_dir:
        cfg.data_dir = args.data_dir

    if args.command == "extract-gamedata":
        from .gamedata.extract import extract_gamedata

        if args.game_dir:
            cfg.game_dir = args.game_dir
        return extract_gamedata(cfg, include_mods=args.include_mods)

    if args.command == "gamedata-dashboard":
        from .viz.weaponmods import build_gamedata_dashboard

        if args.game_dir:
            cfg.game_dir = args.game_dir
        if args.output_dir:
            cfg.output_dir = args.output_dir
        return build_gamedata_dashboard(cfg)

    if args.command == "find":
        from .save.find import run_find

        if args.save:
            cfg.savegame_override = args.save
        if args.x4_user_dir:
            cfg.x4_user_dir = args.x4_user_dir
        return run_find(cfg, args.macro)

    if args.save:
        cfg.savegame_override = args.save
    if args.x4_user_dir:
        cfg.x4_user_dir = args.x4_user_dir
    if args.output_dir:
        cfg.output_dir = args.output_dir
    cfg.spoilers_hide = args.spoilers_hide
    cfg.history_hours = args.history_hours
    cfg.open_browser = not args.no_browser

    from .analyze import run_analysis

    return run_analysis(cfg)


if __name__ == "__main__":
    sys.exit(main())
