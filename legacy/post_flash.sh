#!/bin/bash
# ============================================================================
# Azure Percept DK — Post-Flash Setup
# Run on the device after first boot via SSH:
#
#   ssh root@192.168.1.100  (or DHCP address)
#   bash /root/post_flash.sh
#
# This script:
#   1. Expands rootfs partition to fill all available eMMC space
#   2. Verifies Wi-Fi module is loaded
#   3. Optionally connects to Wi-Fi
#   4. Creates 512MB swap file
#   5. Verifies Docker is running
#   6. Shows system status
# ============================================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${RED}[WARN]${NC}  $*"; }

echo ""
echo "=========================================================="
echo "  Azure Percept DK — Post-Flash Setup"
echo "=========================================================="
echo ""

# ── 1. Expand rootfs to fill eMMC ────────────────────────────────────────
info "[1/6] Expanding rootfs to fill eMMC..."

DISK="/dev/mmcblk0"
ROOT_PART="/dev/mmcblk0p3"
ROOT_PARTNUM=3

# Get current partition info
CURRENT_SIZE=$(lsblk -b -n -o SIZE "$ROOT_PART" 2>/dev/null)
DISK_SIZE=$(lsblk -b -n -o SIZE "$DISK" 2>/dev/null | head -1)

if [ -n "$CURRENT_SIZE" ] && [ -n "$DISK_SIZE" ]; then
    CURRENT_GB=$(echo "scale=1; $CURRENT_SIZE / 1073741824" | bc 2>/dev/null || echo "?")
    DISK_GB=$(echo "scale=1; $DISK_SIZE / 1073741824" | bc 2>/dev/null || echo "?")
    info "Current rootfs: ${CURRENT_GB}G on ${DISK_GB}G disk"
fi

# Check if p4 and p5 still exist (they need to be removed first)
P4_EXISTS=$(sfdisk -d "$DISK" 2>/dev/null | grep -c "p4" || true)
P5_EXISTS=$(sfdisk -d "$DISK" 2>/dev/null | grep -c "p5" || true)

if [ "$P4_EXISTS" -gt 0 ] || [ "$P5_EXISTS" -gt 0 ]; then
    info "Removing unused partitions p4/p5 to free space..."

    # Save current partition table
    sfdisk -d "$DISK" > /tmp/ptable_backup.txt

    # Delete p4 and p5, keep p1-p3
    sfdisk -d "$DISK" | grep -v "p4\|p5" | sfdisk --force "$DISK" 2>/dev/null

    # Now expand p3 to fill all remaining space
    info "Expanding partition 3 to fill disk..."
    echo ", +" | sfdisk -N "$ROOT_PARTNUM" "$DISK" --force 2>/dev/null

    partprobe "$DISK" 2>/dev/null || true
    sleep 1
else
    # p4/p5 already gone — just try expanding p3
    CURRENT_END=$(sfdisk -d "$DISK" 2>/dev/null | grep "p3" | grep -oP 'size=\s*\K[0-9]+')
    info "Partitions p4/p5 already removed. Checking if p3 can grow..."
    echo ", +" | sfdisk -N "$ROOT_PARTNUM" "$DISK" --force 2>/dev/null || true
    partprobe "$DISK" 2>/dev/null || true
    sleep 1
fi

# Resize the filesystem (works online on ext4)
info "Resizing ext4 filesystem..."
resize2fs "$ROOT_PART" 2>/dev/null || true

# Show result
NEW_SIZE=$(df -h "$ROOT_PART" | tail -1 | awk '{print $2}')
USED=$(df -h "$ROOT_PART" | tail -1 | awk '{print $3}')
AVAIL=$(df -h "$ROOT_PART" | tail -1 | awk '{print $4}')
ok "Rootfs: ${NEW_SIZE} total, ${USED} used, ${AVAIL} available"

# ── 2. Verify kernel modules ─────────────────────────────────────────────
echo ""
info "[2/6] Checking kernel modules..."

KVER=$(uname -r)
MOD_COUNT=$(find /lib/modules/$KVER -name '*.ko*' 2>/dev/null | wc -l)
info "Kernel: $KVER  Modules: $MOD_COUNT"

# Check Wi-Fi module
if lsmod | grep -q "88x2ce"; then
    ok "Wi-Fi module 88x2ce is loaded"
else
    warn "Wi-Fi module 88x2ce not loaded, trying to load..."
    modprobe 88x2ce 2>/dev/null || insmod /lib/modules/$KVER/kernel/drivers/net/wireless/88x2ce.ko 2>/dev/null || true
    sleep 2
    if lsmod | grep -q "88x2ce"; then
        ok "Wi-Fi module 88x2ce loaded successfully"
    else
        warn "Failed to load 88x2ce — check dmesg for errors"
    fi
fi

# List wireless interfaces
WLAN_IFS=$(ip link show 2>/dev/null | grep -oP 'wlan[0-9]+' | head -5)
if [ -n "$WLAN_IFS" ]; then
    ok "Wireless interfaces: $WLAN_IFS"
else
    warn "No wireless interfaces detected"
fi

# ── 3. Wi-Fi connection (interactive) ────────────────────────────────────
echo ""
info "[3/6] Wi-Fi setup..."

WPA_CONF="/etc/wpa_supplicant/wpa_supplicant-wlan0.conf"
if [ -f "$WPA_CONF" ]; then
    CONFIGURED_SSID=$(grep 'ssid=' "$WPA_CONF" | head -1 | sed 's/.*ssid="\(.*\)"/\1/')
    info "Wi-Fi already configured for SSID: ${CONFIGURED_SSID}"
    info "To connect: systemctl restart wpa_supplicant@wlan0"
else
    info "No Wi-Fi configured. To set up Wi-Fi later:"
    echo ""
    echo "  # Scan for networks:"
    echo "  iw dev wlan0 scan | grep SSID"
    echo ""
    echo "  # Create config:"
    echo "  wpa_passphrase \"YourSSID\" \"YourPassword\" > /etc/wpa_supplicant/wpa_supplicant-wlan0.conf"
    echo ""
    echo "  # Connect:"
    echo "  systemctl enable --now wpa_supplicant@wlan0"
fi

# ── 4. Create swap file ───────────────────────────────────────────────────
echo ""
info "[4/6] Creating swap file (512MB)..."
if swapon --show | grep -q '/swapfile'; then
    ok "Swap already active"
else
    if [ ! -f /swapfile ]; then
        dd if=/dev/zero of=/swapfile bs=1M count=512 status=progress
        chmod 600 /swapfile
        mkswap /swapfile
    fi
    swapon /swapfile
    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
    ok "Swap file created and enabled"
fi

# ── 5. Verify Docker ─────────────────────────────────────────────────────
echo ""
info "[5/6] Verifying Docker..."
if systemctl is-active --quiet docker; then
    ok "Docker is running"
    docker --version
else
    warn "Docker not running, starting..."
    systemctl start docker 2>/dev/null || true
    sleep 2
    if systemctl is-active --quiet docker; then
        ok "Docker started successfully"
    else
        warn "Docker failed to start — check: journalctl -u docker"
    fi
fi

# ── 6. System status ─────────────────────────────────────────────────────
echo ""
info "[6/6] System status..."
echo ""
echo "  Hostname   : $(hostname)"
echo "  Kernel     : $(uname -r)"
echo "  Uptime     : $(uptime -p)"
echo "  Memory     : $(free -h | awk '/^Mem:/ {printf "%s / %s", $3, $2}')"
echo ""
echo "  Network interfaces:"
ip -br addr 2>/dev/null | while read -r line; do
    echo "    $line"
done
echo ""
echo "  Disk usage:"
df -h / /boot/efi 2>/dev/null | tail -n +2 | while read -r line; do
    echo "    $line"
done
echo ""
echo "  Swap       : $(swapon --show --noheadings 2>/dev/null | awk '{print $3}' || echo 'none')"
echo "  Docker     : $(systemctl is-active docker 2>/dev/null || echo 'inactive')"
echo "  Loaded modules: $(lsmod | wc -l)"
echo "  Running services: $(systemctl list-units --state=running --no-legend 2>/dev/null | wc -l)"
echo ""
echo "=========================================================="
echo "  Post-flash setup complete!"
echo "=========================================================="
echo ""
echo "  Next steps:"
echo "    1. Change passwords:  passwd root"
echo "    2. Set up Wi-Fi (if not already configured)"
echo "    3. Disable root SSH login when ready:"
echo "       sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config"
echo "       systemctl restart ssh"
echo ""
