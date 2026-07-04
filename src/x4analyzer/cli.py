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
    p_an.add_argument("--force-refresh", action="store_true",
                      help="accepted for compatibility with the R version; "
                           "sector resources are recomputed on every run")
    p_an.add_argument("--no-cache-compress", action="store_true",
                      help="keep cache files as plain CSV")
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
        from .gamedata import extract_gamedata

        if args.game_dir:
            cfg.game_dir = args.game_dir
        return extract_gamedata(cfg, include_mods=args.include_mods)

    if args.save:
        cfg.savegame_override = args.save
    if args.x4_user_dir:
        cfg.x4_user_dir = args.x4_user_dir
    if args.output_dir:
        cfg.output_dir = args.output_dir
    cfg.spoilers_hide = args.spoilers_hide
    cfg.cache_force_refresh = args.force_refresh
    cfg.cache_compress = not args.no_cache_compress
    cfg.history_hours = args.history_hours
    cfg.open_browser = not args.no_browser

    from .analyze import run_analysis

    return run_analysis(cfg)


if __name__ == "__main__":
    sys.exit(main())
