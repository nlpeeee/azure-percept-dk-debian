#!/bin/bash
# SPDX-License-Identifier: MIT
# Runs inside the private namespaces made by common.sh:in_ns. Sets up /proc, /dev and
# any BINDS, then chroots. Usage: chroot-enter.sh ROOT [VAR=value ...] -- CMD...
set -euo pipefail
root=$1; shift
envs=()
while [ "$#" -gt 0 ] && [ "$1" != -- ]; do envs+=("$1"); shift; done
shift
mount --make-rprivate /
mount --rbind /dev "$root/dev"
mount -t proc proc "$root/proc"
for b in ${BINDS:-}; do
    src=${b%%:*}; rest=${b#*:}; dst=${rest%%:*}; mode=${rest#*:}
    mkdir -p "$root$dst"
    mount --bind "$src" "$root$dst"
    [ "$mode" = ro ] && mount -o remount,bind,ro "$root$dst"
done
[ -e "$root/etc/resolv.conf" ] || : > "$root/etc/resolv.conf"
mount --bind /etc/resolv.conf "$root/etc/resolv.conf" 2>/dev/null || true
exec chroot "$root" /usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/root TERM=dumb LC_ALL=C DEBIAN_FRONTEND=noninteractive "${envs[@]}" "$@"
