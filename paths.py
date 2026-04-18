"""Path helpers that work identically under `python launcher.py` and inside a
PyInstaller-bundled .app.

- `resource_path(rel)` → read-only bundled assets (templates, static, geojson).
  Under PyInstaller: `sys._MEIPASS/<rel>`. In dev: project-root relative.
- `user_data_path(rel)` → writable per-user data. Always
  `~/Library/Application Support/RestaurantResearch/<rel>` on macOS
  (resolved via platformdirs so Linux/Windows also work if we ever need them).
  The parent directory is created on first access.
"""
from __future__ import annotations

import sys
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "RestaurantResearch"
APP_AUTHOR = "alpstudios"

_PROJECT_ROOT = Path(__file__).resolve().parent


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_path(rel: str = "") -> Path:
    """Absolute path to a bundled read-only resource."""
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", _PROJECT_ROOT))
    else:
        base = _PROJECT_ROOT
    return base / rel if rel else base


def user_data_path(rel: str = "") -> Path:
    """Absolute path to a writable per-user data file/dir. Creates parents on demand."""
    base = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    base.mkdir(parents=True, exist_ok=True)
    if not rel:
        return base
    target = base / rel
    # If caller asked for a path that looks like a file (has a suffix), create
    # the parent dir; otherwise treat `rel` as a directory itself.
    if target.suffix:
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        target.mkdir(parents=True, exist_ok=True)
    return target


def writable_path(rel: str) -> Path:
    """Writable location for cache / runs / pending_update.

    - Frozen: Application Support (the app bundle is read-only).
    - Dev: project-root `data/<rel>` so `python launcher.py` keeps using the
      existing cache.sqlite the developer has been building up.
    """
    if is_frozen():
        return user_data_path(rel)
    target = _PROJECT_ROOT / "data" / rel
    if target.suffix:
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        target.mkdir(parents=True, exist_ok=True)
    return target
