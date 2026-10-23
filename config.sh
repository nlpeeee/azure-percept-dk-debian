#!/bin/bash
# ============================================================================
# Azure Percept DK — Production Flash Configuration
# Edit these values before running 00_build_rootfs.sh
# ============================================================================

# ── Credentials ────────────────────────────────────────────────────────────
# Leave the passwords empty: 00_build_rootfs.sh asks for them during the build,
# so they never sit in this file. Add SSH keys on the device after first boot.
ROOT_PASSWORD=""
NEW_USER="percept"
NEW_USER_PASSWORD=""

# ── Network ────────────────────────────────────────────────────────────────
HOSTNAME="percept-dk"

# Default is pure DHCP. A static IP example config is installed on the device
# at /etc/systemd/network/25-static.network.example — rename to .network to use.
# These values are written into that example file:
STATIC_IP="192.168.1.100/24"
STATIC_GATEWAY="192.168.1.1"
STATIC_DNS="8.8.8.8 8.8.4.4"

# ── Wi-Fi (optional) ──────────────────────────────────────────────────────
# Fill these in to have Wi-Fi connect automatically on boot.
# Leave WIFI_SSID="" to skip Wi-Fi setup in the rootfs.
# Note: Wi-Fi requires the 88x2ce kernel module (handled by the build script).
WIFI_SSID=""
WIFI_PSK=""
WIFI_COUNTRY="US"

# ── Debian ─────────────────────────────────────────────────────────────────
DEBIAN_SUITE="bookworm"
DEBIAN_MIRROR="http://deb.debian.org/debian"
