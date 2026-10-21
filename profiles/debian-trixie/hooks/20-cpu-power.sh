#!/bin/sh
# SPDX-License-Identifier: MIT
# Run INSIDE the target arm64 Debian chroot, with this repository at /src.
# Future rootfs builders pass resolved.rootfs_env unchanged to profile hooks.
set -eu
profile=${PERCEPT_CPU_PROFILE:-unchanged}
case "$profile" in
    unchanged) exit 0 ;;
    rated|oc1500) ;;
    *) echo 'Invalid PERCEPT_CPU_PROFILE' >&2; exit 1 ;;
esac
repo=${PERCEPT_SOURCE:-/src}
[ "$(dpkg --print-architecture)" = arm64 ] || { echo 'CPU hook requires target arm64 chroot' >&2; exit 1; }
python3 "$repo/target/cpu/stage.py" --root / --profile "$profile" --allow-live-root
# The guard/powersave module must be present in every installed target initramfs.
update-initramfs -u -k all
