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
pyinstaller "${APP_NAME}.spec" --noconfirm --clean

if [[ ! -d "$APP_BUNDLE" ]]; then
    echo "Build failed: $APP_BUNDLE not produced." >&2
    exit 1
fi

echo "==> Ad-hoc codesigning (via /tmp to avoid com.apple.provenance detritus)"
# macOS 14+ attaches com.apple.provenance to files in tracked directories
# (Desktop, Documents, iCloud), and codesign rejects bundles that carry it
# ("resource fork, Finder information, or similar detritus not allowed").
# /tmp is not tracked, so we stage the bundle there, sign it, and copy the
# signed bundle back. The signature survives the round-trip.
SIGN_STAGE=$(mktemp -d /tmp/rr-sign-XXXXXX)
STAGED_APP="${SIGN_STAGE}/${APP_NAME}.app"

find "$APP_BUNDLE" -name ".DS_Store" -delete 2>/dev/null || true
ditto --noextattr --noacl --norsrc "$APP_BUNDLE" "$STAGED_APP"

# Sign inner dylibs/.so first so --deep won't miss anything embedded deep.
find "$STAGED_APP/Contents" -type f \( -name "*.dylib" -o -name "*.so" \) \
    -exec codesign --force --sign - --options runtime \
        --entitlements entitlements.plist {} \; 2>/dev/null || true

# Sign the bundle.
codesign --force --deep --sign - --options runtime --timestamp=none \
    --entitlements entitlements.plist "$STAGED_APP"

echo "==> Verifying signature"
codesign --verify --deep --strict "$STAGED_APP"

# Replace the dist/ bundle with the signed copy.
rm -rf "$APP_BUNDLE"
ditto "$STAGED_APP" "$APP_BUNDLE"
rm -rf "$SIGN_STAGE"

# Re-verify in the final location.
codesign --verify --deep --strict "$APP_BUNDLE" || true

echo "==> Building DMG"
rm -f "$DMG_PATH"
if command -v create-dmg >/dev/null 2>&1; then
    # Optional artwork: if present at project root we use it, otherwise the
    # DMG still builds cleanly with plain defaults.
    extra_args=()
    [[ -f "app.icns"          ]] && extra_args+=(--volicon "app.icns")
    [[ -f "assets/dmg-bg.png" ]] && extra_args+=(--background "assets/dmg-bg.png")

    create-dmg \
        --volname "$VOLNAME" \
        --window-size 540 380 \
        --icon-size 96 \
        --icon "${APP_NAME}.app" 140 190 \
        --app-drop-link 400 190 \
        --no-internet-enable \
        "${extra_args[@]}" \
        "$DMG_PATH" "$APP_BUNDLE"
else
    echo "create-dmg not installed; falling back to raw hdiutil."
    hdiutil create -volname "$VOLNAME" -srcfolder "$APP_BUNDLE" \
        -ov -format UDZO "$DMG_PATH"
fi

echo
echo "Done."
echo "  App:  $APP_BUNDLE"
echo "  DMG:  $DMG_PATH"
