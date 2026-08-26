#!/usr/bin/env python3
"""Copy dist/ onefile build outputs to versions with an OS suffix (and,
for a tagged release, the git tag), so artifacts from all three GitHub
Actions runners can sit side by side without colliding and are identifiable
by release. This copies rather than renames: the original unsuffixed files
are left in place because the native-packaging scripts (deb/rpm/installer/
dmg) that run afterwards expect to find them under their plain names.

Usage: python packaging/rename_artifacts.py <linux|macos|windows> [tag]
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

if __name__ == "__main__":
    suffix = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 else ""
    tag_suffix = f"-{tag}" if tag else ""
    ext = ".exe" if suffix == "windows" else ""
    dist = Path("dist")
    for name in ("hls-sniffer", "hls-sniffer-gui"):
        src = dist / f"{name}{ext}"
        dst = dist / f"{name}-{suffix}{tag_suffix}{ext}"
        if src.exists():
            shutil.copy2(str(src), str(dst))
            print(f"{src} -> {dst}")
        else:
            print(f"warning: {src} not found", file=sys.stderr)
