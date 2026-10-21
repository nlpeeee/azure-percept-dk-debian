#!/bin/bash
# ============================================================================
# Azure Percept DK — Copy Source Artifacts
# Copies all needed source files from your existing debian-flash directory
# into the production/sources/ directory.
#
# Run this ONCE from WSL to populate sources/
#
# Usage:
#   bash copy_sources.sh
# ============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$SCRIPT_DIR/sources"
mkdir -p "$SRC_DIR"

# ── Source locations (adjust these paths if your layout differs) ──────────
FLASH_DIR="/mnt/e/percept/debian-flash"
ORIG_DIR="/mnt/e/percept/microsoftorig"

echo "================================================================="
echo "  Copying source artifacts into production/sources/"
echo "================================================================="
echo ""

copy_file() {
    local src="$1"
    local dst="$2"
    if [ -f "$src" ]; then
        echo "  ✓ Copying $(basename "$src") ($(ls -lh "$src" | awk '{print $5}'))"
        cp "$src" "$dst"
    else
        echo "  ✗ MISSING: $src"
        return 1
    fi
}

ERRORS=0

# 1. Original Microsoft image (8.0G) — the base for everything
copy_file "$ORIG_DIR/Azure-Percept-DK.raw" "$SRC_DIR/Azure-Percept-DK.raw" || ERRORS=$((ERRORS+1))

# 2. HAB-signed bootloader (2.6M) — needed for UUU SDP boot + eMMC boot partition
copy_file "$FLASH_DIR/fast-hab-fw.raw" "$SRC_DIR/fast-hab-fw.raw" || ERRORS=$((ERRORS+1))

# 3. Microsoft-signed Mariner kernel (35M) — the ONLY kernel that boots on this board
copy_file "$FLASH_DIR/vmlinuz-mariner" "$SRC_DIR/vmlinuz-mariner" || ERRORS=$((ERRORS+1))

# 4. Original MS kernel modules tarball (8.2M, 647 modules including 88x2ce)
copy_file "$FLASH_DIR/ms-modules.tar.gz" "$SRC_DIR/ms-modules.tar.gz" || ERRORS=$((ERRORS+1))

# 5. Decompressed 88x2ce Wi-Fi driver (6.0M) — extracted from ms-modules for explicit install
copy_file "$FLASH_DIR/wifi-modules/88x2ce.ko" "$SRC_DIR/88x2ce.ko" || ERRORS=$((ERRORS+1))

# 6. Bluetooth firmware from original MS image (52K + 6 bytes)
copy_file "$FLASH_DIR/rtl8822cu_fw" "$SRC_DIR/rtl8822cu_fw" || ERRORS=$((ERRORS+1))
copy_file "$FLASH_DIR/rtl8822cu_config" "$SRC_DIR/rtl8822cu_config" || ERRORS=$((ERRORS+1))

# 7. Debian rootfs tarball (97M) — if already built
if [ -f "$FLASH_DIR/debian-rootfs.tar.zst" ]; then
    copy_file "$FLASH_DIR/debian-rootfs.tar.zst" "$SRC_DIR/debian-rootfs.tar.zst"
    echo "  (rootfs tarball found — you can skip 00_build_rootfs.sh)"
else
    echo "  ⚠ debian-rootfs.tar.zst not found — run 00_build_rootfs.sh to build it"
fi

echo ""
if [ "$ERRORS" -gt 0 ]; then
    echo "WARNING: $ERRORS file(s) missing! Check paths above."
    exit 1
else
    echo "All source files copied successfully."
    echo ""
    echo "Contents of sources/:"
    ls -lh "$SRC_DIR/"
fi
echo ""
echo "Next step: sudo bash 01_build_image.sh"
