#!/bin/bash
# SPDX-License-Identifier: MIT
# Shared helpers for the Linux/WSL2 build scripts. Source this file; do not run it.
#
# Everything runs without root: a user namespace maps your account to root and
# (through /etc/subuid, via newuidmap from the uidmap package) a full range of
# other ids, which is what debootstrap and dpkg need. Mounts made inside the
# namespace are private to it and vanish when the command ends - nothing is
# ever mounted in the host's namespace.

set -euo pipefail

PERCEPT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CACHE=${PERCEPT_CACHE:-$PERCEPT_ROOT/cache}
DL=$CACHE/downloads
BUILDER=$CACHE/builder-bookworm-arm64

say()  { printf '\033[1m==> %s\033[0m\n' "$*" >&2; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

require_linux_build_host() {
    [ "$(uname -s)" = Linux ] || die "this must run on Linux (on Windows, inside WSL2: see docs/quickstart-windows.md)"
    command -v newuidmap >/dev/null || die "newuidmap missing: sudo apt install uidmap"
    command -v debootstrap >/dev/null || die "debootstrap missing: sudo apt install debootstrap"
    [ -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ] || [ "$(uname -m)" = aarch64 ] ||
        die "arm64 emulation missing: sudo apt install qemu-user-static binfmt-support"
    case "$PERCEPT_ROOT" in
        /mnt/?/*) warn "building on a Windows drive ($PERCEPT_ROOT) is slow and loses file ownership; clone the repo inside WSL (~/...) instead" ;;
    esac
}

# in_ns CMD... : run CMD as "root" with a full uid/gid range in private namespaces.
in_ns() {
    unshare --map-root-user --map-auto --mount --pid --fork --kill-child -- "$@"
}

# chroot_run ROOT [VAR=value ...] -- CMD... : run CMD inside an arm64 chroot.
#   BINDS="host:inside[:ro] ..." (environment) adds bind mounts.
chroot_run() {
    local root=$1; shift
    local envs=()
    while [ "$#" -gt 0 ] && [ "$1" != -- ]; do envs+=("$1"); shift; done
    [ "${1:-}" = -- ] && shift
    in_ns bash "$PERCEPT_ROOT/build/chroot-enter.sh" "$root" "${envs[@]}" -- "$@"
}

# fetch URL DEST SHA256 : download once, verify always.
fetch() {
    local url=$1 dest=$2 want=$3
    mkdir -p "$(dirname "$dest")"
    if [ ! -f "$dest" ]; then
        say "downloading ${url##*/}"
        curl -fL --retry 3 -o "$dest.part" "$url"
        mv "$dest.part" "$dest"
    fi
    local got
    got=$(sha256sum "$dest" | cut -d' ' -f1)
    if [ -z "$want" ]; then
        die "no pinned sha256 for ${dest##*/} (got $got): add it to vendor/vendor-manifest.toml after checking the source"
    fi
    [ "$got" = "$want" ] || die "sha256 mismatch for ${dest##*/}: expected $want, got $got"
}

# manifest_get ID FIELD : read a field of an [[input]] in vendor/vendor-manifest.toml.
manifest_get() {
    python3 - "$PERCEPT_ROOT" "$1" "$2" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/src")
from percept import tomlmini
data = tomlmini.load_file(sys.argv[1] + "/vendor/vendor-manifest.toml")
for item in data["input"]:
    if item["id"] == sys.argv[2]:
        print(item.get(sys.argv[3], ""))
        break
else:
    sys.exit("no such manifest entry: " + sys.argv[2])
PY
}
