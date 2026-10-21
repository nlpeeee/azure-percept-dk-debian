#!/bin/bash
# Stage B: runs inside the trixie chroot under the Debian 6.12 kernel (builder
# boot). Finishes debootstrap and configures the system. Uses no network:
# stage A fetched every package. Leaves /percept-build/stage-b.done on success.
set -euo pipefail
b=/percept-build
release=6.12.113+deb13-arm64
esp_uuid=8AB1-C6BE
cd "$b"
sha256sum --strict -c inputs.sha256
[ "$(uname -r)" = "$release" ] || { echo "must run under $release" >&2; exit 1; }
[ ! -e stage-b.done ] || { echo 'stage B already done' >&2; exit 1; }
root_uuid=$(cat root-uuid)
mirror=$(cat mirror)
source ./config.sh
export DEBIAN_FRONTEND=noninteractive LC_ALL=C

/debootstrap/debootstrap --second-stage
printf '#!/bin/sh\nexit 101\n' >/usr/sbin/policy-rc.d
chmod 755 /usr/sbin/policy-rc.d

cat >/etc/apt/sources.list <<EOF
deb $mirror trixie main contrib non-free-firmware
deb $mirror trixie-updates main contrib non-free-firmware
deb http://security.debian.org/debian-security trixie-security main contrib non-free-firmware
EOF

echo "$HOSTNAME" >/etc/hostname
cat >/etc/hosts <<EOF
127.0.0.1       localhost
127.0.1.1       $HOSTNAME

::1             localhost ip6-localhost ip6-loopback
ff02::1         ip6-allnodes
ff02::2         ip6-allrouters
EOF

# Root by UUID: under 6.12 the eMMC is mmcblk1, not mmcblk0.
cat >/etc/fstab <<EOF
# /etc/fstab - Debian trixie on Azure Percept DK
UUID=$root_uuid  /          ext4  errors=remount-ro,noatime  0  1
UUID=$esp_uuid   /boot/efi  vfat  umask=0077,nofail          0  2
EOF
install -d /boot/efi

# Debian initramfs: also load the watchdog early. The stock kernel leaves the
# i.MX watchdog running across kexec, and imx2_wdt keeps it fed.
cat >>/etc/initramfs-tools/modules <<EOF
imx2_wdt
sdhci-esdhc-imx
ext4
EOF

# The exact tested Debian kernel; its postinst builds the initramfs.
dpkg -i "$b/linux-image.deb"
apt-mark hold "linux-image-$release"
test -s "/boot/vmlinuz-$release"
test -s "/boot/initrd.img-$release"

# Networking: DHCP on any wired interface, as in the Bookworm image.
install -d /etc/systemd/network
cat >/etc/systemd/network/20-wired.network <<EOF
[Match]
Name=eth* en*

[Network]
DHCP=yes

[DHCP]
RouteMetric=100
UseDNS=yes
UseNTP=yes
EOF

# SSH per config.sh, plus the supplied keys.
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
install -d -m 700 /root/.ssh
install -m 600 "$b/authorized_keys" /root/.ssh/authorized_keys
echo "root:$ROOT_PASSWORD" | chpasswd
useradd -m -s /bin/bash -G sudo,dialout,audio,video,plugdev "$NEW_USER"
echo "$NEW_USER:$NEW_USER_PASSWORD" | chpasswd

# Reset the board if userspace hangs; journal size as on Bookworm.
install -d /etc/systemd/system.conf.d /etc/systemd/journald.conf.d
printf '[Manager]\nRuntimeWatchdogSec=60\n' >/etc/systemd/system.conf.d/watchdog.conf
printf '[Journal]\nSystemMaxUse=50M\nSystemMaxFileSize=10M\n' >/etc/systemd/journald.conf.d/size.conf

# Clears the launcher's failure counter once SSH and the network are up.
install -m 755 "$b/percept-boot-ok" /usr/local/sbin/percept-boot-ok
install -m 644 "$b/percept-boot-ok.service" /etc/systemd/system/percept-boot-ok.service
install -d /etc/systemd/system/systemd-networkd-wait-online.service.d
install -m 644 "$b/wait-online-override.conf" /etc/systemd/system/systemd-networkd-wait-online.service.d/override.conf

sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen
locale-gen
echo 'LANG=en_US.UTF-8' >/etc/default/locale
ln -sf /usr/share/zoneinfo/UTC /etc/localtime
systemctl enable systemd-networkd systemd-resolved systemd-timesyncd ssh \
    serial-getty@ttymxc0.service percept-boot-ok.service

apt-get clean
rm -rf /var/lib/apt/lists/*
rm /usr/sbin/policy-rc.d
ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
: >/etc/machine-id
rm -f /var/lib/dbus/machine-id

# Checks.
/usr/sbin/sshd -t
grep -q "UUID=$root_uuid" /etc/fstab
sha256sum "/boot/vmlinuz-$release" "/boot/initrd.img-$release" \
    /boot/vmlinuz-5.4.3-mariner >"$b/boot.sha256"
lsinitramfs "/boot/initrd.img-$release" | grep -E 'imx2_wdt|sdhci-esdhc-imx|/ext4' >"$b/initrd-modules.txt"
dpkg-query -W >"$b/packages.txt"
sync
date -u >"$b/stage-b.done"
echo "STAGE B DONE"
