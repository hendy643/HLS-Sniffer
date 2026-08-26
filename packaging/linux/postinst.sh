#!/bin/sh
# Runs after the .deb/.rpm installs the app files (as root). Fetches the OS
# packages Chromium needs to actually launch — that dependency list is large
# and drifts across distro releases (e.g. Ubuntu 24.04 renaming libasound2
# to libasound2t64), so this defers to Playwright's own upstream-maintained
# `install-deps` resolver instead of hardcoding package names in the .deb/.rpm
# Depends/Requires, where getting one wrong would block installation outright.
#
# Best-effort, non-fatal: no internet, an unsupported distro, or anything
# else going wrong here must never fail the package install itself.
/opt/hls-sniffer/hls-sniffer --install-deps || true
exit 0
