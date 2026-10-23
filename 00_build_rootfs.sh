#!/bin/bash
# ============================================================================
# Azure Percept DK — Debian Production Flash
# Step 0: Build Debian Rootfs (run in WSL as root)
#
# Builds a minimal Debian Bookworm arm64 rootfs tarball via qemu-debootstrap.
# Settings come from config.sh.
#
# Usage:
#   sudo bash 00_build_rootfs.sh
#
# Prerequisites:
#   sudo apt install debootstrap qemu-user-static zstd
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/config.sh"

OUTPUT_TARBALL="$SCRIPT_DIR/sources/debian-rootfs.tar.zst"
ROOTFS_DIR="$(mktemp -d)/percept-rootfs"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC}  $*"; }
die()   { echo -e "${RED}[FAIL]${NC}  $*" >&2; exit 1; }

# ── Preflight ──────────────────────────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || die "This script must be run as root (sudo)."
for cmd in debootstrap zstd; do
    command -v "$cmd" &>/dev/null || die "'$cmd' not found. Install: sudo apt install debootstrap qemu-user-static zstd"
done
if ! command -v qemu-aarch64-static &>/dev/null && [ ! -f /usr/bin/qemu-aarch64-static ]; then
    die "qemu-aarch64-static not found. Install: sudo apt install qemu-user-static"
fi

mkdir -p "$SCRIPT_DIR/sources"

# ── Passwords (asked for here unless set in config.sh) ─────────────────────
prompt_password() {
    local label="$1" var="$2" p1 p2
    [ -n "${!var:-}" ] && return
    [ -t 0 ] || die "${var} is empty and there is no terminal to ask on. Set it in config.sh."
    while true; do
        read -rsp "  Password for ${label}: " p1; echo
        read -rsp "  Confirm password for ${label}: " p2; echo
        if [ -z "$p1" ]; then
            echo "  Password cannot be empty."
        elif [ "$p1" != "$p2" ]; then
            echo "  Passwords do not match."
        else
            printf -v "$var" '%s' "$p1"
            return
        fi
    done
}

echo ""
info "Choose the login passwords for this image:"
prompt_password "root" ROOT_PASSWORD
prompt_password "${NEW_USER}" NEW_USER_PASSWORD

echo ""
echo "=========================================================="
echo "  Debian ${DEBIAN_SUITE} arm64 Rootfs Builder"
echo "  Target: Azure Percept DK (NXP i.MX8MQ)"
echo "=========================================================="
echo "  Output     : ${OUTPUT_TARBALL}"
echo "  Users      : root, ${NEW_USER} (passwords set)"
echo "  Static IP  : ${STATIC_IP} (example only, DHCP default)"
echo "  Wi-Fi SSID : ${WIFI_SSID:-<not configured>}"
echo "=========================================================="
echo ""

cleanup() {
    info "Cleaning up build directory..."
    rm -rf "$(dirname "$ROOTFS_DIR")"
}
trap cleanup EXIT

# ── 1. Debootstrap ────────────────────────────────────────────────────────
info "[1/10] Running debootstrap (this takes a few minutes)..."
qemu-debootstrap --arch=arm64 \
    --include=systemd,dbus \
    "${DEBIAN_SUITE}" "${ROOTFS_DIR}" "${DEBIAN_MIRROR}"
ok "Debootstrap complete."

# ── 2. Hostname ───────────────────────────────────────────────────────────
info "[2/10] Setting hostname to '${HOSTNAME}'..."
echo "${HOSTNAME}" > "${ROOTFS_DIR}/etc/hostname"
cat > "${ROOTFS_DIR}/etc/hosts" <<EOF
127.0.0.1       localhost
127.0.1.1       ${HOSTNAME}

::1             localhost ip6-localhost ip6-loopback
ff02::1         ip6-allnodes
ff02::2         ip6-allrouters
EOF
ok "Hostname configured."

# ── 3. Networking ─────────────────────────────────────────────────────────
info "[3/10] Configuring network (DHCP + static example)..."
mkdir -p "${ROOTFS_DIR}/etc/systemd/network"

# Wired — pure DHCP
cat > "${ROOTFS_DIR}/etc/systemd/network/20-wired.network" <<EOF
[Match]
Name=eth* en*

[Network]
DHCP=yes
DNS=8.8.8.8 8.8.4.4

[DHCP]
RouteMetric=100
UseDNS=yes
UseNTP=yes
EOF

# Static IP example — rename to .network to activate
cat > "${ROOTFS_DIR}/etc/systemd/network/25-static.network.example" <<EOF
# To use a static IP instead of DHCP:
# 1. Rename this file: mv /etc/systemd/network/25-static.network.example 25-static.network
# 2. Edit the Address and Gateway below
# 3. Restart networking: systemctl restart systemd-networkd
#
# To go back to DHCP:
# 1. mv /etc/systemd/network/25-static.network /etc/systemd/network/25-static.network.example
# 2. systemctl restart systemd-networkd

[Match]
Name=eth1

[Network]
Address=${STATIC_IP}
Gateway=${STATIC_GATEWAY}
DNS=${STATIC_DNS}
EOF

# Wi-Fi network config (always create it; the driver may or may not be loaded)
cat > "${ROOTFS_DIR}/etc/systemd/network/30-wifi.network" <<EOF
[Match]
Name=wlan* mlan*

[Network]
DHCP=yes

[DHCP]
RouteMetric=200
EOF

# Wi-Fi WPA config (optional)
if [ -n "${WIFI_SSID}" ]; then
    info "  Configuring Wi-Fi for SSID: ${WIFI_SSID}"
    mkdir -p "${ROOTFS_DIR}/etc/wpa_supplicant"
    cat > "${ROOTFS_DIR}/etc/wpa_supplicant/wpa_supplicant-wlan0.conf" <<EOF
ctrl_interface=/var/run/wpa_supplicant
update_config=1
country=${WIFI_COUNTRY}

network={
    ssid="${WIFI_SSID}"
    psk="${WIFI_PSK}"
    key_mgmt=WPA-PSK
}
EOF
    chmod 600 "${ROOTFS_DIR}/etc/wpa_supplicant/wpa_supplicant-wlan0.conf"
fi

ok "Network configured."

# ── 4. Install packages ──────────────────────────────────────────────────
info "[4/10] Installing packages (SSH, networking, Docker, essentials)..."

# Temporary DNS for apt
echo "nameserver 8.8.8.8" > "${ROOTFS_DIR}/etc/resolv.conf"

# Full APT sources with security updates
cat > "${ROOTFS_DIR}/etc/apt/sources.list" <<EOF
deb ${DEBIAN_MIRROR} ${DEBIAN_SUITE} main contrib non-free-firmware
deb ${DEBIAN_MIRROR} ${DEBIAN_SUITE}-updates main contrib non-free-firmware
deb http://security.debian.org/debian-security ${DEBIAN_SUITE}-security main contrib non-free-firmware
EOF

chroot "${ROOTFS_DIR}" /bin/bash -c "
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -q
    apt-get install -y --no-install-recommends \
        openssh-server \
        sudo \
        nano \
        less \
        wget \
        curl \
        git \
        iproute2 \
        iputils-ping \
        net-tools \
        wpasupplicant \
        wireless-tools \
        iw \
        wireless-regdb \
        bluez \
        bluetooth \
        systemd-resolved \
        systemd-timesyncd \
        dbus \
        ca-certificates \
        locales \
        usbutils \
        pciutils \
        kmod \
        i2c-tools \
        fdisk \
        parted \
        e2fsprogs \
        htop \
        bash-completion \
        python3 \
        python3-pip \
        python3-venv \
        build-essential \
        libusb-1.0-0 \
        docker.io \
        containerd \
        iptables \
        unattended-upgrades \
        apt-listchanges
"
ok "Packages installed."

# ── 5. SSH configuration ─────────────────────────────────────────────────
info "[5/10] Configuring SSH for headless access..."

# Allow root login + password auth for initial headless access
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/'                "${ROOTFS_DIR}/etc/ssh/sshd_config"
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/'  "${ROOTFS_DIR}/etc/ssh/sshd_config"

# Host keys are generated on each device's first boot, so boards flashed from
# the same image never share keys. The image's own keys are removed at pack time.
cat > "${ROOTFS_DIR}/etc/systemd/system/ssh-hostkeys.service" <<'EOF'
[Unit]
Description=Generate unique SSH host keys on first boot
Before=ssh.service
ConditionPathExists=!/etc/ssh/ssh_host_ed25519_key

[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A

[Install]
WantedBy=multi-user.target
EOF
chroot "${ROOTFS_DIR}" systemctl enable ssh-hostkeys.service

ok "SSH configured."

# ── 5b. iptables-legacy (kernel lacks nf_tables module) ──────────────────
info "[5b/10] Switching to iptables-legacy (kernel has no nf_tables)..."
chroot "${ROOTFS_DIR}" /bin/bash -c "
    update-alternatives --set iptables /usr/sbin/iptables-legacy 2>/dev/null || true
    update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy 2>/dev/null || true
"
ok "iptables-legacy selected (required for Docker)."

# ── 5c. Journal size limit ────────────────────────────────────────────────
info "[5c/10] Limiting journal size to 50M..."
mkdir -p "${ROOTFS_DIR}/etc/systemd/journald.conf.d"
cat > "${ROOTFS_DIR}/etc/systemd/journald.conf.d/size.conf" <<EOF
[Journal]
SystemMaxUse=50M
SystemMaxFileSize=10M
EOF
ok "Journal limited."

# ── 5d. Unattended upgrades ───────────────────────────────────────────────
info "[5d/10] Configuring unattended security upgrades..."
mkdir -p "${ROOTFS_DIR}/etc/apt/apt.conf.d"
cat > "${ROOTFS_DIR}/etc/apt/apt.conf.d/20auto-upgrades" <<EOF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
ok "Unattended upgrades configured."

# ── 6. Users & passwords ─────────────────────────────────────────────────
info "[6/10] Creating users..."

echo "root:${ROOT_PASSWORD}" | chroot "${ROOTFS_DIR}" chpasswd

chroot "${ROOTFS_DIR}" /bin/bash -c "
    useradd -m -s /bin/bash -G sudo,dialout,audio,video,plugdev ${NEW_USER}
"
echo "${NEW_USER}:${NEW_USER_PASSWORD}" | chroot "${ROOTFS_DIR}" chpasswd

echo "%sudo ALL=(ALL:ALL) ALL" > "${ROOTFS_DIR}/etc/sudoers.d/sudo-group"
chmod 440 "${ROOTFS_DIR}/etc/sudoers.d/sudo-group"

ok "Users created: root, ${NEW_USER} (sudo)."

# ── 7. Serial console ────────────────────────────────────────────────────
info "[7/10] Enabling serial console & service symlinks..."

# Note: fstab and service enable/disable are handled by 01_build_image.sh,
# but we pre-enable some here since they run in chroot properly.
chroot "${ROOTFS_DIR}" /bin/bash -c "
    systemctl enable systemd-networkd 2>/dev/null || true
    systemctl enable systemd-resolved 2>/dev/null || true
    systemctl enable ssh 2>/dev/null || true
    systemctl enable serial-getty@ttymxc0.service 2>/dev/null || true
"
# Only start Wi-Fi when a config exists; otherwise the unit fails every boot
if [ -n "${WIFI_SSID}" ]; then
    chroot "${ROOTFS_DIR}" systemctl enable wpa_supplicant@wlan0 2>/dev/null || true
fi

# securetty
if [ -f "${ROOTFS_DIR}/etc/securetty" ]; then
    grep -q "^ttymxc0$" "${ROOTFS_DIR}/etc/securetty" || echo "ttymxc0" >> "${ROOTFS_DIR}/etc/securetty"
fi

ok "Services enabled."

# ── 8. Locale, timezone, MOTD ────────────────────────────────────────────
info "[8/10] Setting locale, timezone, MOTD..."

chroot "${ROOTFS_DIR}" /bin/bash -c "
    sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen
    locale-gen
    echo 'LANG=en_US.UTF-8' > /etc/default/locale
    ln -sf /usr/share/zoneinfo/UTC /etc/localtime
"

cat > "${ROOTFS_DIR}/etc/motd" <<'MOTD'

  ╔════════════════════════════════════════════════════════════╗
  ║  Azure Percept DK — Debian Bookworm (arm64)               ║
  ╚════════════════════════════════════════════════════════════╝

MOTD

ok "Locale, timezone, MOTD set."

# ── 9/10: Swap file (created at first boot via post_flash.sh) ────────────
info "[9/10] Swap: will be created by post_flash.sh at first boot."
ok "(512MB swap configured in post_flash.sh)"

# ── 10/10: Summary ────────────────────────────────────────────────────────
info "[10/10] Rootfs build summary:"
echo "  - Debian ${DEBIAN_SUITE} arm64"
echo "  - Pure DHCP (static IP example at /etc/systemd/network/25-static.network.example)"
echo "  - Docker + containerd (iptables-legacy)"
echo "  - Unattended security upgrades"
echo "  - Journal limited to 50M"
echo "  - Python 3 + pip + venv + build-essential"
echo "  - Swap file (512MB, created by post_flash.sh)"

# ── Cleanup & pack ────────────────────────────────────────────────────────
info "Cleaning up..."
chroot "${ROOTFS_DIR}" /bin/bash -c "
    apt-get clean
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
"

# Restore resolv.conf to resolved symlink
ln -sf /run/systemd/resolve/stub-resolv.conf "${ROOTFS_DIR}/etc/resolv.conf"

# Per-device identity: every board generates its own on first boot.
# A shared machine-id would give every board the same DHCP client ID.
rm -f "${ROOTFS_DIR}"/etc/ssh/ssh_host_*
: > "${ROOTFS_DIR}/etc/machine-id"
if [ -d "${ROOTFS_DIR}/var/lib/dbus" ]; then
    ln -sf /etc/machine-id "${ROOTFS_DIR}/var/lib/dbus/machine-id"
fi

info "Creating tarball: ${OUTPUT_TARBALL} ..."
tar -C "${ROOTFS_DIR}" --zstd -cf "${OUTPUT_TARBALL}" .

SIZE=$(du -h "${OUTPUT_TARBALL}" | cut -f1)
echo ""
echo "=========================================================="
echo -e "  ${GREEN}ROOTFS BUILD COMPLETE${NC}"
echo "=========================================================="
echo "  Tarball  : ${OUTPUT_TARBALL}  (${SIZE})"
echo ""
echo "  Next step: sudo bash 01_build_image.sh"
echo "=========================================================="
