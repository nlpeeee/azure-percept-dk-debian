#!/bin/bash
# SPDX-License-Identifier: MIT
# Create (once) the arm64 Debian 12 "bookworm" chroot that compiles everything for the
# launcher. Bookworm matches the toolchain (GCC 12.2) the proven binaries were built
# with. Re-run with --rebuild to start over.
source "$(dirname "$0")/common.sh"
require_linux_build_host

rebuild=0; [ "${1:-}" = --rebuild ] && rebuild=1
stamp=$BUILDER/.percept-builder-ok
if [ -f "$stamp" ] && [ "$rebuild" = 0 ]; then
    say "builder already present: $BUILDER"
    exit 0
fi
if [ -d "$BUILDER" ]; then
    say "removing old builder"
    in_ns rm -rf "$BUILDER"
fi

packages=build-essential,ca-certificates,curl,python3,busybox-static,dropbear-bin,e2fsprogs,tar,gzip,zstd,xz-utils,bzip2,\
libfdt-dev,device-tree-compiler,pkg-config,file,bc,flex,bison,libssl-dev,libelf-dev,kmod,cpio,make,zlib1g-dev,patch,git
say "stage 1: debootstrap bookworm arm64 (downloads ~250 MB)"
in_ns debootstrap --arch=arm64 --foreign --variant=minbase --include="$packages" \
    bookworm "$BUILDER" http://deb.debian.org/debian
say "stage 2: configuring under qemu-user (several minutes)"
in_ns bash -c '
    set -e
    mount --rbind /dev "$1/dev"; mount -t proc proc "$1/proc"
    chroot "$1" /debootstrap/debootstrap --second-stage
' _ "$BUILDER"
printf 'builder created %s\n' "$(date -u +%FT%TZ)" > "$stamp"
chroot_run "$BUILDER" -- sh -c 'gcc --version | head -1; python3 --version; busybox | head -1'
say "builder ready: $BUILDER"
