#!/usr/bin/env bash
# Build an AppImage from the onedir PyInstaller GUI build.
#
# Usage: packaging/linux/build_appimage.sh [tag]
set -euo pipefail

TAG="${1:-}"
TAG_SUFFIX="${TAG:+-$TAG}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="$ROOT/dist"
APPDIR="$DIST/AppDir"

if [ ! -d "$DIST/hls-sniffer-gui" ]; then
    echo "error: $DIST/hls-sniffer-gui not found — run: python packaging/build.py gui --onedir" >&2
    exit 1
fi
if [ ! -d "$ROOT/packaging/assets/hicolor" ]; then
    echo "error: $ROOT/packaging/assets/hicolor not found — run: python packaging/assets/generate_icon.py" >&2
    exit 1
fi

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/icons"
cp -r "$DIST/hls-sniffer-gui/." "$APPDIR/usr/bin/"
cp "$ROOT/packaging/linux/hls-sniffer.desktop" "$APPDIR/hls-sniffer.desktop"
# AppImage itself just wants one root icon; the full hicolor tree is for
# desktop integration if the user has appimaged/similar installed.
cp "$ROOT/packaging/assets/icon_256.png" "$APPDIR/hls-sniffer.png"
cp -r "$ROOT/packaging/assets/hicolor" "$APPDIR/usr/share/icons/hicolor"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/hls-sniffer-gui" "$@"
EOF
chmod +x "$APPDIR/AppRun"

TOOL="$DIST/appimagetool"
if [ ! -x "$TOOL" ]; then
    curl -sL -o "$TOOL" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$TOOL"
fi

# GitHub Actions runners have no FUSE, so extract-and-run instead of
# executing the AppImage tool directly.
OUT="$DIST/hls-sniffer-gui-linux${TAG_SUFFIX}.AppImage"
"$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"

echo "Built: $OUT"
