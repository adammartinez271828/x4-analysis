"""Generate the Windows VERSIONINFO file for the PyInstaller build.

Defender's ML heuristics score an anonymous binary (no company, product,
or version resource) as riskier, which contributed to the 1.4.0 EXE being
flagged as Trojan:Win32/Sabsik.TE.A!ml. Generated at build time so the
resource always matches the package version.

Usage: python packaging/make_version_info.py [output-path]
"""

import re
import sys

from x4analyzer import __version__

TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vers},
    prodvers={vers},
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        "040904B0",
        [
          StringStruct("CompanyName", "Adam Martinez"),
          StringStruct("FileDescription", "X4: Foundations savegame analyzer"),
          StringStruct("FileVersion", "{version}"),
          StringStruct("InternalName", "x4-analyzer"),
          StringStruct("LegalCopyright", "Copyright (c) Adam Martinez. GPL-3.0-only."),
          StringStruct("OriginalFilename", "x4-analyzer.exe"),
          StringStruct("ProductName", "x4-analyzer"),
          StringStruct("ProductVersion", "{version}"),
        ],
      )
    ]),
    VarFileInfo([VarStruct("Translation", [1033, 1200])]),
  ],
)
"""


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "version_info.txt"
    # VERSIONINFO wants exactly four integers; tolerate suffixes like "1.5.0rc1".
    nums = [int(m.group()) for p in __version__.split(".") if (m := re.match(r"\d+", p))]
    vers = tuple((nums + [0, 0, 0, 0])[:4])
    text = TEMPLATE.format(vers=vers, version=__version__)
    compile(text, out, "eval")  # PyInstaller evals this file; fail here, not on the runner
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"Wrote {out} for version {__version__} -> {vers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
