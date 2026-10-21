#!/bin/sh
# SPDX-License-Identifier: MIT
# Bounded, opt-in on-device CPU test. Running --help changes nothing.
set -eu
usage() {
    cat <<'EOF'
Usage: run-cpu-test.sh --frequency-khz KHZ --duration-seconds SECONDS
       --boot-id ID --output NEW_DIRECTORY [--workload cpu|mixed|idle]
       [--allow-overclock] [--network HOST --temp-parent DIRECTORY]

KHZ: 800000, 1300000 or 1500000 (last requires --allow-overclock).
Duration: 1..3600 seconds. Default action is help; no implicit test.
Mixed adds 64 MiB storage verification, bounded VM load and network checks.
Requires root, stress-ng, setsid, timeout, ping (mixed), readable debugfs,
thermal sensors, kernel log access and an already configured cpufreq policy0.
Every armed exit stops only this run's process groups and caps at 1300000 kHz.
Does not install drivers, alter DT/voltage, reboot, or restore a prior OC rate.
EOF
}
[ "$#" -gt 0 ] || { usage; exit 0; }
freq= duration= expected_boot= output= workload=cpu network= temp_parent= allow_oc=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --allow-overclock) allow_oc=1; shift ;;
        --frequency-khz|--duration-seconds|--boot-id|--output|--workload|--network|--temp-parent)
            [ "$#" -ge 2 ] || { echo "Missing value for $1" >&2; exit 2; }
            case "$1" in
                --frequency-khz) freq=$2 ;; --duration-seconds) duration=$2 ;;
                --boot-id) expected_boot=$2 ;; --output) output=$2 ;;
                --workload) workload=$2 ;; --network) network=$2 ;;
                --temp-parent) temp_parent=$2 ;;
            esac
            shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
case "$freq" in 800000|1300000) ;; 1500000) [ "$allow_oc" = 1 ] || { echo '1500000 requires --allow-overclock' >&2; exit 2; } ;; *) echo 'Explicit supported frequency required' >&2; exit 2 ;; esac
case "$duration" in ''|*[!0-9]*) echo 'Explicit integer duration required' >&2; exit 2 ;; esac
[ "$duration" -ge 1 ] && [ "$duration" -le 3600 ] || { echo 'Duration must be 1..3600' >&2; exit 2; }
case "$workload" in cpu|idle) ;; mixed) [ -n "$network" ] && [ -n "$temp_parent" ] || { echo 'Mixed requires --network and --temp-parent' >&2; exit 2; } ;; *) echo 'Invalid workload' >&2; exit 2 ;; esac
[ -n "$expected_boot" ] && [ -n "$output" ] || { echo '--boot-id and --output required' >&2; exit 2; }
case "$network" in -*) echo 'Invalid network host' >&2; exit 2 ;; esac
[ "$(id -u)" = 0 ] || { echo 'Root required' >&2; exit 1; }
for tool in stress-ng setsid timeout awk date dmesg mktemp; do
    command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done
[ "$workload" != mixed ] || command -v ping >/dev/null
policy=/sys/devices/system/cpu/cpufreq/policy0
clock=/sys/kernel/debug/clk/clk_summary
regulator=/sys/kernel/debug/regulator/regulator_summary
gpio=/sys/kernel/debug/gpio
boot=/proc/sys/kernel/random/boot_id
[ "$(cat "$boot")" = "$expected_boot" ] || { echo 'Boot ID mismatch' >&2; exit 1; }
[ "$(uname -r)" = '6.12.113+deb13-arm64' ] || { echo 'Unexpected kernel' >&2; exit 1; }
for file in "$policy/scaling_min_freq" "$policy/scaling_max_freq" "$policy/scaling_governor" "$policy/scaling_available_frequencies" "$clock" "$regulator" "$gpio"; do
    [ -r "$file" ] || { echo "Required interface missing: $file" >&2; exit 1; }
done
awk -v f="$freq" 'BEGIN {ok=0} {for(i=1;i<=NF;i++) if($i==f) ok=1} END {exit !ok}' "$policy/scaling_available_frequencies" || { echo 'Frequency absent from active OPP policy' >&2; exit 1; }
awk '{for(i=1;i<=NF;i++) if($i=="performance") ok=1} END {exit !ok}' "$policy/scaling_available_governors" || { echo 'performance governor unavailable' >&2; exit 1; }
[ ! -e "$output" ] || { echo 'Output directory already exists' >&2; exit 1; }
umask 077
mkdir -p "$output"
output=$(cd "$output" && pwd)
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >>"$output/events.log"; }
fail() { log "FAIL $*"; echo "$*" >&2; exit 1; }
stress_pid= logger_pid= ping_pid= work= armed=0
stop_group() {
    [ -n "$1" ] || return 0
    kill -TERM -"$1" 2>/dev/null || :
    # Bounded grace; group kill also covers workers whose leader already exited.
    sleep 1
    kill -KILL -"$1" 2>/dev/null || :
    wait "$1" 2>/dev/null || :
}
cap() {
    min=$(cat "$policy/scaling_min_freq") || return 1
    [ "$min" -le 1300000 ] || printf '1300000\n' >"$policy/scaling_min_freq" || return 1
    printf '1300000\n' >"$policy/scaling_max_freq" || return 1
    [ "$(cat "$policy/scaling_max_freq")" -le 1300000 ]
}
cleanup() {
    rc=$?
    trap - 0 INT TERM HUP
    stop_group "$stress_pid"
    stop_group "$ping_pid"
    if [ "$armed" = 1 ]; then
        if cap; then log 'cleanup cap_khz=1300000'; else log 'FAIL cleanup_cap_failed'; rc=1; fi
    fi
    stop_group "$logger_pid"
    [ -z "$work" ] || rm -rf -- "$work"
    log "exit_status=$rc boot=$(cat "$boot" 2>/dev/null || echo unavailable)"
    exit "$rc"
}
trap cleanup 0
trap 'log signal=INT; exit 130' INT
trap 'log signal=TERM; exit 143' TERM
trap 'log signal=HUP; exit 129' HUP
sample() {
    [ "$(cat "$boot")" = "$expected_boot" ] || fail 'Boot ID changed'
    actual=$(awk '$1=="arm_a53_core" {print $5; n++} END {if(n!=1) exit 1}' "$clock") || fail 'Cannot read unique arm_a53_core clock'
    case "$actual" in ''|*[!0-9]*) fail 'Invalid arm_a53_core clock' ;; esac
    log "requested_khz=$freq actual_arm_a53_core_hz=$actual min_khz=$(cat "$policy/scaling_min_freq") max_khz=$(cat "$policy/scaling_max_freq") cur_khz=$(cat "$policy/scaling_cur_freq")"
    found=0
    for zone in /sys/class/thermal/thermal_zone*; do
        [ -r "$zone/temp" ] || continue
        value=$(cat "$zone/temp") || fail 'Temperature read failed'
        case "$value" in ''|*[!0-9]*) fail 'Invalid temperature' ;; esac
        found=1
        log "thermal_zone=$zone type=$(cat "$zone/type") millidegrees=$value"
        [ "$value" -lt 80000 ] || fail "Thermal stop at $value mC"
    done
    [ "$found" = 1 ] || fail 'No readable thermal sensor'
    {
        printf '\n%s\n' "$(date -u +%FT%TZ)"
        cat "$regulator" "$gpio"
        for cooling in /sys/class/thermal/cooling_device*; do
            [ -r "$cooling/cur_state" ] || continue
            printf '%s type=%s state=%s max=%s\n' "$cooling" "$(cat "$cooling/type")" "$(cat "$cooling/cur_state")" "$(cat "$cooling/max_state")"
        done
    } >>"$output/power-state.log"
    [ ! -s "$output/new-kernel-errors.log" ] || fail 'New kernel error; inspect new-kernel-errors.log'
}
log "start boot=$expected_boot kernel=$(uname -r) frequency_khz=$freq duration_seconds=$duration workload=$workload"
uname -a >"$output/uname.txt"
cat /proc/cmdline >"$output/cmdline.txt"
dmesg >"$output/dmesg-before.log" || fail 'Kernel log unavailable'
# follow-new excludes historical errors; do not clear the kernel ring buffer.
setsid dmesg --follow-new --level=emerg,alert,crit,err,warn >"$output/new-kernel-errors.log" 2>"$output/kernel-monitor-errors.log" &
logger_pid=$!
sleep 1
kill -0 "$logger_pid" 2>/dev/null || fail 'Kernel error monitor failed'
# Arm before any policy mutation. All subsequent exits attempt the safe cap.
armed=1
sample
cap || fail 'Cannot establish 1300 MHz safety cap'
printf 'performance\n' >"$policy/scaling_governor" || fail 'Cannot select governor'
# Lower min first, then select max and finally min: valid for either direction.
printf '800000\n' >"$policy/scaling_min_freq" || fail 'Cannot lower policy minimum'
printf '%s\n' "$freq" >"$policy/scaling_max_freq" || fail 'Cannot set policy maximum'
printf '%s\n' "$freq" >"$policy/scaling_min_freq" || fail 'Cannot set policy minimum'
sleep 1
sample
[ "$actual" = "$((freq * 1000))" ] || fail 'Requested frequency did not become active'
set -- --verify --metrics-brief --timeout "${duration}s" --cpu 4 --cpu-method all
if [ "$workload" = mixed ]; then
    [ -d "$temp_parent" ] || fail 'Temp parent does not exist'
    work=$(mktemp -d "$temp_parent/percept-cpu-test.XXXXXXXX") || fail 'Cannot make private storage directory'
    set -- "$@" --vm 1 --vm-bytes 64M --vm-keep --hdd 1 --hdd-bytes 64M --temp-path "$work"
    setsid timeout --kill-after=1s 3s ping -n -c 1 -W 2 "$network" >>"$output/network.log" 2>&1 &
    ping_pid=$!
    wait "$ping_pid" || fail 'Initial network check failed'
    ping_pid=
fi
if [ "$workload" = idle ]; then
    setsid sleep "$duration" >"$output/idle.log" 2>&1 &
else
    setsid stress-ng "$@" >"$output/stress-ng.log" 2>&1 &
fi
stress_pid=$!
monotonic_seconds() { awk '{print int($1)}' /proc/uptime; }
started=$(monotonic_seconds)
last_ping=0
while kill -0 "$stress_pid" 2>/dev/null; do
    sample
    kill -0 "$logger_pid" 2>/dev/null || fail 'Kernel monitor exited'
    elapsed=$(($(monotonic_seconds) - started))
    [ "$elapsed" -le "$((duration + 10))" ] || fail 'Workload exceeded deadline'
    if [ "$workload" = mixed ] && [ "$((elapsed - last_ping))" -ge 10 ]; then
        setsid timeout --kill-after=1s 3s ping -n -c 1 -W 2 "$network" >>"$output/network.log" 2>&1 &
        ping_pid=$!
        wait "$ping_pid" || fail 'Network check failed'
        ping_pid=
        last_ping=$elapsed
    fi
    sleep 1
done
if wait "$stress_pid"; then :; else fail 'Workload correctness/resource failure'; fi
# Keep group ID until cleanup so stray children cannot outlive this run.
sample
kill -0 "$logger_pid" 2>/dev/null || fail 'Kernel monitor exited'
log 'PASS bounded workload completed; see telemetry and stress-ng metrics'
