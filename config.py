"""Keychain-backed storage for the Google Places API key.

Why not .env or a plaintext file: a file on disk is readable by any process
running as the user (and shows up in Time Machine backups). macOS Keychain
encrypts the value at rest and requires user authorization to export.

Under PyInstaller the automatic keyring backend discovery silently picks the
null backend ("no suitable keyring"), so we pin the macOS backend explicitly.

In dev (non-frozen) we fall back to GOOGLE_MAPS_API_KEY in the environment /
.env so the existing `python app.py` workflow still works with zero friction.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Optional

SERVICE = "com.alpstudios.restaurantresearch"
ACCOUNT = "GOOGLE_MAPS_API_KEY"

_CACHE: dict = {"value": None, "at": 0.0}
_CACHE_TTL_S = 60.0


def _keyring():
    """Import keyring lazily and pin the macOS backend."""
    import keyring  # local import so app can start without keyring in dev
    if sys.platform == "darwin":
        try:
            from keyring.backends.macOS import Keyring as MacKeyring
            keyring.set_keyring(MacKeyring())
        except Exception:
            # Auto-discovery as last resort (dev on non-darwin, etc.).
            pass
    return keyring


def get_api_key() -> Optional[str]:
    """Return the current API key, or None if unset.

    Caches for 60s so per-request lookups are cheap. A successful `set_api_key`
    invalidates the cache so changes take effect immediately.
    """
    now = time.time()
    if _CACHE["value"] is not None and (now - _CACHE["at"]) < _CACHE_TTL_S:
        return _CACHE["value"]

    value: Optional[str] = None
    try:
        value = _keyring().get_password(SERVICE, ACCOUNT)
    except Exception:
        value = None

    # Dev fallback — only when no key in keyring and the process isn't frozen.
    if not value and not getattr(sys, "frozen", False):
        value = os.environ.get(ACCOUNT) or None

    _CACHE["value"] = value or None
    _CACHE["at"] = now
    return _CACHE["value"]


def set_api_key(value: str) -> None:
    """Store the API key in macOS Keychain. Empty string clears it."""
    value = (value or "").strip()
    kr = _keyring()
    if value:
        kr.set_password(SERVICE, ACCOUNT, value)
    else:
        try:
            kr.delete_password(SERVICE, ACCOUNT)
        except Exception:
            pass
    _CACHE["value"] = value or None
    _CACHE["at"] = time.time()


def has_api_key() -> bool:
    return bool(get_api_key())


def masked_key() -> str:
    """Return a safe representation for display: •••••…last4."""
    k = get_api_key() or ""
    if len(k) <= 4:
        return "•" * len(k)
    return "•" * 8 + "…" + k[-4:]
