#!/bin/sh
# Runs in the launcher's rescue mode (stock 5.4 kernel, BusyBox + the bundled
# Bookworm mke2fs/tar/gzip). Never runs trixie binaries: they cannot create
# threads on this kernel.
#
#   rescue-install.sh hash-p3          sha256 of the whole p3 partition
#   rescue-install.sh install <TAR.gz  DESTROYS p3: mkfs + extract trixie tarball
#                                       (stdin); expects /run/trixie.sha256
#   rescue-install.sh arm              ESP: production launcher.conf + grub.cfg,
#                                       failcount 0, percept_tries=4; expects
#                                       /run/launcher.conf.trixie, /run/grub.cfg.production
#
# Upload files with:  ssh root@192.168.1.60 'cat >/run/NAME' <NAME
set -eu
P3=/dev/mmcblk0p3
ESP_DEV=/dev/mmcblk0p1
UUID=a842734f-25d2-4bc4-8e1f-11ede151471f
MNT=/mnt/p3
ESP=/mnt/esp
RELEASE=6.12.113+deb13-arm64
KERNEL_SHA=391a3b39b265585ed094fba56994c4613a3c41fc65b9670e42da5a66d63ca07e
STOCK_SHA=fec6f292e734ab81c056a28ab0c3940ec7f00fcd39cec417cac9da52bb3f7ef2

# Only in launcher rescue mode, on the stock kernel, with p3 not mounted.
[ "$(uname -r)" = 5.4.3-26.cm1 ] || { echo 'not the stock kernel' >&2; exit 1; }
[ -s /run/launcher.log ] && grep -q 'rescue_ready' /run/launcher.log || { echo 'not launcher rescue mode' >&2; exit 1; }
if grep -q "^$P3 " /proc/mounts; then echo 'p3 is mounted' >&2; exit 1; fi

file_sha() { sha256sum "$1" | cut -d' ' -f1; }

case "${1:-}" in
hash-p3)
    dd if="$P3" bs=1M 2>/dev/null | sha256sum | cut -d' ' -f1
    ;;
install)
    want=$(cut -d' ' -f1 /run/trixie.sha256)
    [ "${#want}" = 64 ]
    blockdev --setrw "$P3"
    # Bookworm's mke2fs.conf defaults give the same ext4 features as the old p3
    # (no orphan_file/metadata_csum_seed), which GRUB 2.03 and 5.4 can read.
    /usr/sbin/mke2fs -t ext4 -F -q -U "$UUID" -L trixie "$P3"
    mkdir -p "$MNT"
    mount -t ext4 "$P3" "$MNT"
    rm -f /run/tar.fifo
    mkfifo /run/tar.fifo
    sha256sum /run/tar.fifo >/run/tar.got &
    hasher=$!
    tee /run/tar.fifo | /usr/bin/gzip -dc | /usr/bin/tar --xattrs --xattrs-include='*' --acls \
        --numeric-owner -xpf - -C "$MNT"
    wait "$hasher"
    got=$(cut -d' ' -f1 /run/tar.got)
    [ "$got" = "$want" ] || { echo "tarball sha256 mismatch: $got" >&2; umount "$MNT"; exit 1; }
    [ "$(file_sha "$MNT/boot/vmlinuz-$RELEASE")" = "$KERNEL_SHA" ]
    [ "$(file_sha "$MNT/boot/vmlinuz-5.4.3-mariner")" = "$STOCK_SHA" ]
    [ -s "$MNT/boot/initrd.img-$RELEASE" ]
    [ -L "$MNT/vmlinuz" ]
    [ -L "$MNT/initrd.img" ]
    grep -q "UUID=$UUID" "$MNT/etc/fstab"
    # Newer boot-ok (also re-arms GRUB's countdown) than the one in the tarball.
    if [ -s /run/percept-boot-ok ]; then
        cp /run/percept-boot-ok "$MNT/usr/local/sbin/percept-boot-ok"
        chmod 755 "$MNT/usr/local/sbin/percept-boot-ok"
    fi
    sync
    umount "$MNT"
    sync
    echo "INSTALLED trixie on $P3 uuid=$UUID tarball=$got"
    ;;
arm)
    [ -s /run/launcher.conf.trixie ]
    [ -s /run/grub.cfg.production ]
    mkdir -p "$ESP"
    grep -q " $ESP " /proc/mounts || mount -t vfat "$ESP_DEV" "$ESP"
    G=$ESP/boot/grub2
    cp /run/launcher.conf.trixie "$ESP/percept/launcher.conf"
    cp /run/grub.cfg.production "$G/grub.cfg"
    printf '0\n' >"$ESP/percept/failcount"
    printf '# GRUB Environment Block\npercept_tries=4\n' >/run/grubenv
    n=$(wc -c </run/grubenv)
    head -c $((1024 - n)) /dev/zero | tr '\0' '#' >>/run/grubenv
    [ "$(wc -c </run/grubenv)" = 1024 ]
    cp /run/grubenv "$G/grubenv"
    sync
    sha256sum "$ESP/percept/launcher.conf" "$G/grub.cfg" "$G/grubenv"
    umount "$ESP"
    sync
    echo "ARMED: next boot kexecs trixie"
    ;;
*)
    echo "usage: $0 hash-p3|install|arm" >&2; exit 2 ;;
esac
