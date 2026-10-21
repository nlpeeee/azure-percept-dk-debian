#!/bin/sh
# Hardware video decode proof for the i.MX8MQ Hantro G1/G2 on Debian 13.
# Run ON the board after the VPU DT is active. Everything is written below
# $OUT (default /var/tmp/vpu-test). For each codec it
#   1. generates a deterministic sample with a software encoder,
#   2. decodes it with ffmpeg (software reference) to raw I420,
#   3. decodes it with GStreamer's stateless V4L2 element (hardware) to raw I420,
#   4. compares the two byte for byte and counts the engine's interrupts.
# A non-empty file or high CPU use proves nothing; an interrupt delta on the
# engine's own IRQ plus identical decoded frames does.
#
#   vpu-decode-test.sh [h264|h265|mpeg2|vp8|vp9|all] [WIDTHxHEIGHT] [FRAMES]
set -u
which=${1:-all}
size=${2:-1280x720}
frames=${3:-90}
OUT=${OUT:-/var/tmp/vpu-test}
w=${size%x*}; h=${size#*x}
frame_bytes=$((w * h * 3 / 2))
mkdir -p "$OUT"
cd "$OUT" || exit 2
log=$OUT/results-$size.txt
: >"$log"
say() { printf '%s\n' "$*" | tee -a "$log"; }

irq_count() {   # $1 = pattern of the engine's /proc/interrupts line; sums all CPU columns
    awk -v pat="$1" '$0 ~ pat { n = 0; for (i = 2; i <= NF && $i ~ /^[0-9]+$/; i++) n += $i; print n; exit }' /proc/interrupts
}

# codec | encoder args | container ext | gst parse chain | decoder element | engine IRQ owner
run_case() {
    name=$1; enc=$2; ext=$3; chain=$4; dec=$5; irqpat=$6
    say ""
    say "=== $name  ${size}  ${frames} frames  decoder=$dec"
    sample=sample-$name-$size.$ext
    rm -f "$sample" ref-$name-$size.yuv hw-$name-$size.yuv
    # shellcheck disable=SC2086
    if ! ffmpeg -v error -y -f lavfi -i "testsrc2=size=$size:rate=30" -frames:v "$frames" \
            -pix_fmt yuv420p $enc "$sample" 2>>"$log"; then
        say "SKIP  could not generate the sample"; return 0
    fi
    say "sample: $(stat -c %s "$sample") bytes"
    ffmpeg -v error -y -i "$sample" -pix_fmt yuv420p -f rawvideo "ref-$name-$size.yuv" 2>>"$log" || { say "FAIL  software reference decode"; return 1; }
    ref_frames=$(( $(stat -c %s "ref-$name-$size.yuv") / frame_bytes ))
    say "software reference: $ref_frames frames"

    before=$(irq_count "$irqpat")
    start=$(date +%s.%N)
    timeout 120 gst-launch-1.0 -q filesrc location="$sample" ! $chain ! "$dec" ! "video/x-raw,format=NV12" ! videoconvert \
        ! "video/x-raw,format=I420" ! filesink location="hw-$name-$size.yuv" >>"$log" 2>&1
    rc=$?
    end=$(date +%s.%N)
    after=$(irq_count "$irqpat")
    if [ ! -s "hw-$name-$size.yuv" ]; then say "FAIL  hardware decode produced no output (gst rc=$rc)"; return 1; fi
    hw_frames=$(( $(stat -c %s "hw-$name-$size.yuv") / frame_bytes ))
    secs=$(awk -v a="$start" -v b="$end" 'BEGIN { printf "%.2f", b - a }')
    fps=$(awk -v n="$hw_frames" -v s="$secs" 'BEGIN { if (s > 0) printf "%.1f", n / s; else print "n/a" }')
    irqs=$(( ${after:-0} - ${before:-0} ))
    ref_sum=$(sha256sum "ref-$name-$size.yuv" | cut -c1-16)
    hw_sum=$(sha256sum "hw-$name-$size.yuv" | cut -c1-16)
    say "hardware: $hw_frames frames in ${secs}s (${fps} fps incl. start-up), gst rc=$rc, engine interrupts +$irqs"
    say "sha256  reference=$ref_sum  hardware=$hw_sum"
    if [ "$irqs" -le 0 ]; then say "FAIL  no interrupts from the engine: this was not hardware decode"; return 1; fi
    if [ "$hw_frames" != "$ref_frames" ]; then say "FAIL  frame count differs ($hw_frames vs $ref_frames)"; return 1; fi
    if [ "$ref_sum" = "$hw_sum" ]; then
        say "PASS  $name: bit-identical to the software reference, $irqs engine interrupts"
    else
        # Not identical: measure how different, frame by frame.
        psnr=$(ffmpeg -v info -f rawvideo -pix_fmt yuv420p -s "$size" -i "hw-$name-$size.yuv" \
            -f rawvideo -pix_fmt yuv420p -s "$size" -i "ref-$name-$size.yuv" -lavfi psnr -f null - 2>&1 | grep -o 'average:[^ ]*' | tail -1)
        db=${psnr#average:}
        # MPEG-2's IDCT is only specified to a tolerance (IEEE 1180), so decoders
        # may differ by +-1. Every other codec here must match bit for bit.
        if [ "$name" = mpeg2 ] && awk -v d="$db" 'BEGIN { exit !(d + 0 >= 60) }'; then
            say "PASS  mpeg2: within IDCT tolerance (PSNR $db dB, +-1 level), $irqs engine interrupts"
            return 0
        fi
        say "DIFF  $name: decoded frames differ from the reference (PSNR $psnr)"
        return 1
    fi
}

fail=0
case "$which" in h264|all)
    run_case h264 "-c:v libx264 -preset veryfast -profile:v main -g 30 -bf 2 -f h264" h264 \
        "h264parse" v4l2slh264dec "38300000\.video-codec" || fail=$((fail + 1)) ;; esac
case "$which" in mpeg2|all)
    run_case mpeg2 "-c:v mpeg2video -b:v 8M -g 15 -f mpeg2video" m2v \
        "mpegvideoparse" v4l2slmpeg2dec "38300000\.video-codec" || fail=$((fail + 1)) ;; esac
case "$which" in vp8|all)
    run_case vp8 "-c:v libvpx -b:v 4M -g 30 -f ivf" ivf \
        "ivfparse" v4l2slvp8dec "38300000\.video-codec" || fail=$((fail + 1)) ;; esac
case "$which" in h265|all)
    run_case h265 "-c:v libx265 -preset ultrafast -x265-params keyint=30:bframes=2:log-level=error -f hevc" h265 \
        "h265parse" v4l2slh265dec "38310000\.video-codec" || fail=$((fail + 1)) ;; esac
case "$which" in vp9|all)
    run_case vp9 "-c:v libvpx-vp9 -b:v 4M -g 30 -deadline realtime -cpu-used 8 -f ivf" ivf \
        "ivfparse ! vp9parse" v4l2slvp9dec "38310000\.video-codec" || fail=$((fail + 1)) ;; esac

say ""
[ "$fail" = 0 ] && say "RESULT: ALL PASS" || say "RESULT: $fail case(s) did not pass"
exit "$fail"
