#!/bin/bash
# Stage C, on Bookworm: pack the finished trixie tree (after stage B ran under
# 6.12) with Bookworm's GNU tar, keeping xattrs/ACLs and numeric owners.
# The build inputs under /percept-build are left out of the tarball.
set -euo pipefail
out=/root/percept-kexec-work/trixie-build
root=$out/root
release=6.12.113+deb13-arm64
[ -e "$root/percept-build/stage-b.done" ] || { echo 'stage B not done' >&2; exit 1; }
[ ! -e "$out/trixie-root.tar.gz" ] || { echo 'tarball already exists' >&2; exit 1; }
test -s "$root/boot/vmlinuz-$release"
test -s "$root/boot/initrd.img-$release"
test -s "$root/boot/vmlinuz-5.4.3-mariner"
# Keep the build record next to the tarball.
cp -a "$root/percept-build" "$out/build-record"
rm -f "$out/build-record/linux-image.deb"
tar --xattrs --xattrs-include='*' --acls --numeric-owner --one-file-system \
    --exclude=./percept-build -C "$root" -cpf - . | gzip -6 >"$out/trixie-root.tar.gz"
(cd "$out" && sha256sum trixie-root.tar.gz >trixie-root.tar.gz.sha256)
tar -tzf "$out/trixie-root.tar.gz" | grep -x "./boot/vmlinuz-$release" >/dev/null
du -sh "$out/trixie-root.tar.gz"
cat "$out/trixie-root.tar.gz.sha256"
