#!/bin/bash
# SPDX-License-Identifier: MIT
# Build the pinned Percept module pair in the arm64 Bookworm builder.
source "$(dirname "$0")/../build/common.sh"
require_linux_build_host
out=$PERCEPT_ROOT/out/kexecmod
vendor=$CACHE/vendor/ms
while [ "$#" -gt 0 ]; do
    case "$1" in
        --out) out=$2; shift ;;
        --vendor) vendor=$2; shift ;;
        *) die "unknown option: $1" ;;
    esac
    shift
done
for file in Image System.map config; do [ -s "$vendor/$file" ] || die "missing $vendor/$file; run build/ms-extract.sh first"; done
[ "$(sha256sum "$vendor/Image" | cut -d' ' -f1)" = "$(manifest_get ms-stock-kernel sha256)" ] || die 'stock Image hash mismatch'
fetch "$(manifest_get linux-5.4.3 url)" "$DL/linux-5.4.3.tar.xz" "$(manifest_get linux-5.4.3 sha256)"
fetch "$(manifest_get kexec-mod-4ba956f url)" "$DL/kexec-mod-4ba956f.tar.gz" "$(manifest_get kexec-mod-4ba956f sha256)"
bash "$PERCEPT_ROOT/build/make-builder.sh"
mkdir -p "$out"
commit=$(git -C "$PERCEPT_ROOT" rev-parse HEAD)
BINDS="$PERCEPT_ROOT:/src:ro $DL:/dl:ro $vendor:/vendor:ro $out:/out" \
    chroot_run "$BUILDER" SOURCE_COMMIT="$commit" -- bash /src/kexecmod/chroot-build.sh
( cd "$out" && sha256sum arch.ko core.ko modules.manifest.json > SHA256SUMS )
say "modules built in $out"
cat "$out/SHA256SUMS"
