# hls-sniffer

Find and diagnose the real HLS (`.m3u8`) stream source behind a JS-heavy
video embed page — the kind where the player is buried in an obfuscated
bundle inside an iframe, and the playlist URL is only ever fetched via JS,
never written into the HTML.

Instead of trying to regex-scrape a page that was deliberately built to
resist that, `hls-sniffer` drives a real headless browser, watches every
network request for anything matching `.m3u8`, and then tells you not just
the URL but *why* it will or won't actually play in `ffmpeg`/`mpv`/VLC.

## Why not just grab the URL?

A captured playlist URL frequently doesn't play once you copy it out of the
browser, because:

- it's a short-TTL signed link that expires within seconds of being issued
- the CDN requires a matching `Referer` / `Origin` / `Cookie` / `User-Agent`,
  which players don't send unless told to
- the most-requested playlist during page load is actually a decoy/ad
  stream, and the real one only shows up once the player has fully mounted

So every candidate `hls-sniffer` finds gets re-fetched three different ways
— from inside the live browser session, bare with no headers, and with the
headers copied from the real request — so you can see exactly which of
those is the actual blocker, and get a ready-to-run `ffmpeg`/`mpv` command
with the right headers baked in.

## Install

### Prebuilt packages (recommended for most users)

Grab one from the [Releases](../../releases) page — every filename below has
the release's git tag appended (e.g. `hls-sniffer-gui-windows-setup-v1.0.0.exe`):

| Platform | Formats |
|---|---|
| Windows | `hls-sniffer-gui-windows-setup-<tag>.exe` installer (Start Menu/desktop shortcut, includes the CLI too, no admin required), or the standalone `hls-sniffer-gui-windows-<tag>.exe` / `hls-sniffer-windows-<tag>.exe` (no install) |
| macOS | `hls-sniffer-gui-macos-<tag>.dmg` (drag to Applications; includes the CLI binary too), or the standalone `hls-sniffer-macos-<tag>` binary |
| Linux | `.deb`, `.rpm`, `.AppImage`, or `.flatpak` (each named `hls-sniffer(-gui)-linux-<tag>.<ext>`) — pick whichever fits your distro, or the standalone `hls-sniffer-linux-<tag>` / `hls-sniffer-gui-linux-<tag>` binaries |

Notes:
- **Windows**: the installer downloads [mpv](https://mpv.io/) and Playwright's
  Chromium for you automatically (see below), and installs per-user — no
  admin/UAC needed. It's unsigned, so SmartScreen will warn on first run —
  "More info" → "Run anyway". The standalone `.exe`s trigger the same warning.
- **macOS**: unsigned/unnotarized, so Gatekeeper blocks it the first time.
  Right-click the app/binary → "Open" → "Open", or run
  `xattr -d com.apple.quarantine <file>` once from Terminal.
- **Linux `.deb`/`.rpm`**: installs to `/opt/hls-sniffer` with a
  `hls-sniffer-gui` and `hls-sniffer` command on your PATH, plus a desktop
  entry. **AppImage**: `chmod +x` then run directly, no install needed.
  **Flatpak**: `flatpak install hls-sniffer-gui-linux-<tag>.flatpak`, then
  launch as `io.github.hls_sniffer.HlsSniffer`.
- Standalone binaries need `chmod +x` on macOS/Linux.

On first run, if Chromium isn't already installed for Playwright, the app
downloads it automatically (~150MB, one-time, requires internet) — on
Windows the installer does this proactively so it's already there.

### From source

```bash
pip install -e ".[gui]"       # CLI + GUI
# or: pip install -e .        # CLI only
playwright install chromium
```

## Usage

### CLI

```bash
hls-sniffer "https://example.com/some-page-with-a-video-embed"
hls-sniffer "<url>" --headed --wait 25
hls-sniffer "<url>" --json diag.json
```

Each candidate playlist found is printed with its status under three fetch
strategies, a diagnosis of what's blocking playback, and copy-pasteable
`ffmpeg` and `mpv` commands.

### GUI

```bash
hls-sniffer-gui
```

Paste in a page URL, hit **Sniff**, and watch the log pane while it captures
traffic. Select a result to see its full diagnosis, copy an `ffmpeg`/`mpv`
command, or play it directly with `mpv` if it's installed and on your PATH.

## Building packages locally

```bash
pip install -e ".[gui,build]"

# standalone binaries
python packaging/build.py            # both CLI and GUI, onefile
python packaging/build.py gui        # just the GUI
python packaging/build.py cli        # just the CLI

# onedir build (what the native installers below are built from)
python packaging/build.py gui --onedir
```

Output goes to `dist/`. PyInstaller doesn't cross-compile, so this only
builds for the OS you run it on. From the onedir build:

```bash
# Windows (needs Inno Setup 6: choco install innosetup)
iscc packaging\windows\installer.iss /DAppVersion=1.0.0 /DTag=v1.0.0

# Linux (needs fpm: gem install fpm; and rpm, ruby-dev, build-essential)
packaging/linux/build_deb_rpm.sh 1.0.0 v1.0.0
packaging/linux/build_appimage.sh v1.0.0
packaging/linux/build_flatpak.sh v1.0.0   # needs flatpak-builder + the freedesktop runtime installed

# macOS
packaging/macos/build_dmg.sh v1.0.0
```

The trailing `v1.0.0`/`/DTag=v1.0.0` above is optional — every script above
appends it to the output filename when given, and omits the suffix entirely
when it isn't (as in a local build with no release tag in play).

`.github/workflows/release.yml` runs all of the above across
Windows/macOS/Linux runners in CI, using the git tag that triggered the run
for that suffix, and attaches every artifact to a GitHub Release whenever a
`v*` tag is pushed (or via manual dispatch for a test build without
publishing, where filenames are left unsuffixed since there's no tag).

## How it works

1. Launches Chromium via [Playwright](https://playwright.dev/python/) and
   loads the target page, including into nested iframes.
2. Listens for every request matching `\.m3u8(\?|$)` across all frames.
3. Groups repeated polls of the same playlist together (live HLS playlists
   are normally re-fetched every few seconds — that's expected, not a bug).
4. Re-fetches each distinct playlist:
   - from the browser context (real cookies, real TLS fingerprint)
   - bare, with nothing but a generic `User-Agent`
   - with `Referer`/`Origin`/`User-Agent`/`Cookie` copied from the captured
     request
5. Parses whichever response succeeds to classify it as a master or media
   playlist, flags AES-128 encryption, and does a reachability check on the
   first referenced segment.

## Limitations

- Some sites detect headless browsers and behave differently; try `--headed`
  / "Show browser window" if nothing is captured.
- Single-use or IP-bound tokens can't be "fixed" with headers — if the
  diagnosis says it's still failing with headers copied, you likely need to
  play the stream immediately after capture rather than saving the URL for
  later.
- This tool only *finds and diagnoses* a stream URL that a page already
  serves to your browser; it doesn't bypass encryption, DRM, or paywalls.

## Legal note

Only use this against pages you have the right to access and stream from.
Respect the target site's terms of service and applicable copyright law —
this is a network-debugging tool, not a license to redistribute or pirate
content.

## License

MIT — see [LICENSE](LICENSE).
