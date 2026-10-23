#!/bin/bash
# ============================================================================
# Azure Percept DK — Extract Source Artifacts
# Pulls the signed bootloader, kernel, modules, Wi-Fi driver and Bluetooth
# firmware out of Microsoft's recovery image into sources/.
#
# Run this ONCE from WSL, as root (it loop-mounts the image read-only):
#
# Usage:
#   sudo bash copy_sources.sh [path/to/Azure-Percept-DK.raw]
#
# With no argument, uses sources/Azure-Percept-DK.raw or the image extracted
# from the recovery ZIP at sources/ms-image/Azure-Percept-DK*.raw.
# Set SOURCES_DIR to write somewhere other than sources/.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="${SOURCES_DIR:-$SCRIPT_DIR/sources}"
KVER="5.4.3-26.cm1"

die() { echo "ERROR: $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "This script must be run as root (sudo)."
for cmd in losetup xz tar; do
    command -v "$cmd" &>/dev/null || die "'$cmd' not found."
done
mkdir -p "$SRC_DIR"

# ── Find the MS image ─────────────────────────────────────────────────────
MS_IMAGE="${1:-}"
if [ -z "$MS_IMAGE" ]; then
    for f in "$SRC_DIR/Azure-Percept-DK.raw" "$SRC_DIR"/ms-image/Azure-Percept-DK*.raw; do
        [ -f "$f" ] && { MS_IMAGE="$f"; break; }
    done
fi
[ -f "$MS_IMAGE" ] || die "MS recovery image not found. Extract the recovery ZIP into $SRC_DIR/ms-image/ or pass the .raw path."
IMG_DIR="$(cd "$(dirname "$MS_IMAGE")" && pwd)"

echo "================================================================="
echo "  Extracting source artifacts into $SRC_DIR"
echo "  From: $MS_IMAGE"
echo "================================================================="
echo ""

# 01_build_image.sh only looks in sources/ and sources/ms-image/
case "$IMG_DIR" in
    "$SRC_DIR"|"$SRC_DIR/ms-image") ;;
    *)
        echo "  Copying MS image to $SRC_DIR/Azure-Percept-DK.raw (8 GB)..."
        cp "$MS_IMAGE" "$SRC_DIR/Azure-Percept-DK.raw"
        ;;
esac

# ── HAB-signed bootloader (flash.bin in the ZIP) ──────────────────────────
if [ ! -f "$SRC_DIR/fast-hab-fw.raw" ]; then
    for f in "$IMG_DIR/fast-hab-fw.raw" "$IMG_DIR/flash.bin"; do
        [ -f "$f" ] && { cp "$f" "$SRC_DIR/fast-hab-fw.raw"; break; }
    done
fi
[ -f "$SRC_DIR/fast-hab-fw.raw" ] || die "fast-hab-fw.raw / flash.bin not found next to the image."
echo "  ✓ fast-hab-fw.raw"

# ── Mount rootfs-A (p3) read-only ─────────────────────────────────────────
LOOPDEV=""; MNT=""
cleanup() {
    [ -z "$MNT" ] || { umount "$MNT" 2>/dev/null || true; rmdir "$MNT" 2>/dev/null || true; }
    [ -z "$LOOPDEV" ] || losetup -d "$LOOPDEV" 2>/dev/null || true
}
trap cleanup EXIT

LOOPDEV=$(losetup --find --show --partscan --read-only "$MS_IMAGE")
sleep 1
MNT=$(mktemp -d)
mount -o ro,noload "${LOOPDEV}p3" "$MNT"

# Resolve a path inside the image, following one symlink level within $MNT
in_image() {
    local p="$MNT$1" t
    if [ -L "$p" ]; then
        t=$(readlink "$p")
        case "$t" in
            /*) p="$MNT$t" ;;
            *)  p="$(dirname "$p")/$t" ;;
        esac
    fi
    echo "$p"
}

cp "$(in_image /boot/vmlinuz)" "$SRC_DIR/vmlinuz-mariner"
echo "  ✓ vmlinuz-mariner"

tar czf "$SRC_DIR/ms-modules.tar.gz" -C "$MNT/lib/modules" "$KVER"
echo "  ✓ ms-modules.tar.gz"

xz -dc "$MNT/lib/modules/$KVER/kernel/drivers/net/wireless/88x2ce.ko.xz" > "$SRC_DIR/88x2ce.ko"
echo "  ✓ 88x2ce.ko"

cp "$(in_image /lib/firmware/rtl_bt/rtl8822cu_fw.bin)" "$SRC_DIR/rtl8822cu_fw"
cp "$(in_image /lib/firmware/rtl_bt/rtl8822cu_config.bin)" "$SRC_DIR/rtl8822cu_config"
echo "  ✓ rtl8822cu_fw, rtl8822cu_config"

echo ""
echo "All source files extracted:"
ls -lh "$SRC_DIR/"
echo ""
if [ -f "$SRC_DIR/debian-rootfs.tar.zst" ]; then
    echo "Next step: sudo bash 01_build_image.sh"
else
    echo "Next step: sudo bash 00_build_rootfs.sh"
fi
