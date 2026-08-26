#!/usr/bin/env bash
# Build .deb and .rpm packages from the onedir PyInstaller build using fpm.
#
# Prereqs (installed by CI, see .github/workflows/release.yml):
#   sudo apt-get install -y ruby ruby-dev build-essential rpm
#   sudo gem install --no-document fpm
#
# Usage: packaging/linux/build_deb_rpm.sh <version> [tag]
set -euo pipefail

VERSION="${1:-0.0.0}"
TAG="${2:-}"
TAG_SUFFIX="${TAG:+-$TAG}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="$ROOT/dist"

if [ ! -d "$DIST/hls-sniffer-gui" ]; then
    echo "error: $DIST/hls-sniffer-gui not found — run: python packaging/build.py gui --onedir" >&2
    exit 1
fi
if [ ! -d "$ROOT/packaging/assets/hicolor" ]; then
    echo "error: $ROOT/packaging/assets/hicolor not found — run: python packaging/assets/generate_icon.py" >&2
    exit 1
fi

install -Dm755 "$ROOT/packaging/linux/hls-sniffer-gui-launcher" "$DIST/.launcher/hls-sniffer-gui"

for PKG_TYPE in deb rpm; do
    fpm -s dir -t "$PKG_TYPE" -f \
        -n hls-sniffer \
        -v "$VERSION" \
        --description "Find and diagnose the real HLS (.m3u8) stream source behind a JS-heavy video embed page" \
        --url "https://github.com/OWNER/hls-sniffer" \
        --license MIT \
        --maintainer "hls-sniffer contributors" \
        -p "$DIST/hls-sniffer-linux${TAG_SUFFIX}.${PKG_TYPE}" \
        "$DIST/hls-sniffer-gui/=/opt/hls-sniffer/" \
        "$DIST/.launcher/hls-sniffer-gui=/usr/bin/hls-sniffer-gui" \
        "$DIST/hls-sniffer=/usr/bin/hls-sniffer" \
        "$ROOT/packaging/linux/hls-sniffer.desktop=/usr/share/applications/hls-sniffer.desktop" \
        "$ROOT/packaging/assets/hicolor/=/usr/share/icons/hicolor/"
done

echo "Built:"
ls -la "$DIST"/*.deb "$DIST"/*.rpm
