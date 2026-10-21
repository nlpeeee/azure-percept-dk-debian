#!/bin/bash
# SPDX-License-Identifier: MIT
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive LC_ALL=C
printf '#!/bin/sh\nexit 101\n' >/usr/sbin/policy-rc.d
chmod 755 /usr/sbin/policy-rc.d
/debootstrap/debootstrap --second-stage
mkdir -p /etc/apt/preferences.d /etc/initramfs-tools
cat >/etc/apt/preferences.d/percept-kernel <<'EOF'
Package: linux-image-*
Pin: version 6.12.*
Pin-Priority: 1001
EOF
python3 - <<'PY'
import json,os
c=json.load(open(os.environ['BUILD_SETTINGS']))['config'];mirror=c['os'].get('mirror') or 'http://deb.debian.org/debian'
open('/etc/apt/sources.list','w').write('deb '+mirror+' trixie main contrib non-free-firmware\ndeb '+mirror+' trixie-updates main contrib non-free-firmware\ndeb http://security.debian.org/debian-security trixie-security main contrib non-free-firmware\n')
PY
printf 'imx2_wdt\nsdhci-esdhc-imx\next4\n' >/etc/initramfs-tools/modules
apt-get update
apt-get install -y linux-image-arm64
release=$(find /lib/modules -mindepth 1 -maxdepth 1 -type d -printf '%f\n')
case "$release" in 6.12.*-arm64) ;; *) echo "unsupported installed kernel $release" >&2; exit 1 ;; esac
profile=$(python3 -c 'import json,os;print(json.load(open(os.environ["BUILD_SETTINGS"]))["config"]["os"]["cpu_profile"])')
hooks=$(PYTHONPATH=/src/src python3 -c 'from percept import tomlmini;print(" ".join(tomlmini.load_file("/src/profiles/debian-trixie/profile.toml")["rootfs"].get("hooks",[])))')
for hook in $hooks; do
    PERCEPT_CPU_PROFILE="$profile" sh "/src/profiles/debian-trixie/hooks/$hook"
done
lsinitramfs "/boot/initrd.img-$release" >/percept-initramfs-members
printf '%s\n' "$release" >/percept-kernel-release
dpkg-query -W '-f=${binary:Package}=${Version}\n' >/percept-package-versions
mkdir -p /etc/kernel/postinst.d
cat >/etc/kernel/postinst.d/percept-series <<'EOF'
#!/bin/sh
case "$1" in 6.12.*) ;; *) echo 'WARNING: kernel outside Percept validated 6.12 series' >&2 ;; esac
EOF
chmod 755 /etc/kernel/postinst.d/percept-series
apt-get clean
rm -f /usr/sbin/policy-rc.d
