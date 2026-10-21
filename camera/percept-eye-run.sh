#!/bin/sh
# Run the extracted azureeyemodule runtime from a chroot: no Docker, no daemon.
# Equivalent to the prepared proof-of-capture.sh, with unshare -n standing in
# for --network none and bind mounts standing in for --mount/--device-cgroup-rule.
#
#   percept-eye-run.sh record  [SECONDS]   offline: empty netns, H.264 + detector
#   percept-eye-run.sh preview [SECONDS]   host network: RTSP on 8554 for LAN
#
# Never flashes peripheral firmware and changes nothing outside TARGET/OUT.
set -eu

mode=${1:?record or preview}
seconds=${2:-30}
root=${EYE_ROOT:-/opt/eyesom}
out=${EYE_OUT:-/var/tmp/eye-capture}
case "$mode" in record|preview) ;; *) echo 'mode must be record or preview' >&2; exit 1 ;; esac
case "$seconds" in ''|*[!0-9]*) echo 'seconds must be a number' >&2; exit 1 ;; esac
[ "$(id -u)" = 0 ] || { echo 'must run as root (chroot and mounts)' >&2; exit 1; }
[ -x "$root/app/inference" ] || { echo "no runtime at $root" >&2; exit 1; }

# Everything below runs in a PRIVATE mount namespace. The bind mounts of /sys and
# /dev are recursive copies of shared mounts: unmounting them in the host
# namespace propagates back and unmounts the real /sys/fs/cgroup, /dev/pts,
# /dev/shm, /dev/mqueue, /sys/kernel/debug and more. An earlier version did
# exactly that to the running system (new cgroups and scopes then failed with
# "No such file or directory"). In a private namespace nothing can propagate
# out, and the kernel tears the mounts down when the script exits.
if [ -z "${EYE_PRIVATE_NS:-}" ]; then
    EYE_PRIVATE_NS=1 exec unshare --mount --propagation private "$0" "$@"
fi

# Same two hardware gates as the reviewed Docker script.
descriptor=$(lsusb -v -d 045e:066f 2>/dev/null || true)
printf '%s\n' "$descriptor" | grep -Eq 'bcdDevice[[:space:]]+3\.00' || {
    echo 'Stop: SoM controller 045e:066f is not an updated 3.00 unit.' >&2; exit 1; }
# 2485 is the Myriad X boot ROM; after a run it stays booted and re-enumerates
# as f63b ("VSC Loopback Device") until the SoM is power-cycled. Accept either,
# so a second run does not falsely report the VPU as missing.
if lsusb -d 03e7:2485 | grep -q 03e7:2485; then
    vpu='2485 (boot ROM)'
elif lsusb -d 03e7:f63b | grep -q 03e7:f63b; then
    vpu='f63b (already booted)'
else
    echo 'Stop: no Myriad X (03e7:2485 or 03e7:f63b); inspect before capture.' >&2
    exit 1
fi
echo "Myriad X: $vpu"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
capture=$out/$mode-$stamp
mkdir -p "$capture"
printf '%s\n' "$descriptor" >"$capture/usb-descriptor.txt"
lsusb -t >"$capture/usb-tree.txt"
lsusb >"$capture/lsusb.txt"

mounted=''
cleanup() {
    for m in $mounted; do umount -l "$m" 2>/dev/null || true; done
    mounted=''
}
trap cleanup EXIT INT TERM
for m in proc sys dev; do
    mkdir -p "$root/$m"
    case "$m" in
        proc) mount -t proc proc "$root/proc" ;;
        sys)  mount --rbind /sys "$root/sys" ;;
        # /dev carries /dev/bus/usb, which is how libusb reaches the VPU.
        dev)  mount --rbind /dev "$root/dev" ;;
    esac
    mounted="$root/$m $mounted"
done
mkdir -p "$root/capture"
mount --bind "$capture" "$root/capture"
mounted="$root/capture $mounted"

set -- /app/inference \
    --model=/app/data/ssd_mobilenet_v2_coco.blob \
    --label=/app/data/labels.txt --parser=ssd100 \
    --mvcmd=/eyesom/mx.mvcmd --size="${EYE_SIZE:-720p}" --fps="${EYE_FPS:-10}"
if [ "$mode" = record ]; then
    set -- "$@" --h264_out=/capture/proof.h264
fi

# Empty network namespace for the offline test; preview needs the host's LAN.
isolate=''
[ "$mode" = record ] && isolate='unshare -n'

echo "running $mode for ${seconds}s; output in $capture"
set +e
env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
    timeout -s INT -k 10 "$seconds" \
    $isolate chroot "$root" "$@" >"$capture/runtime.log" 2>&1
status=$?
set -e
printf 'exit status: %s\n' "$status" >>"$capture/runtime.log"
cleanup
trap - EXIT INT TERM

echo "--- last 25 log lines"
tail -25 "$capture/runtime.log" || true
echo "--- artefacts"
ls -la "$capture"
if [ "$mode" = record ]; then
    if [ -s "$capture/proof.h264" ]; then
        echo "Candidate recording: $capture/proof.h264 ($(stat -c %s "$capture/proof.h264") bytes)"
        echo "Decode a frame to prove capture (a non-empty file is not proof)."
    else
        echo "No recording produced; read $capture/runtime.log" >&2
        exit 1
    fi
fi
