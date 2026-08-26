#!/usr/bin/env bash
# Build a single-file .flatpak bundle from the onedir PyInstaller GUI build.
#
# Prereqs (installed by CI, see .github/workflows/release.yml):
#   sudo apt-get install -y flatpak flatpak-builder
#   flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
#   flatpak install --user -y flathub org.freedesktop.Platform//23.08 org.freedesktop.Sdk//23.08
#
# Usage: packaging/linux/build_flatpak.sh [tag]
set -euo pipefail

TAG="${1:-}"
TAG_SUFFIX="${TAG:+-$TAG}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="$ROOT/dist"
MANIFEST="$ROOT/packaging/linux/flatpak/io.github.hls_sniffer.HlsSniffer.yml"
APP_ID="io.github.hls_sniffer.HlsSniffer"

if [ ! -d "$DIST/hls-sniffer-gui" ]; then
    echo "error: $DIST/hls-sniffer-gui not found — run: python packaging/build.py gui --onedir" >&2
    exit 1
fi
if [ ! -d "$ROOT/packaging/assets/hicolor" ]; then
    echo "error: $ROOT/packaging/assets/hicolor not found — run: python packaging/assets/generate_icon.py" >&2
    exit 1
fi

flatpak-builder --user --force-clean --repo="$DIST/flatpak-repo" \
    "$DIST/flatpak-build" "$MANIFEST"

OUT="$DIST/hls-sniffer-gui-linux${TAG_SUFFIX}.flatpak"
flatpak build-bundle "$DIST/flatpak-repo" "$OUT" "$APP_ID"

echo "Built: $OUT"
