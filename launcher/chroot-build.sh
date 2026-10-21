#!/bin/bash
# SPDX-License-Identifier: MIT
# Runs INSIDE the arm64 builder chroot (see launcher/build.sh). Compiles the launcher's
# own programs and assembles the initramfs. Inputs (bind-mounted by build.sh):
#   /src     the repository, read-only
#   /dl      downloaded source tarballs, read-only
#   /out     output directory, read-write
#   /modules directory holding arch.ko and core.ko (optional, read-only)
# Environment: SOURCE_DATE_EPOCH (for reproducible timestamps), NO_MODULES=1 to skip the .ko files.
set -euo pipefail

export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1700000000}
export TZ=UTC LC_ALL=C
jobs=$(nproc)
work=/tmp/launcher-build
rm -rf "$work"; mkdir -p "$work" /out/stage
cd "$work"

echo "== kexec-tools 2.0.25 (stock, unpatched: the 'quiet purgatory' build that boots board 1)"
tar -xf /dl/kexec-tools-2.0.25.tar.xz
( cd kexec-tools-2.0.25 &&
  ./configure --prefix=/usr >configure.log 2>&1 &&
  make -j"$jobs" >make.log 2>&1 )
install -D kexec-tools-2.0.25/build/sbin/kexec /out/stage/kexec

echo "== capture.so (LD_PRELOAD shim that records kexec_load instead of calling it)"
gcc -O2 -Wall -shared -fpic -o /out/stage/capture.so /src/launcher/src/capture.c

echo "== udp_log_sender (static)"
gcc -O2 -Wall -static -o /out/stage/udp_log_sender /src/launcher/src/udp_log_sender.c

echo "== device-tree helpers (static)"
gcc -O2 -Wall -Wextra -static -o /out/stage/percept-fdt-upper /src/launcher/fdt/extend-fdt.c
gcc -O2 -Wall -Wextra -static -o /out/stage/percept-fdt-thermal /src/launcher/fdt/fix-thermal-fdt.c
gcc -O2 -Wall -Wextra -static -o /out/stage/percept-fdt-media /src/launcher/fdt/adapt-fdt.c -lfdt
for kind in cpu pmic; do
    gcc -std=c99 -O2 -Wall -Wextra -Werror -static -o /out/stage/percept-fdt-$kind \
        /src/launcher/fdt/adapt-$kind-fdt.c -lfdt
done

args=(
  --output /out/launcher.cpio.gz
  --manifest /out/launcher.manifest.json
  --init /src/launcher/init
  --busybox /bin/busybox
  --binary /out/stage/kexec:sbin/kexec
  --binary /usr/sbin/dropbear:usr/sbin/dropbear
  --binary /usr/bin/dropbearkey:usr/bin/dropbearkey
  --binary /usr/sbin/mke2fs:usr/sbin/mke2fs
  --binary /usr/bin/tar:usr/bin/tar
  --binary /usr/bin/gzip:usr/bin/gzip
  --binary /usr/bin/zstd:usr/bin/zstd
  --binary /usr/bin/sha256sum:usr/bin/sha256sum
  --symlink usr/sbin/mkfs.ext4:mke2fs
  --file /etc/mke2fs.conf:etc/mke2fs.conf
  --file /out/stage/capture.so:lib/percept/capture.so:0755
  --file /src/launcher/lib/percept-config.sh:lib/percept/percept-config.sh:0644
  --file /src/launcher/udhcpc.script:lib/percept/udhcpc.script:0755
  --static-binary /out/stage/udp_log_sender:bin/udp_log_sender
  --static-binary /out/stage/percept-fdt-upper:bin/percept-fdt-upper
  --static-binary /out/stage/percept-fdt-thermal:bin/percept-fdt-thermal
  --static-binary /out/stage/percept-fdt-media:bin/percept-fdt-media
  --static-binary /out/stage/percept-fdt-cpu:bin/percept-fdt-cpu
  --static-binary /out/stage/percept-fdt-pmic:bin/percept-fdt-pmic
)
if [ "${NO_MODULES:-0}" != 1 ]; then
    args+=(--file /modules/arch.ko:lib/percept/arch.ko:0444 --file /modules/core.ko:lib/percept/core.ko:0444)
fi
[ -n "${AUTHORIZED_KEYS:-}" ] && args+=(--authorized-keys "$AUTHORIZED_KEYS")

echo "== assembling initramfs"
python3 /src/launcher/mkinitramfs.py "${args[@]}"

verify=(/out/launcher.cpio.gz)
[ "${NO_MODULES:-0}" != 1 ] || verify+=(--no-modules)
[ -z "${AUTHORIZED_KEYS:-}" ] || verify+=(--allow-authorized-keys)
python3 /src/launcher/verify_archive.py "${verify[@]}" > /out/archive-validation.json

echo "== self-check: every program starts with only the archive's own files"
check=$work/check
mkdir -p "$check"
gzip -dc /out/launcher.cpio.gz | ( cd "$check" && busybox cpio -id 2>/dev/null )
chroot "$check" /bin/busybox sh -n /init
chroot "$check" /sbin/kexec --version
chroot "$check" /bin/busybox env LD_PRELOAD=/lib/percept/capture.so /sbin/kexec --version
chroot "$check" /usr/sbin/dropbear -V 2>&1
chroot "$check" /usr/sbin/mkfs.ext4 -V 2>&1 | head -1
chroot "$check" /usr/bin/tar --version | head -1
chroot "$check" /usr/bin/zstd -V
chroot "$check" /bin/sh -c '. /lib/percept/percept-config.sh' 2>&1 || true
for h in upper thermal media cpu pmic; do chroot "$check" /bin/percept-fdt-$h 2>&1 | head -1 || true; done
python3 /src/build/write-manifest.py --output /out/build.manifest.json --kind launcher \
    --source-commit "$SOURCE_COMMIT" --artifact /out/launcher.cpio.gz \
    --input /src/launcher/init --input /src/launcher/lib/percept-config.sh \
    --input /dl/kexec-tools-2.0.25.tar.xz
echo "== done"
sha256sum /out/launcher.cpio.gz
