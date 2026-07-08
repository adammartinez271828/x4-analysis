"""PyInstaller entry point (absolute imports only — PyInstaller analyzes
this as a plain script, so relative imports would fail)."""

import multiprocessing
import sys
import traceback

from x4analyzer.cli import main


def _console_vanishes_on_exit() -> bool:
    """True when this process is the only one attached to its console —
    the Windows double-click case, where the window closes the instant we
    exit and the user can't read the final output (or a traceback)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        procs = (ctypes.c_uint * 2)()
        attached = ctypes.windll.kernel32.GetConsoleProcessList(procs, 2)
        return attached == 1
    except Exception:
        return False


if __name__ == "__main__":
    multiprocessing.freeze_support()
    pause = _console_vanishes_on_exit()
    try:
        code = main()
    except SystemExit as exc:  # argparse exits this way on bad arguments
        code = exc.code if exc.code is not None else 0
    except Exception:
        traceback.print_exc()
        code = 1
    if pause:
        try:
            input("\nDone - press Enter to close this window...")
        except EOFError:
            pass
    sys.exit(code)
