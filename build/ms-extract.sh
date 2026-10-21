#!/bin/bash
# SPDX-License-Identifier: MIT
# Pull what the build needs out of Microsoft's recovery image - rootlessly, no loop mounts.
#
#   build/ms-extract.sh PATH   PATH = the recovery .zip you downloaded, or its extracted .raw
#
# Writes cache/vendor/ms/: Image, System.map, config, pe100.dtb, modules/ (the 647 stock
# modules), efi/ (shim + GRUB), and, from a .zip, fast-hab-fw.raw + emmc_full.txt. Every file
# is hash-checked where vendor/vendor-manifest.toml pins one. Nothing here is redistributed.
source "$(dirname "$0")/common.sh"
for t in sfdisk debugfs mcopy mdir python3 sha256sum; do command -v "$t" >/dev/null || die "$t missing (see: python percept doctor)"; done

src=${1:?usage: ms-extract.sh PATH-TO-ZIP-OR-RAW}
dest=$CACHE/vendor/ms
mkdir -p "$dest"
export MTOOLS_SKIP_CHECK=1

raw=$src
case "$src" in
    *.zip)
        want=$(manifest_get ms-recovery-zip sha256)
        say "verifying the recovery zip (1.1 GB)"
        got=$(sha256sum "$src" | cut -d' ' -f1)
        [ "$got" = "$want" ] || die "recovery zip sha256 mismatch: expected $want, got $got"
        member=$(unzip -Z1 "$src" | grep -E '\.raw$' | grep -v fast-hab | head -1)
        [ -n "$member" ] || die "no disk image found inside the zip"
        for m in fast-hab-fw.raw emmc_full.txt; do
            unzip -p "$src" "$m" > "$dest/$m"
        done
        # Only the first partitions are needed: stream up to the end of partition 3, then stop.
        head_bytes=$(( (165888 + 4194304) * 512 ))
        say "streaming the first $((head_bytes / 1048576)) MiB of $member"
        unzip -p "$src" "$member" 2>/dev/null | head -c "$head_bytes" > "$dest/ms-head.img" || true
        raw=$dest/ms-head.img
        ;;
    *) [ -f "$src" ] || die "not a file: $src" ;;
esac

check() {   # check ID FILE
    local want
    want=$(manifest_get "$1" sha256)
    [ -z "$want" ] && return 0
    [ "$(sha256sum "$2" | cut -d' ' -f1)" = "$want" ] || die "$2 does not match the pinned $1 hash"
}

part() {   # part INDEX -> "offset size" in bytes
    sfdisk -J "$raw" 2>/dev/null | python3 -c "
import json, sys
p = json.load(sys.stdin)['partitiontable']['partitions'][$1]
print(p['start'] * 512, p['size'] * 512)"
}
read -r o1 _ < <(part 0)
read -r o3 _ < <(part 2)

say "EFI partition"
mkdir -p "$dest/efi"
mcopy -n -i "$raw@@$o1" ::pe100.dtb "$dest/pe100.dtb"
mcopy -n -i "$raw@@$o1" ::EFI/BOOT/bootaa64.efi ::EFI/BOOT/grubaa64.efi "$dest/efi/"
check ms-pe100-dtb "$dest/pe100.dtb"

say "root partition: kernel, symbols, config, modules"
ext4="$raw?offset=$o3"
release=5.4.3-26.cm1
debugfs -R "dump /boot/vmlinuz $dest/Image" "$ext4" >/dev/null 2>&1
debugfs -R "dump /boot/System.map-$release $dest/System.map" "$ext4" >/dev/null 2>&1
debugfs -R "dump /boot/config-$release $dest/config" "$ext4" >/dev/null 2>&1
check ms-stock-kernel "$dest/Image"
rm -rf "$dest/modules"
mkdir -p "$dest/modules"
( cd "$dest/modules" && debugfs -R "rdump /lib/modules/$release ." "$ext4" >/dev/null 2>&1 )
n=$(find "$dest/modules" -name '*.ko*' | wc -l)
[ "$n" -ge 600 ] || die "expected ~647 stock modules, found $n"
say "done: $dest ($(du -sh "$dest" | cut -f1); $n modules)"
