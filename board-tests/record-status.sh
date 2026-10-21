#!/bin/sh
set -eu
printf 'UTC: '; date -u
printf 'Kernel: '; uname -r
printf 'Boot ID: '; cat /proc/sys/kernel/random/boot_id
dpkg-query -W firmware-realtek wireless-regdb iw bluez device-tree-compiler libfdt-dev
sha256sum /usr/lib/firmware/rtw88/rtw8822c_fw.bin \
    /usr/lib/firmware/rtw88/rtw8822c_wow_fw.bin \
    /usr/lib/firmware/rtl_bt/rtl8822cu_fw.bin \
    /usr/lib/firmware/rtl_bt/rtl8822cu_config.bin /usr/lib/firmware/regulatory.db
sha256sum /boot/vmlinuz-6.12.113+deb13-arm64 /boot/initrd.img-6.12.113+deb13-arm64 \
    /boot/efi/percept/launcher.cpio.gz /boot/efi/percept/launcher.conf
lspci -nnk
iw dev
btmgmt info
systemctl is-enabled bluetooth
for z in /sys/class/thermal/thermal_zone*; do
    [ -d "$z" ] || continue
    printf '%s\n' "$z"
    cat "$z/type" "$z/temp"
done
readlink /sys/bus/platform/devices/30260000.tmu/driver || true
readlink /sys/bus/platform/devices/38100000.usb/driver || true
lsusb
cat /boot/efi/percept/failcount
dmesg | grep -E 'rtw_8822ce|Bluetooth: hci0: RTL:|qoriq_thermal|thermal_sys:'
