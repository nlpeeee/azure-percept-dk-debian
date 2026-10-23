#!/bin/bash
# PC-side health check of a running Percept trixie boot. Read-only on the board.
#   verify-boot.sh [--vpu] [--audio]   prints PASS/FAIL/INFO lines, exits non-zero on any FAIL
#
# Needs key-based root (or sudo) SSH to the board: set PERCEPT_HOST and optionally PERCEPT_KEY. --vpu also
# requires Hantro G1/G2 probe plus video/media nodes. --audio requires the updated Ear SoM
# (controller firmware 3.00, USB audio 0671, ALSA card PerceptEar with 5 capture channels).
set -u
host=${PERCEPT_HOST:?set PERCEPT_HOST to the board address}
key=${PERCEPT_KEY:-$HOME/.ssh/id_ed25519}
kh=${PERCEPT_KNOWN_HOSTS:-$HOME/.ssh/percept_known_hosts}
want_vpu=0; want_audio=0
for arg in "$@"; do
    case $arg in
        --vpu) want_vpu=1 ;;
        --audio) want_audio=1 ;;
        *) echo "usage: $0 [--vpu] [--audio]" >&2; exit 2 ;;
    esac
done
ssh_opts=(-i "$key" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8
          -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$kh" -o LogLevel=ERROR)

out=$(ssh "${ssh_opts[@]}" "root@$host" 'sh -s' <<'REMOTE' 2>&1
echo "kernel=$(uname -r)"
echo "boot_id=$(cat /proc/sys/kernel/random/boot_id)"
echo "uptime_s=$(cut -d. -f1 /proc/uptime)"
echo "memtotal_kb=$(awk '/MemTotal/{print $2}' /proc/meminfo)"
echo "cmdline=$(cat /proc/cmdline)"
echo "state=$(systemctl is-system-running 2>&1)"
echo "failed=$(systemctl --failed --no-legend 2>/dev/null | awk '{print $2}' | tr '\n' ' ')"
echo "eth0=$(cat /sys/class/net/eth0/operstate 2>/dev/null) $(ip -4 -o addr show eth0 2>/dev/null | awk '{print $4}')"
echo "wlan=$(ls /sys/class/net | grep -c '^wlan')"
echo "hci=$(ls /sys/class/bluetooth 2>/dev/null | tr '\n' ' ')"
echo "thermal_mC=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)"
echo "deferred=$(cat /sys/kernel/debug/devices_deferred 2>/dev/null | tr '\n' ';')"
echo "dwc3=$(ls /sys/bus/platform/drivers/dwc3 2>/dev/null | grep -c '^3')"
echo "usb_som=$(lsusb 2>/dev/null | grep -cE '045e:066f')"
echo "usb_vpu=$(lsusb 2>/dev/null | grep -cE '03e7:(2485|f63b)')"
ear_bcd=""; ear_n=0
for d in /sys/bus/usb/devices/*; do
    [ -r "$d/idVendor" ] && [ "$(cat "$d/idVendor")" = 045e ] || continue
    case "$(cat "$d/idProduct" 2>/dev/null)" in
        0673) ear_bcd=$(cat "$d/bcdDevice" 2>/dev/null) ;;
        0671) ear_n=$((ear_n + 1)) ;;
    esac
done
echo "ear_ctl_bcd=$ear_bcd"
echo "ear_audio_n=$ear_n"
echo "ear_card=$([ -d /proc/asound/PerceptEar ] && echo 1 || echo 0)"
echo "ear_cap_ch=$(awk '/^Capture:/{c=1} c&&/Channels:/{print $2; exit}' /proc/asound/PerceptEar/stream0 2>/dev/null)"
echo "render=$(ls /dev/dri/renderD* 2>/dev/null | tr '\n' ' ')"
echo "etnaviv=$(dmesg | grep -c 'Initialized etnaviv')"
echo "hantro_lines=$(dmesg | grep -ci 'hantro')"
echo "video=$(ls /dev/video* 2>/dev/null | tr '\n' ' ')"
echo "media=$(ls /dev/media* 2>/dev/null | tr '\n' ' ')"
echo "fault_lines=$(dmesg | grep -ciE 'mmu fault|gpu hang|Oops|BUG:|Unable to handle|soft lockup|rcu: INFO')"
mountpoint -q /boot/efi || mount /boot/efi 2>/dev/null
echo "failcount=$(cat /boot/efi/percept/failcount 2>/dev/null)"
echo "percept_tries=$(grep -a -o 'percept_tries=[0-9]*' /boot/efi/boot/grub2/grubenv 2>/dev/null)"
echo "media_conf=$(grep -E '^media=' /boot/efi/percept/launcher.conf 2>/dev/null)"
REMOTE
) || { echo "FAIL ssh: cannot reach $host"; exit 2; }

get() { printf '%s\n' "$out" | sed -n "s/^$1=//p" | head -1; }
fails=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; fails=$((fails + 1)); }
info() { printf 'INFO  %s\n' "$1"; }
check() { if [ "$2" = 1 ]; then pass "$1"; else fail "$1"; fi; }

printf 'boot_id %s  uptime %ss  media %s\n' "$(get boot_id)" "$(get uptime_s)" "$(get media_conf)"
check "Debian kernel 6.12.113+deb13-arm64 ($(get kernel))" "$([ "$(get kernel)" = 6.12.113+deb13-arm64 ] && echo 1)"
mem=$(get memtotal_kb); check "RAM $((mem / 1024)) MiB (4 GiB map, > 3.8 GiB)" "$([ "${mem:-0}" -gt 3900000 ] && echo 1)"
check "eth0 up with address ($(get eth0))" "$(get eth0 | grep -q '^up ' && echo 1)"
check "Wi-Fi interface present ($(get wlan))" "$([ "$(get wlan)" -ge 1 ] && echo 1)"
check "Bluetooth controller ($(get hci))" "$([ -n "$(get hci | tr -d ' ')" ] && echo 1)"
t=$(get thermal_mC); check "CPU thermal ${t:-none} m°C (plausible 15-85 °C)" "$([ -n "$t" ] && [ "$t" -gt 15000 ] && [ "$t" -lt 85000 ] && echo 1)"
check "no deferred devices ('$(get deferred)')" "$([ -z "$(get deferred | tr -d ';')" ] && echo 1)"
check "USB-C dwc3 controllers bound ($(get dwc3) of 2)" "$([ "$(get dwc3)" = 2 ] && echo 1)"
check "camera SoM 045e:066f enumerated" "$([ "$(get usb_som)" -ge 1 ] && echo 1)"
check "Myriad X present (2485 or f63b)" "$([ "$(get usb_vpu)" -ge 1 ] && echo 1)"
check "GPU render node + etnaviv ($(get render))" "$([ -n "$(get render | tr -d ' ')" ] && [ "$(get etnaviv)" -ge 1 ] && echo 1)"
check "no kernel fault/hang lines ($(get fault_lines))" "$([ "$(get fault_lines)" = 0 ] && echo 1)"
failed=$(get failed | sed 's/systemd-networkd-wait-online.service//; s/[[:space:]]//g')
check "no failed units besides wait-online ('${failed}')" "$([ -z "$failed" ] && echo 1)"
info "state=$(get state) failcount=$(get failcount) $(get percept_tries)"
if [ "$want_vpu" = 1 ]; then
    check "Hantro driver messages present ($(get hantro_lines))" "$([ "$(get hantro_lines)" -ge 1 ] && echo 1)"
    check "video nodes ($(get video))" "$([ -n "$(get video | tr -d ' ')" ] && echo 1)"
    check "media nodes ($(get media))" "$([ -n "$(get media | tr -d ' ')" ] && echo 1)"
else
    info "VPU: hantro_lines=$(get hantro_lines) video='$(get video)' media='$(get media)'"
fi
if [ "$want_audio" = 1 ]; then
    check "Ear SoM controller 045e:0673 firmware 3.00 (bcdDevice '$(get ear_ctl_bcd)')" "$([ "$(get ear_ctl_bcd)" = 0300 ] && echo 1)"
    check "Ear SoM USB audio 045e:0671 present ($(get ear_audio_n))" "$([ "$(get ear_audio_n)" -ge 1 ] && echo 1)"
    check "ALSA card PerceptEar present" "$([ "$(get ear_card)" = 1 ] && echo 1)"
    check "5 capture channels ($(get ear_cap_ch))" "$([ "$(get ear_cap_ch)" = 5 ] && echo 1)"
else
    info "audio: ctl_bcd='$(get ear_ctl_bcd)' usb_audio=$(get ear_audio_n) card=$(get ear_card) capture_ch='$(get ear_cap_ch)'"
fi
[ "$fails" = 0 ] && echo "RESULT: ALL PASS" || echo "RESULT: $fails FAIL"
exit $((fails > 0))
