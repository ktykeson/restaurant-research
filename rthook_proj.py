"""PyInstaller runtime hook: point pyproj at its bundled PROJ data.

PyInstaller copies pyproj's `proj_dir/share/proj` next to the module but the
env var PROJ_LIB is required for pyproj to find it on some macOS builds.
"""
import os
import sys

if getattr(sys, "frozen", False) and sys.platform == "darwin":
    candidates = [
        os.path.join(sys._MEIPASS, "pyproj", "proj_dir", "share", "proj"),
        os.path.join(sys._MEIPASS, "pyproj", "proj", "share", "proj"),
        os.path.join(sys._MEIPASS, "pyproj", "share", "proj"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            os.environ.setdefault("PROJ_LIB", c)
            os.environ.setdefault("PROJ_DATA", c)
            break
