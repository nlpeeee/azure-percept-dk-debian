#!/bin/sh
# SPDX-License-Identifier: MIT
# Paired sysbench measurements; no install/reboot/voltage changes.
set -eu
[ "$#" = 2 ] || { echo 'Usage: benchmark.sh EXPECTED_BOOT_ID NEW_OUTPUT_DIR'; exit 2; }
boot=$1 out=$2
[ "$(cat /proc/sys/kernel/random/boot_id)" = "$boot" ] || exit 1
[ ! -e "$out" ] || exit 1
mkdir -p "$out"
policy=/sys/devices/system/cpu/cpufreq/policy0
child=
cleanup() {
    status=$?
    trap - 0 INT TERM HUP
    if [ -n "$child" ]; then
        kill -TERM -"$child" 2>/dev/null || :
        sleep 1
        kill -KILL -"$child" 2>/dev/null || :
        wait "$child" 2>/dev/null || :
    fi
    printf '800000\n' >"$policy/scaling_min_freq" || status=1
    printf '1300000\n' >"$policy/scaling_max_freq" || status=1
    printf 'schedutil\n' >"$policy/scaling_governor" || status=1
    printf 'exit_status=%s cleanup_cap_khz=1300000\n' "$status" >>"$out/status.txt"
    exit "$status"
}
trap cleanup 0
trap 'exit 143' TERM HUP
trap 'exit 130' INT
uname -a >"$out/context.txt"
sysbench --version >>"$out/context.txt"
cat /proc/cmdline /proc/loadavg >>"$out/context.txt"
printf 'timestamp,stage,arm_a53_core_hz,temperature_mc\n' >"$out/telemetry.csv"
run() {
    name=$1 seconds=$2
    shift 2
    printf '%s START %s\n' "$(date -u +%FT%TZ)" "$name" | tee -a "$out/status.txt"
    printf '%s\n' "$*" >"$out/$name.command.txt"
    setsid timeout --kill-after=3s "$((seconds + 15))s" "$@" >"$out/$name.txt" 2>&1 &
    child=$!
    while kill -0 "$child" 2>/dev/null; do
        temperature=$(cat /sys/class/thermal/thermal_zone0/temp)
        actual_rate=$(awk '$1=="arm_a53_core" {print $5}' /sys/kernel/debug/clk/clk_summary)
        printf '%s,%s,%s,%s\n' "$(date -u +%FT%TZ)" "$name" "$actual_rate" "$temperature" >>"$out/telemetry.csv"
        [ "$temperature" -lt 80000 ] || { echo 'Thermal stop' >&2; exit 1; }
        sleep 1
    done
    wait "$child"
    child=
    printf '%s PASS %s\n' "$(date -u +%FT%TZ)" "$name" | tee -a "$out/status.txt"
}
for rate in 1300000 1500000; do
    printf '800000\n' >"$policy/scaling_min_freq"
    printf '%s\n' "$rate" >"$policy/scaling_max_freq"
    printf '%s\n' "$rate" >"$policy/scaling_min_freq"
    printf 'performance\n' >"$policy/scaling_governor"
    run "cpu-$rate" 60 sysbench cpu --threads=4 --cpu-max-prime=10000 --time=60 run
    for threads in 1 4; do
        run "memory-$rate-t$threads" 10 sysbench memory --threads="$threads" --time=10 \
            --memory-block-size=1K --memory-total-size=100G --memory-scope=global \
            --memory-oper=write --memory-access-mode=seq run
    done
done
echo 'PASS paired benchmarks' >>"$out/status.txt"
