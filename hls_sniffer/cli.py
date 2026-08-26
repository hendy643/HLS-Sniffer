#!/usr/bin/env python3
"""Command-line interface for hls-sniffer."""

from __future__ import annotations

import argparse
import json
import sys

from . import core


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hls-sniffer",
        description=__doc__ or "Find and diagnose the real HLS (.m3u8) source behind a JS-heavy embed page.",
    )
    parser.add_argument("url", nargs="?", help="Page URL to inspect (e.g. a link to a page embedding a video player)")
    parser.add_argument("--wait", type=float, default=20.0, help="Seconds to watch network traffic (default: 20)")
    parser.add_argument("--headed", action="store_true", help="Show the browser window instead of running headless")
    parser.add_argument("--no-click", action="store_true", help="Don't attempt to click play / dismiss overlays")
    parser.add_argument("--user-agent", default=core.DEFAULT_UA)
    parser.add_argument("--json", metavar="FILE", help="Write full diagnostic results to FILE")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress messages")
    parser.add_argument(
        "--install-chromium",
        action="store_true",
        help="Just download Playwright's Chromium (if not already present) and exit — "
        "used by the Windows installer, but safe to run manually.",
    )
    args = parser.parse_args()

    def on_status(msg: str) -> None:
        if not args.quiet:
            print(f"... {msg}", file=sys.stderr)

    if args.install_chromium:
        ok = core.ensure_chromium(on_status)
        sys.exit(0 if ok else 1)

    if not args.url:
        parser.error("the following arguments are required: url")

    try:
        candidates = core.rip(
            args.url,
            wait=args.wait,
            headless=not args.headed,
            ua=args.user_agent,
            click=not args.no_click,
            on_status=on_status,
        )
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if not candidates:
        print(
            "No .m3u8 requests were observed. Try --headed to watch it load, or increase --wait.",
            file=sys.stderr,
        )
        sys.exit(2)

    print(f"\nFound {len(candidates)} distinct .m3u8 playlist(s):\n")
    for i, c in enumerate(candidates, 1):
        print(f"[{i}] {c.url}")
        print(f"    first seen: {c.first_ts:.2f}s   last seen: {c.last_ts:.2f}s   requests: {c.count}")
        print(f"    kind: {c.playlist_kind}{'  (AES-encrypted)' if c.encrypted else ''}")
        print(
            f"    status  in-browser: {c.browser_status}   "
            f"bare (no headers): {c.bare_status}   with copied headers: {c.headered_status}"
        )
        if c.segment_check:
            print(f"    first segment check: {c.segment_check}")
        print(f"    -> diagnosis: {c.diagnosis()}")
        print(f"    ffmpeg: {core.ffmpeg_cmd(c, args.user_agent)}")
        print(f"    mpv:    {core.mpv_cmd(c, args.user_agent)}")
        print()

    best = core.best_guess(candidates)
    if best:
        print(f"Best guess at the real stream: {best.url}")
    else:
        print(
            "None of the captured playlists parsed as valid HLS content — "
            "rerun with --headed and watch what the player actually does, "
            "the real m3u8 may need a longer --wait or a manual click on the play button."
        )

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([c.to_json() for c in candidates], f, indent=2)
        print(f"\nFull diagnostic results written to {args.json}")


if __name__ == "__main__":
    main()
