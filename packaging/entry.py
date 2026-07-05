"""PyInstaller entry point (absolute imports only — PyInstaller analyzes
this as a plain script, so relative imports would fail)."""

import multiprocessing
import sys

from x4analyzer.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
