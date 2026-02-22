#!/bin/bash
# ============================================================================
# Azure Percept DK — Production Flash Configuration
# Edit these values before running 00_build_rootfs.sh
# ============================================================================

# ── Credentials ────────────────────────────────────────────────────────────
# CHANGE THESE for security! These are burned into the rootfs at build time.
ROOT_PASSWORD="percept"
NEW_USER="percept"
NEW_USER_PASSWORD="percept"

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

# ── SSH (optional) ─────────────────────────────────────────────────────────
# Paste your SSH public key for passwordless login. Leave empty to skip.
# Example: SSH_PUBKEY="ssh-ed25519 AAAA... you@yourpc"
SSH_PUBKEY=""

# ── Debian ─────────────────────────────────────────────────────────────────
DEBIAN_SUITE="bookworm"
DEBIAN_MIRROR="http://deb.debian.org/debian"
