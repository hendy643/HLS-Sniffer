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
chmod +x "$ROOT/packaging/linux/postinst.sh"

# Most of Qt itself is bundled in the PyInstaller build (--collect-all
# PyQt6), but the low-level X11/Wayland platform-plugin integration libs
# aren't, and PyQt6 apps fail to even start without them ("could not load
# the Qt platform plugin xcb"). These package names are small and stable
# across distro releases, so declaring them as hard deps here is safe —
# unlike Chromium's much larger, faster-drifting dependency list, which
# postinst.sh resolves via Playwright's own `install-deps` instead (see
# there for why).
for PKG_TYPE in deb rpm; do
    if [ "$PKG_TYPE" = "deb" ]; then
        # mpv is in Debian/Ubuntu's default repos, so this is safe as a
        # recommendation (apt installs it by default, but a missing mpv
        # doesn't block installing hls-sniffer itself).
        DEPS=(-d libxcb-cursor0 -d libxkbcommon0 --deb-recommends mpv)
    else
        # mpv isn't in Fedora/RHEL's default repos (needs RPM Fusion
        # enabled), so it's deliberately left off here rather than risking
        # an unresolvable hard dependency on a stock system.
        DEPS=(-d xcb-util-cursor -d libxkbcommon)
    fi

    fpm -s dir -t "$PKG_TYPE" -f \
        -n hls-sniffer \
        -v "$VERSION" \
        --description "Find and diagnose the real HLS (.m3u8) stream source behind a JS-heavy video embed page" \
        --url "https://github.com/OWNER/hls-sniffer" \
        --license MIT \
        --maintainer "hls-sniffer contributors" \
        --after-install "$ROOT/packaging/linux/postinst.sh" \
        "${DEPS[@]}" \
        -p "$DIST/hls-sniffer-linux${TAG_SUFFIX}.${PKG_TYPE}" \
        "$DIST/hls-sniffer-gui/=/opt/hls-sniffer/" \
        "$DIST/.launcher/hls-sniffer-gui=/usr/bin/hls-sniffer-gui" \
        "$DIST/hls-sniffer=/usr/bin/hls-sniffer" \
        "$ROOT/packaging/linux/hls-sniffer.desktop=/usr/share/applications/hls-sniffer.desktop" \
        "$ROOT/packaging/assets/hicolor/=/usr/share/icons/hicolor/"
done

echo "Built:"
ls -la "$DIST"/*.deb "$DIST"/*.rpm
