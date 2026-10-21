#!/bin/sh
# Hardware decode throughput on the Hantro engines, vs CPU-only software decode.
# Run ON the board while otherwise idle. Decodes to a fakesink with sync=false,
# so display pacing, colour conversion and disk writes are not in the number.
# CPU use is the whole-system busy time from /proc/stat across the run (all cores),
# which is meaningful because nothing else is running.
#   vpu-bench.sh [WIDTHxHEIGHT] [FRAMES]
set -u
size=${1:-1280x720}; frames=${2:-300}
OUT=${OUT:-/var/tmp/vpu-bench}; mkdir -p "$OUT"; cd "$OUT" || exit 2
log=$OUT/bench-$size.txt; : >"$log"
say() { printf '%s\n' "$*" | tee -a "$log"; }
busy() { awk '/^cpu /{ print $2 + $3 + $4 + $7 + $8 }' /proc/stat; }   # jiffies, 100/s

run_timed() {   # sets wall (s) and cpu (CPU-seconds); returns the command's status
    b0=$(busy); t0=$(date +%s.%N)
    "$@" >/dev/null 2>&1; rc=$?
    t1=$(date +%s.%N); b1=$(busy)
    wall=$(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.2f", b - a }')
    cpu=$(awk -v a="$b0" -v b="$b1" 'BEGIN { printf "%.2f", (b - a) / 100 }')
    return "$rc"
}

bench() {   # name enc-args ext parse decoder
    name=$1; enc=$2; ext=$3; parse=$4; dec=$5
    f=bench-$name-$size.$ext
    if [ ! -s "$f" ]; then
        # shellcheck disable=SC2086
        ffmpeg -v error -y -f lavfi -i "testsrc2=size=$size:rate=30" -frames:v "$frames" -pix_fmt yuv420p $enc "$f" || { say "$name: could not generate sample"; return; }
    fi
    # shellcheck disable=SC2086
    run_timed gst-launch-1.0 -q filesrc location="$f" ! $parse ! "$dec" ! "video/x-raw,format=NV12" ! fakesink sync=false
    hrc=$?; hwall=$wall; hcpu=$cpu
    run_timed ffmpeg -v error -threads 4 -i "$f" -f null -
    src=$?; swall=$wall; scpu=$cpu
    hfps=$(awk -v n="$frames" -v s="$hwall" 'BEGIN { printf "%.1f", n / s }')
    sfps=$(awk -v n="$frames" -v s="$swall" 'BEGIN { printf "%.1f", n / s }')
    say "$name $size ($frames frames): HARDWARE ${hfps} fps, ${hwall}s wall, ${hcpu} CPU-s (rc=$hrc)  |  SOFTWARE ${sfps} fps, ${swall}s wall, ${scpu} CPU-s (rc=$src)"
}
say "== decode throughput, $size, $frames frames, $(date -u +%H:%MZ), temp $(cat /sys/class/thermal/thermal_zone0/temp) m C"
bench h264  "-c:v libx264 -preset veryfast -profile:v main -g 30 -bf 2 -f h264" h264 h264parse v4l2slh264dec
bench vp8   "-c:v libvpx -b:v 4M -g 30 -f ivf" ivf ivfparse v4l2slvp8dec
bench h265  "-c:v libx265 -preset ultrafast -x265-params keyint=30:bframes=2:log-level=error -f hevc" h265 h265parse v4l2slh265dec
bench vp9   "-c:v libvpx-vp9 -b:v 4M -g 30 -deadline realtime -cpu-used 8 -f ivf" ivf "ivfparse ! vp9parse" v4l2slvp9dec
say "temp after: $(cat /sys/class/thermal/thermal_zone0/temp) m C"
