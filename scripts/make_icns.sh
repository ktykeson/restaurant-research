#!/usr/bin/env bash
# Convert a 1024x1024 PNG into app.icns (multi-resolution Apple icon).
#
# Usage:
#   ./scripts/make_icns.sh path/to/logo.png
#
# Output:
#   app.icns at project root (PyInstaller auto-picks it up).
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <logo.png>" >&2
    exit 1
fi

SRC="$1"
if [[ ! -f "$SRC" ]]; then
    echo "Source not found: $SRC" >&2
    exit 1
fi

cd "$(dirname "$0")/.."

# Verify at least 1024x1024 — smaller sources produce blurry icons at Retina sizes.
dims=$(sips -g pixelWidth -g pixelHeight "$SRC" 2>/dev/null | awk '/pixel(Width|Height)/ {print $2}' | tr '\n' 'x' | sed 's/x$//')
w=${dims%x*}; h=${dims#*x}
if [[ -z "$w" || -z "$h" ]] || (( w < 1024 || h < 1024 )); then
    echo "Warning: source is ${dims}. 1024x1024 or larger is recommended for sharp Retina icons." >&2
fi

ICONSET=app.iconset
rm -rf "$ICONSET" app.icns
mkdir "$ICONSET"

# Apple-mandated sizes (names matter — iconutil validates them).
sips -z   16   16 "$SRC" --out "$ICONSET/icon_16x16.png"       >/dev/null
sips -z   32   32 "$SRC" --out "$ICONSET/icon_16x16@2x.png"    >/dev/null
sips -z   32   32 "$SRC" --out "$ICONSET/icon_32x32.png"       >/dev/null
sips -z   64   64 "$SRC" --out "$ICONSET/icon_32x32@2x.png"    >/dev/null
sips -z  128  128 "$SRC" --out "$ICONSET/icon_128x128.png"     >/dev/null
sips -z  256  256 "$SRC" --out "$ICONSET/icon_128x128@2x.png"  >/dev/null
sips -z  256  256 "$SRC" --out "$ICONSET/icon_256x256.png"     >/dev/null
sips -z  512  512 "$SRC" --out "$ICONSET/icon_256x256@2x.png"  >/dev/null
sips -z  512  512 "$SRC" --out "$ICONSET/icon_512x512.png"     >/dev/null
sips -z 1024 1024 "$SRC" --out "$ICONSET/icon_512x512@2x.png"  >/dev/null

iconutil -c icns "$ICONSET"
rm -rf "$ICONSET"

echo "Created app.icns ($(du -h app.icns | awk '{print $1}')). Re-run ./build.sh to apply."
