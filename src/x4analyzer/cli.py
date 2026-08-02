"""Command-line entry point: `x4-analyzer [analyze|extract-gamedata]`."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__
from .config import Config


def log(*parts: object) -> None:
    """Timestamped progress message, matching the R script's style."""
    print(time.strftime("%H:%M:%S"), *parts, file=sys.stderr, flush=True)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-dir", type=Path, help="reference CSV / cache directory")
    # On every subparser as well as top-level, so the flag works wherever it
    # lands — including after the analyze-shim rewrite below. The literal
    # prefix (not %(prog)s) keeps subparsers from printing "x4-analyzer analyze".
    parser.add_argument("--version", action="version",
                        version=f"x4-analyzer {__version__}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="x4-analyzer",
        description="Analyze an X4: Foundations savegame into an HTML dashboard. "
                    "With no subcommand, `analyze` is run.",
    )
    parser.add_argument("--version", action="version",
                        version=f"x4-analyzer {__version__}")
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
    p_ex.add_argument("--game-dir", type=Path,
                      help="X4 installation directory (default: detected via "
                           "$X4_GAME_DIR or the Steam libraries)")
    p_ex.add_argument("--include-mods", action="store_true",
                      help="also scan non-DLC extensions for added ships")
    _add_common_args(p_ex)

    p_gd = sub.add_parser(
        "gamedata-dashboard",
        help="build the game-data analysis dashboard (weapon-mod comparison)",
    )
    p_gd.add_argument("--game-dir", type=Path,
                      help="X4 installation directory (default: detected via "
                           "$X4_GAME_DIR or the Steam libraries)")
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

    p_se = sub.add_parser(
        "seed-trends",
        help="seed the trend layer from archived saves "
             "(chronological import; world state and event history "
             "stay at the newest save)",
    )
    p_se.add_argument("saves", nargs="*", type=Path,
                      help="save files (default: every save in the "
                           "savegame dir)")
    p_se.add_argument("--x4-user-dir", type=Path,
                      help="X4 user dir with <id>/save/")
    _add_common_args(p_se)

    # default to `analyze` when no subcommand given — except for the flags
    # that mean "tell me about the CLI itself": help must reach the top-level
    # parser (the only place the subcommands are listed; analyze's own help
    # stays at `x4-analyzer analyze -h`).
    if argv is None:
        argv = sys.argv[1:]
    if not argv or (argv[0].startswith("-")
                    and argv[0] not in ("-h", "--help", "--version")):
        argv = ["analyze", *argv]
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (FileNotFoundError, RuntimeError) as exc:
        # Path/discovery failures are user errors, not bugs: report them
        # the way the rest of the pipeline reports problems.
        log("ERROR:", exc)
        return 1


def _run(args: argparse.Namespace) -> int:
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

    if args.command == "seed-trends":
        from .analyze import run_seed

        if args.x4_user_dir:
            cfg.x4_user_dir = args.x4_user_dir
        return run_seed(cfg, args.saves)

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
