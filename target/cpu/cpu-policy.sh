#!/bin/sh
# SPDX-License-Identifier: MIT
# Apply the qualified runtime policy after boot's powersave initialization.
set -eu
policy=/sys/devices/system/cpu/cpufreq/policy0
limit_file=/etc/percept-cpu/max-khz
limit=1300000
[ ! -f "$limit_file" ] || limit=$(cat "$limit_file")
case "$limit" in 1300000|1500000) ;; *) echo 'Invalid CPU policy maximum' >&2; exit 1 ;; esac
cap() {
    [ -w "$policy/scaling_min_freq" ] || return 0
    printf '800000\n' >"$policy/scaling_min_freq" || return 1
    printf '1300000\n' >"$policy/scaling_max_freq"
}
finish() {
    rc=$?
    trap - 0
    if [ "$rc" != 0 ]; then cap || echo 'CPU policy fallback cap failed' >&2; fi
    exit "$rc"
}
trap finish 0
trap 'exit 143' TERM HUP
trap 'exit 130' INT
ready=0
for attempt in $(seq 1 60); do
    if [ -r "$policy/scaling_available_frequencies" ]; then
        for cooling in /sys/class/thermal/thermal_zone0/cdev[0-9]*; do
            [ -r "$cooling/type" ] || continue
            if [ "$(cat "$cooling/type")" = cpufreq-cpu0 ]; then ready=1; break; fi
        done
    fi
    [ "$ready" = 0 ] || break
    sleep 1
done
[ "$ready" = 1 ] || { echo 'CPU policy/cooling device unavailable' >&2; exit 1; }
[ "$(awk '{$1=$1; print}' "$policy/affected_cpus")" = '0 1 2 3' ] || exit 1
for required in 800000 1300000 "$limit"; do
    case " $(cat "$policy/scaling_available_frequencies") " in
        *" $required "*) ;; *) echo "Missing CPU frequency $required" >&2; exit 1 ;;
    esac
done
case " $(cat "$policy/scaling_available_governors") " in *' schedutil '*) ;; *) exit 1 ;; esac
printf '800000\n' >"$policy/scaling_min_freq"
printf '%s\n' "$limit" >"$policy/scaling_max_freq"
printf 'schedutil\n' >"$policy/scaling_governor"
printf 'CPU policy: min=%s max=%s governor=%s\n' \
    "$(cat "$policy/scaling_min_freq")" "$(cat "$policy/scaling_max_freq")" \
    "$(cat "$policy/scaling_governor")"
