"""Entry point for the packaged macOS .app.

Responsibilities, in order:

  1. If a staged update exists in Application Support, apply it by replacing
     /Applications/RestaurantResearch.app, then re-exec into it.
  2. Initialize SQLite + seed Swiss cantons (idempotent).
  3. Pick a free port on 127.0.0.1.
  4. Start the Waitress WSGI server in a daemon thread.
  5. Wait for /healthz to return 200.
  6. Kick off the silent updater in a background thread.
  7. Open a pywebview window pointing at http://127.0.0.1:<port>.
  8. When the window closes, the process exits (daemon threads are killed).

In dev (`python launcher.py`), steps 1 and updater are no-ops.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

import httpx

import updater
from paths import is_frozen


APP_BUNDLE_NAME = "RestaurantResearch.app"
APPLICATIONS_DIR = Path("/Applications")
WINDOW_TITLE = "Restaurant Research"


def _apply_pending_update_and_reexec() -> None:
    """If a staged update exists, replace the /Applications bundle and re-exec."""
    if not is_frozen() or sys.platform != "darwin":
        return
    if updater.pending_update_info() is None:
        return

    # Find the currently-running .app bundle. In a PyInstaller BUNDLE build,
    # sys.executable is .../RestaurantResearch.app/Contents/MacOS/RestaurantResearch.
    exe = Path(sys.executable).resolve()
    try:
        # Walk up to the .app dir.
        bundle = next(p for p in exe.parents if p.suffix == ".app")
    except StopIteration:
        return

    # Only auto-apply when launched from /Applications (otherwise the user may
    # be test-running a build from Desktop and we don't want to silently
    # replace the wrong bundle).
    try:
        bundle.relative_to(APPLICATIONS_DIR)
    except ValueError:
        return

    new_bundle = updater.apply_pending_update(bundle)
    if not new_bundle:
        return

    # Re-exec into the replaced bundle. The old Mach-O file is kept alive by
    # the kernel even after we overwrote its directory entry, so this works.
    new_exe = new_bundle / "Contents" / "MacOS" / bundle.stem
    if new_exe.exists():
        try:
            os.execv(str(new_exe), [str(new_exe)])
        except Exception:
            # Fall through to running the old binary — user gets the update on
            # the *next* launch instead.
            return


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(port: int) -> None:
    # Import Flask app here so cache.init_db() and seeding happen after
    # writable dirs exist.
    from search import cache
    from search import regions as regions_mod
    cache.init_db()
    regions_mod.seed_swiss_cantons()

    from app import app
    from waitress import serve

    def run():
        # waitress handles SSE fine; threads default is 4 which is plenty.
        serve(app, host="127.0.0.1", port=port, threads=8, _quiet=True)

    t = threading.Thread(target=run, name="waitress", daemon=True)
    t.start()


def _wait_for_healthz(port: int, timeout_s: float = 10.0) -> bool:
    deadline = time.time() + timeout_s
    url = f"http://127.0.0.1:{port}/healthz"
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def main() -> int:
    # 1. Apply staged update if present. This function may os.execv — if it
    #    returns, there was nothing to do (or it failed gracefully).
    _apply_pending_update_and_reexec()

    # 2–4. Start server.
    port = _pick_free_port()
    _start_server(port)

    # 5. Wait for readiness.
    if not _wait_for_healthz(port):
        # Still open the window — the user will see a Flask error and can retry.
        pass

    # 6. Background update check (no-op in dev).
    updater.check_and_stage_async()

    # 7. Open native window. pywebview's webview.start() *must* run on the
    #    main thread on macOS (cocoa requirement).
    import webview
    window = webview.create_window(
        WINDOW_TITLE,
        url=f"http://127.0.0.1:{port}/",
        width=1280,
        height=820,
        resizable=True,
        confirm_close=False,
    )
    # gui='cocoa' is the default on macOS; pass explicitly for clarity.
    webview.start(gui="cocoa")
    return 0


if __name__ == "__main__":
    sys.exit(main())
