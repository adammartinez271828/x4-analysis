"""Allow `python -m x4analyzer`."""

import sys

from x4analyzer.cli import main

if __name__ == "__main__":
    sys.exit(main())
