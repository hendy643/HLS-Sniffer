#!/usr/bin/env bash
# Package the PyInstaller .app bundle into a .dmg disk image.
#
# `python packaging/build.py gui --onedir` on macOS already produces a
# proper dist/hls-sniffer-gui.app bundle (PyInstaller does this automatically
# for --windowed --onedir on darwin), this just wraps it for distribution.
#
# Usage: packaging/macos/build_dmg.sh [tag]
set -euo pipefail

TAG="${1:-}"
TAG_SUFFIX="${TAG:+-$TAG}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="$ROOT/dist"
APP="$DIST/hls-sniffer-gui.app"
STAGING="$DIST/dmg-staging"
OUT="$DIST/hls-sniffer-gui-macos${TAG_SUFFIX}.dmg"

if [ ! -d "$APP" ]; then
    echo "error: $APP not found — run: python packaging/build.py gui --onedir" >&2
    exit 1
fi

rm -rf "$STAGING" "$OUT"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

# Include the CLI binary too, if it was built.
if [ -f "$DIST/hls-sniffer" ]; then
    cp "$DIST/hls-sniffer" "$STAGING/hls-sniffer"
fi

hdiutil create -volname "hls-sniffer" -srcfolder "$STAGING" -ov -format UDZO "$OUT"

echo "Built: $OUT"
echo "Note: this is unsigned/unnotarized — users will need to right-click > Open the first time (see README)."
