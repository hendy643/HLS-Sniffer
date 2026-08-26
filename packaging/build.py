#!/usr/bin/env python3
"""Build hls-sniffer executables with PyInstaller.

    python packaging/build.py cli               # onefile CLI binary
    python packaging/build.py gui                # onefile GUI binary
    python packaging/build.py gui --onedir        # onedir build (a folder,
                                                    # or a .app bundle on
                                                    # macOS) — what the native
                                                    # installer scripts
                                                    # (Inno Setup/deb/rpm/
                                                    # AppImage/flatpak/dmg)
                                                    # consume
    python packaging/build.py                     # both, onefile

Output lands in dist/. This must be run once per target OS (PyInstaller does
not cross-compile) — .github/workflows/release.yml does that in CI across
Windows/macOS/Linux on every tagged release, and also drives the OS-native
installer scripts under packaging/{windows,linux,macos}/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "packaging" / "assets"


def _icon_args() -> list[str]:
    if sys.platform == "darwin":
        icon = ASSETS / "icon.icns"
    elif sys.platform.startswith("win"):
        icon = ASSETS / "icon.ico"
    else:
        icon = ASSETS / "icon.png"
    return ["--icon", str(icon)] if icon.exists() else []


def build_cli(onedir: bool) -> None:
    PyInstaller.__main__.run([
        str(ROOT / "packaging" / "cli_entry.py"),
        "--name", "hls-sniffer",
        "--noconfirm",
        "--onedir" if onedir else "--onefile",
        "--paths", str(ROOT),
        "--collect-all", "playwright",
    ])


def build_gui(onedir: bool) -> None:
    args = [
        str(ROOT / "packaging" / "gui_entry.py"),
        "--name", "hls-sniffer-gui",
        "--noconfirm",
        "--onedir" if onedir else "--onefile",
        "--windowed",
        "--paths", str(ROOT),
        "--collect-all", "playwright",
        "--collect-all", "PyQt6",
        *_icon_args(),
    ]
    if sys.platform == "darwin":
        args += ["--osx-bundle-identifier", "io.github.hls-sniffer.app"]
    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    argv = sys.argv[1:]
    onedir = "--onedir" in argv
    argv = [a for a in argv if a != "--onedir"]
    target = argv[0] if argv else "both"

    if target not in ("cli", "gui", "both"):
        print(f"unknown target: {target!r} (expected cli, gui, or both)", file=sys.stderr)
        sys.exit(1)

    if target in ("cli", "both"):
        build_cli(onedir)
    if target in ("gui", "both"):
        build_gui(onedir)
