#!/bin/bash
# ============================================================================
# Azure Percept DK — Debian Production Flash
# Step 1: Build Image (run in WSL)
#
# Builds a flashable eMMC image from:
#   - Original Microsoft Azure-Percept-DK.raw (preserves Secure Boot chain)
#   - Debian Bookworm arm64 rootfs
#   - Microsoft's signed Mariner 5.4.3 kernel
#   - Original MS kernel modules (including 88x2ce Wi-Fi driver)
#
# Usage:
#   sudo bash 01_build_image.sh
#
# Prerequisites:
#   sudo apt install debootstrap qemu-user-static zstd
# ============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MS_IMAGE="$SCRIPT_DIR/sources/Azure-Percept-DK.raw"
OUTPUT="$SCRIPT_DIR/output/debian-percept-dk.raw"
ROOTFS_TAR="$SCRIPT_DIR/sources/debian-rootfs.tar.zst"
MARINER_KERNEL="$SCRIPT_DIR/sources/vmlinuz-mariner"
MS_MODULES="$SCRIPT_DIR/sources/ms-modules.tar.gz"
WIFI_MODULE="$SCRIPT_DIR/sources/88x2ce.ko"
BT_FW="$SCRIPT_DIR/sources/rtl8822cu_fw"
BT_CFG="$SCRIPT_DIR/sources/rtl8822cu_config"

echo "================================================================="
echo "  Azure Percept DK — Debian Image Builder"
echo "================================================================="
echo ""

# ── Preflight ──────────────────────────────────────────────────────────
MISSING=0
for f in "$MS_IMAGE" "$ROOTFS_TAR" "$MARINER_KERNEL" "$MS_MODULES" "$WIFI_MODULE" "$BT_FW" "$BT_CFG"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: Missing $f"
        MISSING=1
    else
        echo "  ✓ $(basename "$f") ($(ls -lh "$f" | awk '{print $5}'))"
    fi
done
[ "$MISSING" -eq 0 ] || { echo ""; echo "Place missing files in sources/ directory."; exit 1; }

mkdir -p "$SCRIPT_DIR/output"
echo ""

# ── Step 1: Copy original MS image ────────────────────────────────────
echo "--- Copying original MS image (this takes a minute)... ---"
cp "$MS_IMAGE" "$OUTPUT"
echo "Copy done: $(ls -lh "$OUTPUT" | awk '{print $5}')"

# ── Step 2: Set up loop device ────────────────────────────────────────
echo ""
echo "--- Setting up loop device ---"
LOOPDEV=$(losetup --find --show --partscan "$OUTPUT")
echo "Loop device: $LOOPDEV"

# Wait for partition devices
sleep 1
partprobe "$LOOPDEV" 2>/dev/null || true
sleep 1

echo ""
echo "--- Partition table ---"
fdisk -l "$OUTPUT" 2>/dev/null | grep "^$OUTPUT"
echo ""
lsblk "$LOOPDEV"

# ── Step 3: Patch GRUB config on EFI-A (p1) ──────────────────────────
echo ""
echo "--- Patching GRUB config on EFI-A (p1) ---"
EFI_MNT=$(mktemp -d)
mount "${LOOPDEV}p1" "$EFI_MNT"

# Find and backup original GRUB config
GRUB_CFG=$(find "$EFI_MNT" -name "grub.cfg" -type f | head -1)
if [ -z "$GRUB_CFG" ]; then
    echo "ERROR: grub.cfg not found on EFI partition!"
    umount "$EFI_MNT"
    losetup -d "$LOOPDEV"
    exit 1
fi

echo "Original GRUB config:"
cat "$GRUB_CFG"
cp "$GRUB_CFG" "${GRUB_CFG}.orig"

GRUB_CONTENT='# Debian on Azure Percept DK
# Patched from original Mariner GRUB config.
# systemd.unified_cgroup_hierarchy=0 forces cgroup v1 — required because the
# MS kernel lacks CONFIG_BPF_SYSCALL, and cgroup v2 device controller needs BPF.
# Without this, Docker containers fail with "bpf_prog_query(BPF_CGROUP_DEVICE) failed".
set timeout=0
set root=(hd0,gpt3)
set efiroot=(hd0,gpt1)

menuentry "Debian" {
    linux /boot/vmlinuz root=/dev/mmcblk0p3 rw rootwait systemd.unified_cgroup_hierarchy=0 console=ttymxc0,115200 net.ifnames=0 loglevel=7
    devicetree $efiroot/pe100.dtb
}'

echo "$GRUB_CONTENT" > "$GRUB_CFG"

# Also ensure /boot/grub2/grub.cfg exists (GRUB binary has prefix=/boot/grub2)
mkdir -p "$EFI_MNT/boot/grub2"
echo "$GRUB_CONTENT" > "$EFI_MNT/boot/grub2/grub.cfg"

echo ""
echo "New GRUB config:"
cat "$GRUB_CFG"

# Verify DTB and bootloader are present
echo ""
[ -f "$EFI_MNT/pe100.dtb" ] && echo "✓ pe100.dtb present" || echo "✗ pe100.dtb MISSING"
ls "$EFI_MNT"/EFI/BOOT/bootaa64.efi >/dev/null 2>&1 && echo "✓ shim present" || echo "✗ shim MISSING"
ls "$EFI_MNT"/EFI/BOOT/grubaa64.efi >/dev/null 2>&1 && echo "✓ GRUB binary present" || echo "✗ GRUB binary MISSING"

umount "$EFI_MNT"
rmdir "$EFI_MNT"

# ── Step 4: Replace rootfs on p3 ─────────────────────────────────────
echo ""
echo "--- Replacing rootfs-A (p3) with Debian ---"
ROOTFS_MNT=$(mktemp -d)

echo "Formatting p3 as ext4..."
mkfs.ext4 -F -q "${LOOPDEV}p3"

mount "${LOOPDEV}p3" "$ROOTFS_MNT"

echo "Extracting Debian rootfs..."
tar --zstd -xf "$ROOTFS_TAR" -C "$ROOTFS_MNT"

# ── Step 5: Install Mariner kernel ───────────────────────────────────
echo "Installing Mariner kernel at /boot/vmlinuz..."
cp "$MARINER_KERNEL" "$ROOTFS_MNT/boot/vmlinuz"
cp "$MARINER_KERNEL" "$ROOTFS_MNT/boot/vmlinuz-5.4.3-mariner"

# ── Step 6: Install kernel modules from original MS image ────────────
echo "Installing kernel modules (647 from original MS image)..."
mkdir -p "$ROOTFS_MNT/lib/modules"
tar xzf "$MS_MODULES" -C "$ROOTFS_MNT/lib/modules/"
# Remove broken source symlink
rm -f "$ROOTFS_MNT/lib/modules/5.4.3-26.cm1/source"

# ── Step 7: Install decompressed 88x2ce Wi-Fi module ─────────────────
echo "Installing decompressed 88x2ce.ko Wi-Fi driver..."
cp "$WIFI_MODULE" "$ROOTFS_MNT/lib/modules/5.4.3-26.cm1/kernel/drivers/net/wireless/88x2ce.ko"

# ── Step 7b: Install Bluetooth firmware from original MS image ────
echo "Installing RTL8822CU Bluetooth firmware..."
mkdir -p "$ROOTFS_MNT/lib/firmware/rtl_bt"
cp "$BT_FW" "$ROOTFS_MNT/lib/firmware/rtl_bt/rtl8822cu_fw"
cp "$BT_CFG" "$ROOTFS_MNT/lib/firmware/rtl_bt/rtl8822cu_config"
ln -sf rtl8822cu_fw "$ROOTFS_MNT/lib/firmware/rtl_bt/rtl8822cu_fw.bin"
ln -sf rtl8822cu_config "$ROOTFS_MNT/lib/firmware/rtl_bt/rtl8822cu_config.bin"

# ── Step 8: Configure auto-load of Wi-Fi module ──────────────────
echo "Configuring Wi-Fi module auto-load..."
mkdir -p "$ROOTFS_MNT/etc/modules-load.d"
echo "88x2ce" > "$ROOTFS_MNT/etc/modules-load.d/wifi.conf"

# ── Step 8b: Install post-flash script on device ─────────────────────
echo "Installing post_flash.sh to /root/..."
cp "$SCRIPT_DIR/post_flash.sh" "$ROOTFS_MNT/root/post_flash.sh"
chmod +x "$ROOTFS_MNT/root/post_flash.sh"

# ── Step 9: Write correct fstab ──────────────────────────────────────
echo "Writing fstab..."
cat > "$ROOTFS_MNT/etc/fstab" << 'FSTABEOF'
# /etc/fstab - Debian on Azure Percept DK
/dev/mmcblk0p3  /           ext4    errors=remount-ro,noatime   0   1
/dev/mmcblk0p1  /boot/efi   vfat    umask=0077                  0   1
FSTABEOF

# ── Step 10: Enable essential services ────────────────────────────────
echo "Enabling services..."
# SSH
ln -sf /lib/systemd/system/ssh.service \
    "$ROOTFS_MNT/etc/systemd/system/multi-user.target.wants/ssh.service" 2>/dev/null || true

# Serial console
mkdir -p "$ROOTFS_MNT/etc/systemd/system/getty.target.wants"
ln -sf /lib/systemd/system/serial-getty@.service \
    "$ROOTFS_MNT/etc/systemd/system/getty.target.wants/serial-getty@ttymxc0.service" 2>/dev/null || true

# systemd-networkd
ln -sf /lib/systemd/system/systemd-networkd.service \
    "$ROOTFS_MNT/etc/systemd/system/multi-user.target.wants/systemd-networkd.service" 2>/dev/null || true
ln -sf /lib/systemd/system/systemd-networkd-wait-online.service \
    "$ROOTFS_MNT/etc/systemd/system/network-online.target.wants/systemd-networkd-wait-online.service" 2>/dev/null || true

# systemd-resolved (if installed in rootfs)
if [ -f "$ROOTFS_MNT/lib/systemd/system/systemd-resolved.service" ]; then
    ln -sf /lib/systemd/system/systemd-resolved.service \
        "$ROOTFS_MNT/etc/systemd/system/sysinit.target.wants/systemd-resolved.service" 2>/dev/null || true
    # Set up resolv.conf symlink for resolved
    rm -f "$ROOTFS_MNT/etc/resolv.conf"
    ln -sf ../run/systemd/resolve/stub-resolv.conf "$ROOTFS_MNT/etc/resolv.conf"
    echo "✓ systemd-resolved enabled"
else
    # Fallback: static resolv.conf
    rm -f "$ROOTFS_MNT/etc/resolv.conf"
    printf 'nameserver 8.8.8.8\nnameserver 8.8.4.4\n' > "$ROOTFS_MNT/etc/resolv.conf"
    echo "⚠ systemd-resolved not in rootfs, using static resolv.conf"
fi

# ── Summary ───────────────────────────────────────────────────────────
echo ""
echo "=== Rootfs contents ==="
echo "Kernel: $(ls -lh "$ROOTFS_MNT/boot/vmlinuz" | awk '{print $5}')"
echo "Modules: $(find "$ROOTFS_MNT/lib/modules" -name '*.ko*' | wc -l) files"
echo "Init: $(readlink "$ROOTFS_MNT/sbin/init" 2>/dev/null || echo 'direct')"
echo "SSH: $(ls "$ROOTFS_MNT/usr/sbin/sshd" 2>/dev/null && echo 'yes' || echo 'no')"
echo ""
df -h "$ROOTFS_MNT"

umount "$ROOTFS_MNT"
rmdir "$ROOTFS_MNT"

# ── Cleanup loop device ──────────────────────────────────────────────
losetup -d "$LOOPDEV"

echo ""
echo "================================================================="
echo "  Image built successfully!"
echo "================================================================="
echo ""
ls -lh "$OUTPUT"
echo ""
echo "Next step: Flash with UUU"
echo "  1. Put device in USB recovery mode (hold recovery button, power cycle)"
echo "  2. Run:  uuu.exe flash.uuu"
echo "  3. After flash, SSH to root@<device-ip> (use the password you set in config.sh)"
echo "  4. Run:  bash /root/post_flash.sh"
