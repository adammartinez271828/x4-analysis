x4-analyzer — Windows build
===========================

EXTRACT THIS ZIP COMPLETELY BEFORE RUNNING.

Double-clicking x4-analyzer.exe from inside the zip preview window fails
with "Failed to load Python DLL": Windows extracts only the EXE, without
the _internal folder it needs.

1. Right-click the zip -> Extract All...
2. Open the extracted x4-analyzer folder.
3. Double-click x4-analyzer.exe. A console window shows progress, and the
   dashboard opens in your browser.

SmartScreen may warn because the binary is unsigned: choose "More info"
-> "Run anyway".

Your newest savegame is found automatically (Documents\Egosoft\X4); run
from a terminal with --save <file> or --x4-user-dir <dir> otherwise. The
dashboard is written to output\ in the current directory.
