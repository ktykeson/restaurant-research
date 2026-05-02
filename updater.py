"""Silent background updater via GitHub Releases.

Flow:
    1. On launch, `check_and_stage_async()` is fired in a daemon thread.
    2. It asks api.github.com for the latest release's tag.
    3. If that tag is newer than the bundled VERSION, it downloads the .dmg
       asset, mounts it, copies the inner .app into
       `<Application Support>/pending_update/RestaurantResearch.app`,
       detaches the DMG, and strips the quarantine xattr.
    4. On next launch, `launcher.py` sees the staged app and atomically
       replaces `/Applications/RestaurantResearch.app` with it, then re-execs.

All errors are swallowed: the updater must never break a working launch.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

import httpx
from packaging.version import InvalidVersion, Version

from paths import resource_path, user_data_path

# ---------------------------------------------------------------------------
# IMPORTANT: set these to your actual GitHub repo before publishing a release.
# Owner / repo of the public GitHub repo that hosts releases.
GITHUB_OWNER = "ktykeson"
GITHUB_REPO = "restaurant-research"
# Name of the .dmg asset attached to each release. Must match build.sh.
DMG_ASSET_NAME = "RestaurantResearch.dmg"
# Name of the .app inside the DMG. Must match the PyInstaller BUNDLE name.
APP_BUNDLE_NAME = "RestaurantResearch.app"
# ---------------------------------------------------------------------------

API_LATEST = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
PENDING_DIR = "pending_update"
UPDATE_MARKER = "last_updated_to.txt"


def current_version() -> Optional[str]:
    try:
        return (resource_path("VERSION")).read_text().strip()
    except Exception:
        return None


def _parse(v: str) -> Optional[Version]:
    try:
        return Version(v.lstrip("v"))
    except (InvalidVersion, TypeError):
        return None


def _fetch_latest_release() -> Optional[dict]:
    try:
        r = httpx.get(API_LATEST, timeout=15.0, follow_redirects=True,
                      headers={"Accept": "application/vnd.github+json"})
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _find_dmg_asset(release: dict) -> Optional[dict]:
    for asset in release.get("assets", []) or []:
        if asset.get("name") == DMG_ASSET_NAME:
            return asset
    return None


def _download(url: str, dest: Path) -> bool:
    try:
        with httpx.stream("GET", url, timeout=600.0, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=1024 * 64):
                    f.write(chunk)
        return True
    except Exception:
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def _mount_dmg(dmg: Path) -> Optional[Path]:
    """Mount the DMG at a fresh temp dir. Returns the mount point or None."""
    mount = Path(tempfile.mkdtemp(prefix="rr-dmg-"))
    try:
        subprocess.run(
            ["hdiutil", "attach", "-nobrowse", "-noautoopen", "-quiet",
             "-mountpoint", str(mount), str(dmg)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        shutil.rmtree(mount, ignore_errors=True)
        return None
    if (mount / APP_BUNDLE_NAME).exists():
        return mount
    _detach(mount)
    return None


def _detach(mount: Path) -> None:
    try:
        subprocess.run(["hdiutil", "detach", "-quiet", str(mount)],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _clear_quarantine(p: Path) -> None:
    try:
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(p)],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _stage(app_src: Path) -> Path:
    pending = user_data_path(PENDING_DIR)
    target = pending / APP_BUNDLE_NAME
    # Remove any half-staged previous attempt.
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(app_src, target, symlinks=True)
    _clear_quarantine(target)
    return target


def _check_and_stage() -> Optional[str]:
    """Runs the full check-download-stage pipeline. Returns staged version or None."""
    if GITHUB_OWNER.startswith("REPLACE_ME") or GITHUB_REPO.startswith("REPLACE_ME"):
        return None  # Updater not configured yet.
    if not getattr(sys, "frozen", False):
        return None  # Only auto-update the packaged app.
    if sys.platform != "darwin":
        return None

    current = _parse(current_version() or "")
    if current is None:
        return None

    release = _fetch_latest_release()
    if not release:
        return None

    tag = (release.get("tag_name") or "").strip()
    latest = _parse(tag)
    if latest is None or latest <= current:
        return None

    asset = _find_dmg_asset(release)
    if not asset or not asset.get("browser_download_url"):
        return None

    with tempfile.TemporaryDirectory(prefix="rr-update-") as td:
        dmg = Path(td) / DMG_ASSET_NAME
        if not _download(asset["browser_download_url"], dmg):
            return None
        mount = _mount_dmg(dmg)
        if mount is None:
            return None
        try:
            app_src = mount / APP_BUNDLE_NAME
            if not app_src.exists():
                return None
            _stage(app_src)
            (user_data_path(PENDING_DIR) / "version.txt").write_text(str(latest))
            return str(latest)
        finally:
            _detach(mount)


def check_and_stage_async() -> None:
    """Fire-and-forget check. Safe to call on every launch."""
    t = threading.Thread(target=_check_and_stage, name="updater", daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Pending-update applier (called by launcher before starting the server).

def pending_update_info() -> Optional[tuple[Path, str]]:
    pending = user_data_path(PENDING_DIR) / APP_BUNDLE_NAME
    ver_file = user_data_path(PENDING_DIR) / "version.txt"
    if not pending.exists():
        return None
    version = ver_file.read_text().strip() if ver_file.exists() else ""
    return pending, version


def apply_pending_update(target_bundle: Path) -> Optional[Path]:
    """Copy the staged .app over `target_bundle`. Returns the new bundle path or None."""
    info = pending_update_info()
    if info is None:
        return None
    staged, version = info

    # Replace atomically where possible: rename current to .old, move staged in, delete .old.
    parent = target_bundle.parent
    old_bak = parent / (target_bundle.name + ".old")
    try:
        if old_bak.exists():
            shutil.rmtree(old_bak, ignore_errors=True)
        if target_bundle.exists():
            target_bundle.rename(old_bak)
        shutil.copytree(staged, target_bundle, symlinks=True)
        _clear_quarantine(target_bundle)
    except Exception:
        # Roll back if possible.
        try:
            if not target_bundle.exists() and old_bak.exists():
                old_bak.rename(target_bundle)
        except Exception:
            pass
        return None

    # Clean up staged + backup.
    try:
        shutil.rmtree(staged.parent, ignore_errors=True)
    except Exception:
        pass
    try:
        shutil.rmtree(old_bak, ignore_errors=True)
    except Exception:
        pass

    # Write a marker so the UI can show a one-time "Updated to X" toast.
    try:
        (user_data_path() / UPDATE_MARKER).write_text(version)
    except Exception:
        pass
    return target_bundle


def pop_update_marker() -> Optional[str]:
    """Read and delete the 'last updated to' marker, if present."""
    marker = user_data_path() / UPDATE_MARKER
    if not marker.exists():
        return None
    try:
        v = marker.read_text().strip()
        marker.unlink(missing_ok=True)
        return v or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# User-triggered apply: called from the in-app "Update now" banner.

def schedule_relaunch() -> bool:
    """Schedule the running app to quit and relaunch via the macOS `open`
    command. The next launch picks up the staged update via the launcher's
    pending-update applier — no in-process bundle replacement, which is
    unsafe while Python imports are mid-flight.

    Returns True if the relaunch was scheduled, False otherwise.
    """
    if not getattr(sys, "frozen", False) or sys.platform != "darwin":
        return False

    # Locate the bundle we're running from.
    exe = Path(sys.executable).resolve()
    try:
        bundle = next(p for p in exe.parents if p.suffix == ".app")
    except StopIteration:
        return False

    # Detached helper: wait for parent to exit, then re-open the bundle.
    # `open -n -a` opens a fresh instance; `nohup` + `setsid`-equivalent via
    # start_new_session detaches from this process group so killing us
    # doesn't kill the helper.
    try:
        import subprocess
        subprocess.Popen(
            ["/bin/sh", "-c", f"sleep 1.5 && /usr/bin/open -n -a {str(bundle)!r}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        return False

    # Tell pywebview to close the window. The Python process exits when the
    # cocoa runloop returns; the helper above then re-opens us.
    try:
        import webview
        for w in list(webview.windows):
            try:
                w.destroy()
            except Exception:
                pass
    except Exception:
        # Hard fallback if pywebview isn't importable here.
        import os, threading
        threading.Timer(0.3, lambda: os._exit(0)).start()
    return True
