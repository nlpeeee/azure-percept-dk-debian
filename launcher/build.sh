#!/bin/bash
# SPDX-License-Identifier: MIT
# Build the launcher initramfs (launcher.cpio.gz) reproducibly, without root.
#
#   launcher/build.sh [--no-modules] [--modules DIR] [--keys FILE] [--out DIR]
#
# Needs a Linux build host (Windows: WSL2). The first run creates an arm64 Debian 12
# chroot (cache/builder-bookworm-arm64) - see build/make-builder.sh. Output goes to
# out/launcher/: launcher.cpio.gz, launcher.manifest.json and SHA256SUMS.
source "$(dirname "$0")/../build/common.sh"
require_linux_build_host

out=$PERCEPT_ROOT/out/launcher
modules=$PERCEPT_ROOT/out/kexecmod
no_modules=0
keys=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --no-modules) no_modules=1 ;;
        --modules) modules=$2; shift ;;
        --keys) keys=$2; shift ;;
        --out) out=$2; shift ;;
        *) die "unknown option: $1" ;;
    esac
    shift
done
if [ "$no_modules" = 0 ] && ! { [ -f "$modules/arch.ko" ] && [ -f "$modules/core.ko" ]; }; then
    die "no kexec modules in $modules (build them with kexecmod/build.sh, or pass --no-modules for a rescue-only test archive)"
fi

"$PERCEPT_ROOT/build/make-builder.sh"
fetch "$(manifest_get kexec-tools-2.0.25 url)" "$DL/kexec-tools-2.0.25.tar.xz" "$(manifest_get kexec-tools-2.0.25 sha256)"

mkdir -p "$out"
binds="$PERCEPT_ROOT:/src:ro $DL:/dl:ro $out:/out"
envs=(NO_MODULES=$no_modules SOURCE_COMMIT=$(git -C "$PERCEPT_ROOT" rev-parse HEAD))
if [ "$no_modules" = 0 ]; then binds="$binds $modules:/modules:ro"; fi
if [ -n "$keys" ]; then
    cp "$keys" "$out/authorized_keys.input"
    envs+=(AUTHORIZED_KEYS=/out/authorized_keys.input)
fi
say "building launcher in the arm64 chroot"
BINDS="$binds" chroot_run "$BUILDER" "${envs[@]}" -- bash /src/launcher/chroot-build.sh
rm -f "$out/authorized_keys.input"
rm -rf "$out/stage"
( cd "$out" && sha256sum launcher.cpio.gz launcher.manifest.json > SHA256SUMS )
say "launcher built: $out/launcher.cpio.gz ($(stat -c %s "$out/launcher.cpio.gz") bytes)"
cat "$out/SHA256SUMS"
