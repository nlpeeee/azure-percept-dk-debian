#!/bin/sh
# Build the ESP launcher initramfs natively on the Percept (under Bookworm).
# Writes only below $work/launcher-BUILD; never touches the ESP, GRUB, p3's own
# system, kernel modules or the running kernel. Nothing is installed.
#
# Usage: build-launcher.sh BUILD_ID      (e.g. 20261021-01)
# Expects init and build_percept_initramfs.py next to this script, or the repo
# layout (experiments/percept-launcher + tools).
set -eu

build=${1:?build ID required, e.g. 20261021-01}
case "$build" in *[!0-9-]*|'') echo 'invalid build ID' >&2; exit 1 ;; esac
here=$(cd "$(dirname "$0")" && pwd)
work=/root/percept-kexec-work
out=$work/launcher-$build
experiment=percept-launcher-$build
max_size=6000000

init=$here/init
tool=$here/build_percept_initramfs.py
[ -r "$tool" ] || tool=$here/../../tools/build_percept_initramfs.py
busybox=$work/custom-kernel/busybox/bin/busybox
sender=$work/diagnostics-20261020/udp_log_sender
kexec=$work/quiet-purgatory-20261021-01/kexec-tools-2.0.25/build/sbin/kexec
capture=$work/sources/kexec-mod/user/capture.so
arch=$work/post-init-20261020/arch.ko
core=$work/caam-20261021-02/core.ko
upper_helper=${PERCEPT_UPPER_HELPER:-/root/percept-upper-ram/percept-fdt-upper}
thermal_helper=${PERCEPT_THERMAL_HELPER:-/root/percept-hardware-support/percept-fdt-thermal}
keys=/root/.ssh/authorized_keys

[ "$(uname -r)" = 5.4.3-26.cm1 ] || { echo 'unexpected stock kernel' >&2; exit 1; }
[ ! -e "$out" ] || { echo "already exists: $out" >&2; exit 1; }
for file in "$init" "$tool" "$busybox" "$sender" "$kexec" "$capture" "$keys" "$upper_helper" "$thermal_helper" /etc/mke2fs.conf; do
    [ -r "$file" ] || { echo "missing: $file" >&2; exit 1; }
done
printf '%s\n' \
  "c90f408f7e06c01ca280193f221a6f6fe02548cef62a0fc2eb84c8809d22f6c0  $arch" \
  "03cd9ebb8a79ac53d093e46bb0994e251a8487ca618e4ada2efe8d066dcac4e9  $core" \
  | sha256sum -c -
if [ ! -x /usr/sbin/dropbear ]; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends dropbear-bin
fi
grep -q '^ssh-' "$keys"
"$busybox" sh -n "$init"

install -d -m 700 "$out"
cp "$keys" "$out/authorized_keys"
# Host key for rescue mode, for installation as /percept/ on the ESP. The
# launcher generates a temporary one if it is absent there.
dropbearkey -t ed25519 -f "$out/dropbear_ed25519_host_key" >"$out/host-key.txt" 2>&1
dropbearkey -y -f "$out/dropbear_ed25519_host_key" >>"$out/host-key.txt" 2>&1

python3 "$tool" \
  --busybox "$busybox" --sender "$sender" --init "$init" \
  --source-boot "$(cat /proc/sys/kernel/random/boot_id)" --experiment "$experiment" \
  --output "$out/launcher.cpio.gz" \
  --binary "$kexec:sbin/kexec" \
  --binary "$capture:lib/percept/capture.so" \
  --file "$arch:lib/percept/arch.ko:0444" \
  --file "$core:lib/percept/core.ko:0444" \
  --file "$upper_helper:bin/percept-fdt-upper:0755" \
  --file "$thermal_helper:bin/percept-fdt-thermal:0755" \
  --file "$out/authorized_keys:etc/percept-launcher/authorized_keys:0600" \
  --binary /usr/sbin/dropbear:usr/sbin/dropbear \
  --binary /usr/bin/dropbearkey:usr/bin/dropbearkey \
  --binary /usr/sbin/mke2fs:usr/sbin/mke2fs \
  --symlink usr/sbin/mkfs.ext4:mke2fs \
  --file /etc/mke2fs.conf:etc/mke2fs.conf \
  --binary /usr/bin/tar:usr/bin/tar \
  --binary /usr/bin/gzip:usr/bin/gzip \
  --binary /usr/bin/zstd:usr/bin/zstd \
  --binary /usr/bin/sha256sum:usr/bin/sha256sum \
  --require-applet blockdev --require-applet umount --require-applet sync \
  --require-applet grep --require-applet rmmod --require-applet insmod \
  --require-applet cp --require-applet chmod --require-applet env \
  --require-applet sha256sum --require-applet cpio >"$out/build.log"

cd "$out"
size=$(stat -c %s launcher.cpio.gz)
[ "$size" -lt "$max_size" ] || { echo "too large: $size >= $max_size" >&2; exit 1; }
gzip -dc launcher.cpio.gz | "$busybox" cpio -tv >listing.txt 2>&1

# Every bundled program must start with only the archive's own libraries.
check=$out/check-root
install -d -m 700 "$check"
gzip -dc launcher.cpio.gz | (cd "$check" && "$busybox" cpio -id 2>/dev/null)
cp dropbear_ed25519_host_key "$check/tmp/host-key"
{
    chroot "$check" /bin/busybox sh -n /init && echo 'init: sh -n ok'
    chroot "$check" /sbin/kexec --version
    chroot "$check" /bin/busybox env LD_PRELOAD=/lib/percept/capture.so /sbin/kexec --version
    chroot "$check" /usr/sbin/dropbear -V
    chroot "$check" /usr/bin/dropbearkey -y -f /tmp/host-key
    chroot "$check" /usr/sbin/mkfs.ext4 -V
    chroot "$check" /usr/bin/tar --version
    chroot "$check" /usr/bin/zstd -V
    chroot "$check" /usr/bin/gzip --version
    chroot "$check" /usr/bin/sha256sum --version
    # The sender rejects an incomplete argument list with status 2.
    status=0
    chroot "$check" /bin/udp_log_sender 2>/dev/null || status=$?
    [ "$status" = 2 ] && echo 'udp_log_sender: usage status 2'
} >runtime-check.txt 2>&1
rm -rf "$check"

cp "$init" init
sha256sum "$busybox" "$sender" "$kexec" "$capture" "$arch" "$core" "$upper_helper" "$thermal_helper" \
  /usr/sbin/dropbear /usr/bin/dropbearkey /usr/sbin/mke2fs /etc/mke2fs.conf \
  /usr/bin/tar /usr/bin/gzip /usr/bin/zstd /usr/bin/sha256sum >inputs.sha256
sha256sum launcher.cpio.gz launcher.cpio.gz.json init authorized_keys \
  dropbear_ed25519_host_key listing.txt runtime-check.txt build.log >outputs.sha256
printf 'built: %s size=%s\n' "$out/launcher.cpio.gz" "$size"
grep launcher.cpio.gz outputs.sha256 | head -1
