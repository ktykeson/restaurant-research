#!/usr/bin/env bash
# Builds the macOS .app and packages it into a .dmg.
#
# Prereqs (one-time):
#   brew install create-dmg
#   pip install -r requirements.txt pyinstaller
#
# Outputs:
#   dist/RestaurantResearch.app
#   dist/RestaurantResearch.dmg
set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="RestaurantResearch"
APP_BUNDLE="dist/${APP_NAME}.app"
DMG_PATH="dist/${APP_NAME}.dmg"
VOLNAME="Restaurant Research"

echo "==> Checking logo"
# If you drop a PNG at assets/logo.png, the build auto-converts it to
# app.icns (the macOS multi-resolution icon). Regenerate only when the
# source PNG is newer than the existing .icns — keeps incremental builds fast.
LOGO_SRC="assets/logo.png"
ICNS_OUT="app.icns"
if [[ -f "$LOGO_SRC" ]]; then
    if [[ ! -f "$ICNS_OUT" || "$LOGO_SRC" -nt "$ICNS_OUT" ]]; then
        echo "    regenerating $ICNS_OUT from $LOGO_SRC"
        ./scripts/make_icns.sh "$LOGO_SRC"
    else
        echo "    $ICNS_OUT is up to date"
    fi
else
    echo "    no $LOGO_SRC found — using PyInstaller's default icon"
fi

echo "==> Cleaning previous build"
rm -rf build dist

echo "==> Stripping xattrs from source tree"
# Finder/iCloud/backup operations leave resource-fork and FinderInfo xattrs on
# random files. codesign refuses to sign anything with those attached, so we
# clear them on the source dirs PyInstaller will copy into the bundle.
for d in templates static data/boundaries; do
    [[ -d "$d" ]] && xattr -cr "$d" || true
done
xattr -c VERSION 2>/dev/null || true

echo "==> Running PyInstaller"
# PyInstaller attempts its own ad-hoc codesign of the BUNDLE at the end; that
# can emit a "You will need to sign the bundle manually!" warning. Safe to
# ignore — we sign properly below.
# We already `rm -rf build dist` above; do NOT pass --clean, as it removes
# the workpath subdir and on some Python+PyInstaller combos it then fails to
# recreate it before writing base_library.zip into it.
mkdir -p build
pyinstaller "${APP_NAME}.spec" --noconfirm

if [[ ! -d "$APP_BUNDLE" ]]; then
    echo "Build failed: $APP_BUNDLE not produced." >&2
    exit 1
fi

echo "==> Ad-hoc codesigning + DMG (entirely in /tmp to avoid com.apple.provenance)"
# macOS 14+ attaches com.apple.provenance to files in tracked directories
# (Desktop, Documents, iCloud) the moment they touch the filesystem, and
# codesign rejects bundles that carry it ("resource fork, Finder info, or
# similar detritus not allowed"). /tmp is not tracked, so we sign AND build
# the DMG entirely in /tmp, then move only the resulting .dmg back to dist/.
SIGN_STAGE=$(mktemp -d /tmp/rr-sign-XXXXXX)
STAGED_APP="${SIGN_STAGE}/${APP_NAME}.app"
STAGED_DMG="${SIGN_STAGE}/${APP_NAME}.dmg"

find "$APP_BUNDLE" -name ".DS_Store" -delete 2>/dev/null || true
ditto --noextattr --noacl --norsrc "$APP_BUNDLE" "$STAGED_APP"

# Sign inner dylibs/.so first so --deep won't miss anything embedded deep.
find "$STAGED_APP/Contents" -type f \( -name "*.dylib" -o -name "*.so" \) \
    -exec codesign --force --sign - --options runtime \
        --entitlements entitlements.plist {} \; 2>/dev/null || true

# Sign the bundle.
codesign --force --deep --sign - --options runtime --timestamp=none \
    --entitlements entitlements.plist "$STAGED_APP"

echo "==> Verifying signature (in /tmp)"
codesign --verify --deep --strict "$STAGED_APP"

echo "==> Building DMG (also in /tmp)"
if command -v create-dmg >/dev/null 2>&1; then
    extra_args=()
    [[ -f "app.icns"          ]] && extra_args+=(--volicon "$(pwd)/app.icns")
    [[ -f "assets/dmg-bg.png" ]] && extra_args+=(--background "$(pwd)/assets/dmg-bg.png")
    create-dmg \
        --volname "$VOLNAME" \
        --window-size 540 380 \
        --icon-size 96 \
        --icon "${APP_NAME}.app" 140 190 \
        --app-drop-link 400 190 \
        --no-internet-enable \
        "${extra_args[@]}" \
        "$STAGED_DMG" "$STAGED_APP"
else
    echo "create-dmg not installed; falling back to raw hdiutil."
    hdiutil create -volname "$VOLNAME" -srcfolder "$STAGED_APP" \
        -ov -format UDZO "$STAGED_DMG"
fi

# Move the produced artifacts to dist/.
mkdir -p dist
rm -f "$DMG_PATH"
mv "$STAGED_DMG" "$DMG_PATH"
# Also keep an unsigned-on-disk copy of the .app for local debugging.
rm -rf "$APP_BUNDLE"
ditto "$STAGED_APP" "$APP_BUNDLE"
rm -rf "$SIGN_STAGE"

echo
echo "Done."
echo "  App:  $APP_BUNDLE  (codesign verify may fail here due to"
echo "                      com.apple.provenance reattaching; the copy"
echo "                      INSIDE the DMG is the signed one to ship.)"
echo "  DMG:  $DMG_PATH"
