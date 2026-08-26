#!/usr/bin/env python3
"""Render hls_sniffer.png (the reference artwork) into every icon format and
size the packaging scripts need: a Windows .ico, a macOS .icns, a flat
icon.png for AppImage/Flatpak, and a full hicolor size set for the Linux
.deb/.rpm packages.

Requires Pillow: pip install pillow
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent
SOURCE = OUT / "hls_sniffer.png"
PACKAGE_DIR = OUT.parent.parent / "hls_sniffer"

# Standard freedesktop hicolor theme sizes (used by .deb/.rpm/AppImage/Flatpak
# desktop integration) plus the sizes Windows .ico and macOS .icns embed.
HICOLOR_SIZES = [16, 22, 24, 32, 48, 64, 128, 256, 512]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def load_master() -> Image.Image:
    """Pad the source art to a square canvas (it's 779x785, not quite
    square) so every resize below is a uniform scale, never a stretch."""
    img = Image.open(SOURCE).convert("RGBA")
    size = max(img.size)
    if img.size == (size, size):
        return img
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
    return canvas


def resized(master: Image.Image, size: int) -> Image.Image:
    return master.resize((size, size), Image.LANCZOS)


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"{SOURCE} not found — expected the reference app icon there.")

    master = load_master()

    # Flat PNGs used directly: AppImage root icon, Flatpak source, generic fallback.
    resized(master, 512).save(OUT / "icon.png")
    resized(master, 256).save(OUT / "icon_256.png")

    # Windows: multi-resolution .ico for the exe and installer.
    ico_base = resized(master, max(ICO_SIZES))
    ico_base.save(OUT / "icon.ico", sizes=[(s, s) for s in ICO_SIZES])

    # macOS: multi-resolution .icns (Pillow writes these directly, no need
    # for iconutil/an .iconset directory).
    icns_base = resized(master, max(ICNS_SIZES))
    icns_base.save(OUT / "icon.icns", sizes=[(s, s) for s in ICNS_SIZES])

    # Linux: full hicolor theme tree, mirroring the install path
    # (/usr/share/icons/hicolor/<size>x<size>/apps/hls-sniffer.png) so the
    # packaging scripts can just copy this directory wholesale.
    hicolor = OUT / "hicolor"
    for size in HICOLOR_SIZES:
        apps_dir = hicolor / f"{size}x{size}" / "apps"
        apps_dir.mkdir(parents=True, exist_ok=True)
        resized(master, size).save(apps_dir / "hls-sniffer.png")

    # A copy inside the package itself: PyInstaller's --icon only sets the
    # .exe file's own icon (what Explorer/the taskbar shortcut shows before
    # launch) — the *running* window's title-bar/taskbar icon is a separate
    # Qt-level thing set via QApplication.setWindowIcon() in gui.py, which
    # loads this file at runtime (see build.py's --add-data for the frozen
    # case, and gui.py's _icon_path() for how it's located either way).
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    resized(master, 256).save(PACKAGE_DIR / "icon.png")

    print(f"Wrote icon.ico ({ICO_SIZES}), icon.icns ({ICNS_SIZES}), "
          f"icon.png, icon_256.png, hicolor/ ({HICOLOR_SIZES}), and "
          f"hls_sniffer/icon.png to {OUT}")


if __name__ == "__main__":
    main()
