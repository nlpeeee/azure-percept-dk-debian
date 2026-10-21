#!/bin/bash
# Stage A, on Bookworm under the stock kernel: debootstrap --foreign a clean
# Debian trixie arm64 tree and stage the inputs stage-b.sh needs.
#
# Trixie binaries that create threads crash on the stock 5.4 kernel (see
# docs/trixie-install.md), so nothing from trixie is executed here: --foreign
# only downloads and unpacks with Bookworm's tools. stage-b.sh runs later in a
# chroot under the Debian 6.12 kernel. Writes only below $work/trixie-build.
#
# Usage: build-trixie-rootfs.sh ROOT_UUID AUTHORIZED_KEYS_FILE
set -euo pipefail

root_uuid=${1:?trixie root filesystem UUID required}
keys=${2:?authorized_keys file required}
here=$(cd "$(dirname "$0")" && pwd)
work=/root/percept-kexec-work
out=$work/trixie-build
root=$out/root
kernel_deb=$work/debian-kernel.deb
kernel_hash=fb1d4ff8bffc992b9b7e073f9a07d1ce378c041cfba78bb8e039c15a504b3129
stock_kernel_hash=fec6f292e734ab81c056a28ab0c3940ec7f00fcd39cec417cac9da52bb3f7ef2
mirror=http://deb.debian.org/debian

[[ "$root_uuid" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]
grep -q '^ssh-' "$keys"
printf '%s  %s\n' "$kernel_hash" "$kernel_deb" | sha256sum -c -
printf '%s  %s\n' "$stock_kernel_hash" /boot/vmlinuz | sha256sum -c -
[ ! -e "$out" ] || { echo "already exists: $out" >&2; exit 1; }
# Bookworm's debootstrap 1.0.128 is too old for trixie. Use trixie's 1.0.141,
# unpacked (not installed) after checking it against the signed
# InRelease -> Packages.xz -> .deb hash chain.
bootstrap=$work/debootstrap-trixie/x
printf '%s  %s\n' 8c02cb8ad712eb67afb0d23fab175c562804cc97eda70b70cb0f3bc2a21732d7 \
    "$work/debootstrap-trixie/debootstrap_1.0.141_all.deb" | sha256sum -c -
[ -x "$bootstrap/usr/sbin/debootstrap" ]

# Everything stage B installs is fetched now; the builder boot needs no network.
# The kernel .deb itself depends only on kmod and initramfs-tools.
packages=systemd,systemd-sysv,dbus,initramfs-tools,kmod,ca-certificates,locales
packages=$packages,openssh-server,sudo,nano,less,curl,wget,iproute2,iputils-ping
packages=$packages,systemd-resolved,systemd-timesyncd,e2fsprogs,dosfstools,fdisk
packages=$packages,pciutils,usbutils,i2c-tools,htop,bash-completion,zstd

install -d -m 700 "$out"
DEBOOTSTRAP_DIR=$bootstrap/usr/share/debootstrap "$bootstrap/usr/sbin/debootstrap" \
    --foreign --arch=arm64 --include="$packages" \
    trixie "$root" "$mirror" >"$out/debootstrap-foreign.log" 2>&1
[ -x "$root/debootstrap/debootstrap" ]

# Inputs for stage B, all under /percept-build in the new tree.
b=$root/percept-build
install -d -m 700 "$b"
install -m 644 "$kernel_deb" "$b/linux-image.deb"
install -m 600 "$keys" "$b/authorized_keys"
install -m 755 "$here/stage-b.sh" "$b/stage-b.sh"
install -m 644 "$here/config.sh" "$b/config.sh"
install -m 755 "$here/percept-boot-ok" "$b/percept-boot-ok"
install -m 644 "$here/percept-boot-ok.service" "$b/percept-boot-ok.service"
install -m 644 "$here/wait-online-override.conf" "$b/wait-online-override.conf"
printf '%s\n' "$root_uuid" >"$b/root-uuid"
printf '%s\n' "$mirror" >"$b/mirror"
# GRUB still loads the signed stock kernel from p3: keep it under its own name
# and at the path the current grub.cfg uses.
install -d "$root/boot"
install -m 755 /boot/vmlinuz "$root/boot/vmlinuz-5.4.3-mariner"
ln "$root/boot/vmlinuz-5.4.3-mariner" "$root/boot/vmlinuz"
(cd "$b" && sha256sum linux-image.deb authorized_keys stage-b.sh config.sh \
    percept-boot-ok percept-boot-ok.service wait-online-override.conf root-uuid mirror >inputs.sha256)
du -sh "$root"
echo "FOREIGN READY: $root (run percept-build/stage-b.sh in a chroot under 6.12)"
