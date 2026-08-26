"""Capture and diagnose HLS (.m3u8) stream sources from a JS-heavy embed page.

Sites that embed a video player rarely put the stream URL in the page HTML —
an iframe (often on a different domain) runs obfuscated JS that fetches the
.m3u8 playlist via XHR/fetch and re-polls it every few seconds (normal HLS
live-playlist refresh behavior). Regex-scraping the HTML won't find it, so
this drives a real browser (Playwright) and watches network traffic instead.

A captured URL often still won't play in ffmpeg/mpv/VLC because:
  - it's a short-TTL signed link that expires within seconds of being issued
  - the CDN requires a matching Referer/Origin/Cookie/User-Agent, which
    those players don't send unless told to
  - the most-requested playlist during page load is actually a decoy/ad
    stream, and the real one only shows up once the player is fully mounted

So every candidate found is re-fetched three ways (from inside the browser
context, bare, and with copied headers) so the caller can see exactly which
of those it is, instead of guessing.
"""

from __future__ import annotations

import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit, urlunsplit


def _default_playwright_browsers_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "ms-playwright"


# When frozen by PyInstaller, Playwright's bundled driver resolves browsers
# to a path relative to itself (inside the onefile temp extraction dir, or
# the onedir install dir) instead of the normal shared user cache — for a
# --onefile build that means it gets silently wiped and re-downloaded on
# every single launch. Pin it to the standard location explicitly so
# behavior is identical (and the download persists) whether frozen or not.
# Must happen before playwright is imported anywhere, hence: here, at
# module load, ahead of every (deliberately lazy) `import playwright` below.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_default_playwright_browsers_path()))

M3U8_RE = re.compile(r"\.m3u8(\?|$)", re.IGNORECASE)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class Hit:
    url: str
    ts: float
    frame_url: str
    headers: dict = field(default_factory=dict)


@dataclass
class Candidate:
    base: str
    url: str  # a representative full URL (with query) for this base
    count: int
    first_ts: float
    last_ts: float
    headers: dict = field(default_factory=dict)
    browser_status: "int | str | None" = None
    browser_body: "str | None" = None
    bare_status: "int | str | None" = None
    headered_status: "int | str | None" = None
    playlist_kind: "str | None" = None  # "master" | "media" | "unknown" | "not-a-playlist"
    encrypted: bool = False
    segment_check: "str | None" = None

    def to_json(self) -> dict:
        d = dict(self.__dict__)
        d.pop("browser_body", None)
        return d

    def diagnosis(self) -> str:
        bare_ok = str(self.bare_status).isdigit() and int(str(self.bare_status)) < 400
        headered_ok = str(self.headered_status).isdigit() and int(str(self.headered_status)) < 400
        if bare_ok:
            return "plays with no special headers; if it still failed, the token likely expired before you fed it to a player"
        if headered_ok:
            return "needs Referer/Origin/User-Agent (and maybe Cookie) headers to play"
        return "still failing even with copied headers/cookies — likely a single-use/IP-bound token, or this is a decoy/ad playlist rather than the real stream"


def base_of(url: str) -> str:
    """Strip the query string so repeated polls of the same playlist collapse
    to one candidate (some players do vary the path per poll too, so this is
    a heuristic, not a guarantee)."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _bare_fetch(url: str, headers: "dict | None" = None, timeout: float = 8.0):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(4096).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return f"error: {e}", None


def _classify_playlist(body: "str | None") -> "tuple[str, bool]":
    if not body:
        return "unknown", False
    if "#EXTM3U" not in body:
        return "not-a-playlist", False
    encrypted = "#EXT-X-KEY" in body
    if "#EXT-X-STREAM-INF" in body:
        return "master", encrypted
    if "#EXTINF" in body:
        return "media", encrypted
    return "unknown", encrypted


def _run_playwright_cli(args: list[str], status: "Callable[[str], None]") -> None:
    """Run a `playwright <args>` subcommand in-process, via the bundled
    driver — works from a frozen (PyInstaller) executable too, not just a
    normal pip install."""
    from playwright.__main__ import main as playwright_main

    old_argv = sys.argv
    sys.argv = ["playwright", *args]
    try:
        playwright_main()
    except SystemExit as e:
        if e.code not in (None, 0):
            raise RuntimeError(f"playwright {' '.join(args)} failed (exit code {e.code}).") from e
    finally:
        sys.argv = old_argv
    status(f"playwright {' '.join(args)} done.")


def _install_chromium(status: "Callable[[str], None]") -> None:
    """Download the Chromium build Playwright needs."""
    status("Chromium not found — downloading it now (first run only, ~150MB)...")
    _run_playwright_cli(["install", "chromium"], status)


def install_os_deps(on_status: "Callable[[str], None] | None" = None) -> bool:
    """Linux only: install the OS packages Chromium needs to actually launch
    (nss, atk, alsa, etc.) via `playwright install-deps`, which shells out to
    apt/dnf with the exact package list for the running distro — that list
    is large and drifts across distro releases (e.g. Ubuntu 24.04 renaming
    libasound2 to libasound2t64), so we defer to Playwright's own
    upstream-maintained resolver instead of hardcoding it. Needs root; the
    .deb/.rpm postinst script is what actually calls this (via
    `hls-sniffer --install-deps`), not anything that runs as a normal user.
    Returns True on success, False otherwise (never raises)."""
    status = on_status or (lambda _msg: None)
    try:
        _run_playwright_cli(["install-deps", "chromium"], status)
        return True
    except Exception as e:
        status(f"OS dependency install failed: {e}")
        return False


def ensure_chromium(on_status: "Callable[[str], None] | None" = None) -> bool:
    """Make sure Playwright's Chromium is installed, downloading it if not.
    Used both by rip()'s own lazy fallback and by the Windows installer's
    InstallChromium custom action (via `hls-sniffer --install-chromium`), so
    the app doesn't have to eat that ~150MB download cold on first launch.
    Returns True if Chromium ended up available, False otherwise."""
    status = on_status or (lambda _msg: None)
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        status("Chromium already installed.")
        return True
    except Exception:
        pass
    try:
        _install_chromium(status)
        return True
    except Exception as e:
        status(f"Chromium install failed: {e}")
        return False


def rip(
    url: str,
    wait: float = 20.0,
    headless: bool = True,
    ua: str = DEFAULT_UA,
    click: bool = True,
    on_hit: "Callable[[Hit], None] | None" = None,
    on_status: "Callable[[str], None] | None" = None,
) -> list[Candidate]:
    """Load `url` in a real browser, capture every .m3u8 request/response,
    then diagnose each distinct playlist found. Returns candidates in the
    order their base URL was first observed.

    `on_hit` is called synchronously for every .m3u8 network request as it
    happens (useful for live progress logging in a GUI); `on_status` is
    called with short human-readable progress messages.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright isn't installed. Run:\n"
            "    pip install playwright\n"
            "    playwright install chromium"
        ) from e

    def status(msg: str) -> None:
        if on_status:
            on_status(msg)

    hits: list[Hit] = []
    start = time.monotonic()

    def on_request(request):
        if M3U8_RE.search(request.url):
            try:
                headers = request.all_headers()
            except Exception:
                headers = dict(request.headers)
            hit = Hit(request.url, time.monotonic() - start, request.frame.url, headers)
            hits.append(hit)
            if on_hit:
                on_hit(hit)

    status(f"launching browser (headless={headless})")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=headless)
        except Exception:
            # Recover inline (no separate ensure_chromium() launch+close
            # probe here) since we already know it's missing from this
            # failure — that avoids starting a second Playwright driver
            # session just to confirm what we're about to fix anyway.
            _install_chromium(status)
            browser = p.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=ua, viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.on("request", on_request)

        status(f"loading {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        if click:
            status("attempting to trigger playback (click)")
            try:
                page.mouse.click(page.viewport_size["width"] // 2, page.viewport_size["height"] // 2)
            except Exception:
                pass
            for frame in page.frames:
                try:
                    frame.click("body", timeout=1000)
                except Exception:
                    pass

        status(f"watching network traffic for {wait:.0f}s")
        page.wait_for_timeout(int(wait * 1000))

        cookies = context.cookies()

        by_base: "OrderedDict[str, Candidate]" = OrderedDict()
        for h in hits:
            b = base_of(h.url)
            if b not in by_base:
                by_base[b] = Candidate(base=b, url=h.url, count=0, first_ts=h.ts, last_ts=h.ts, headers=h.headers)
            c = by_base[b]
            c.count += 1
            c.last_ts = h.ts

        candidates = list(by_base.values())

        status(f"re-checking {len(candidates)} candidate(s) with real browser cookies")
        for c in candidates:
            try:
                resp = context.request.get(c.url, headers={"Referer": c.headers.get("referer", url)})
                c.browser_status = resp.status
                if resp.ok:
                    c.browser_body = resp.text()[:4096]
            except Exception as e:
                c.browser_status = f"error: {e}"

        browser.close()

    cookie_header_by_domain: dict[str, str] = {}
    for c in candidates:
        domain = urlsplit(c.url).netloc
        relevant = [ck for ck in cookies if domain.endswith(ck["domain"].lstrip("."))]
        if relevant:
            cookie_header_by_domain[domain] = "; ".join(f"{ck['name']}={ck['value']}" for ck in relevant)

    status("replaying candidates outside the browser (bare vs. headered) to diagnose playback")
    for c in candidates:
        c.bare_status, _ = _bare_fetch(c.url, headers={"User-Agent": "curl/8.0"})

        domain = urlsplit(c.url).netloc
        headered = {
            "User-Agent": c.headers.get("user-agent", ua),
            "Referer": c.headers.get("referer", url),
            "Origin": c.headers.get("origin", f"https://{urlsplit(url).netloc}"),
        }
        if domain in cookie_header_by_domain:
            headered["Cookie"] = cookie_header_by_domain[domain]
        c.headered_status, body = _bare_fetch(c.url, headers=headered)
        if body and not c.browser_body:
            c.browser_body = body

        kind, enc = _classify_playlist(c.browser_body)
        c.playlist_kind = kind
        c.encrypted = enc

        if c.browser_body and kind in ("master", "media"):
            first_ref = next(
                (line.strip() for line in c.browser_body.splitlines() if line.strip() and not line.startswith("#")),
                None,
            )
            if first_ref:
                seg_url = urljoin(c.url, first_ref)
                seg_status, _ = _bare_fetch(seg_url, headers=headered)
                c.segment_check = f"{seg_url} -> {seg_status}"

    status("done")
    return candidates


def header_lines(c: Candidate, ua: str = DEFAULT_UA) -> list[str]:
    """User-Agent/Referer/Origin as "Name: value" lines, in the order
    ffmpeg/mpv expect them — shared by ffmpeg_cmd, mpv_cmd, and the GUI's
    direct `mpv` launch so there's one place that knows the header order."""
    lines = [f"User-Agent: {c.headers.get('user-agent', ua)}"]
    ref = c.headers.get("referer")
    org = c.headers.get("origin")
    if ref:
        lines.append(f"Referer: {ref}")
    if org:
        lines.append(f"Origin: {org}")
    return lines


def ffmpeg_cmd(c: Candidate, ua: str = DEFAULT_UA) -> str:
    header_str = "\\r\\n".join(header_lines(c, ua))
    return f'ffmpeg -headers "{header_str}\\r\\n" -i "{c.url}" -c copy out.mp4'


def mpv_cmd(c: Candidate, ua: str = DEFAULT_UA) -> str:
    field_str = ",".join(header_lines(c, ua))
    return f'mpv --http-header-fields="{field_str}" "{c.url}"'


def best_guess(candidates: list[Candidate]) -> "Candidate | None":
    real = [c for c in candidates if c.playlist_kind in ("master", "media")]
    if not real:
        return None
    return max(real, key=lambda c: (c.playlist_kind == "master", c.count))
