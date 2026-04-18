# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for RestaurantResearch.app (macOS arm64)."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None
ROOT = Path(SPECPATH).resolve()


def _read_version() -> str:
    try:
        return (ROOT / "VERSION").read_text().strip()
    except Exception:
        return "0.0.0"


VERSION = _read_version()

# --- shapely / pyproj: collect binaries + data ---------------------------------
shapely_datas, shapely_binaries, shapely_hiddenimports = collect_all("shapely")
pyproj_datas, pyproj_binaries, pyproj_hiddenimports = collect_all("pyproj")

# --- App-level data files (bundled read-only) ---------------------------------
app_datas = [
    ("templates", "templates"),
    ("static", "static"),
    ("data/boundaries", "data/boundaries"),
    ("VERSION", "."),
]

hiddenimports = [
    # Keychain backend auto-discovery fails in frozen builds; name it explicitly.
    "keyring.backends.macOS",
    "keyring.backends.chainer",
    # pywebview macOS backend.
    "webview.platforms.cocoa",
    # waitress (only imported dynamically inside launcher.py).
    "waitress",
] + shapely_hiddenimports + pyproj_hiddenimports


a = Analysis(
    ["launcher.py"],
    pathex=[str(ROOT)],
    binaries=shapely_binaries + pyproj_binaries,
    datas=app_datas + shapely_datas + pyproj_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["rthook_proj.py"],
    excludes=["tkinter", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RestaurantResearch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="RestaurantResearch",
)

app = BUNDLE(
    coll,
    name="RestaurantResearch.app",
    icon=str(ROOT / "app.icns") if (ROOT / "app.icns").exists() else None,
    bundle_identifier="com.alpstudios.restaurantresearch",
    version=VERSION,
    info_plist={
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "CFBundleName": "Restaurant Research",
        "CFBundleDisplayName": "Restaurant Research",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.business",
        "NSHumanReadableCopyright": f"© {__import__('datetime').date.today().year} alpstudios",
    },
)
