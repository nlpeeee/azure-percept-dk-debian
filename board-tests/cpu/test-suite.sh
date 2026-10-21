#!/bin/sh
# SPDX-License-Identifier: MIT
# Sequential runner only: no install, reboot, direct clock or voltage writes.
set -eu
usage() {
    cat <<'EOF'
Usage: test-suite.sh --suite smoke|minute|rated|oc1500 --boot-id ID
       --output-root NEW_DIRECTORY --network HOST --temp-parent DIRECTORY
       [--allow-overclock]

Default: help, no test. Every suite needs explicit boot ID and new output root.
smoke: 800 MHz CPU 5s, 1300 MHz mixed 5s, 800 MHz idle 5s.
minute: 800 MHz CPU 60s, 1300 MHz mixed 60s, 1500 MHz mixed 60s.
        Requires --allow-overclock.
rated: 800 MHz CPU 900s, 1300 MHz CPU 900s, then fifteen 30s idle
       (800 MHz)/30s mixed (1300 MHz) pairs: 900s alternation.
oc1500: 1500 MHz CPU 60s, 300s, 1800s, then mixed 3600s.
         Requires --allow-overclock; stops after each failed stage.
Mixed includes verified CPU/VM/storage and bounded network checks.
No automatic reboot. Signal forwards to the active runner, which caps at 1300.
EOF
}
[ "$#" -gt 0 ] || { usage; exit 0; }
suite= boot= output= network= temp_parent= allow_oc=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --allow-overclock) allow_oc=1; shift ;;
        --suite|--boot-id|--output-root|--network|--temp-parent)
            [ "$#" -ge 2 ] || { echo "Missing value for $1" >&2; exit 2; }
            case "$1" in
                --suite) suite=$2 ;; --boot-id) boot=$2 ;; --output-root) output=$2 ;;
                --network) network=$2 ;; --temp-parent) temp_parent=$2 ;;
            esac
            shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
case "$suite" in smoke|rated) ;; minute|oc1500) [ "$allow_oc" = 1 ] || { echo 'OC suite requires --allow-overclock' >&2; exit 2; } ;; *) echo 'Explicit valid suite required' >&2; exit 2 ;; esac
[ -n "$boot" ] && [ -n "$output" ] && [ -n "$network" ] && [ -n "$temp_parent" ] || { echo 'boot ID, output root, network and temp parent required' >&2; exit 2; }
case "$network" in -*) echo 'Invalid network host' >&2; exit 2 ;; esac
runner=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/run-cpu-test.sh
[ -r "$runner" ] || { echo 'Adjacent run-cpu-test.sh missing' >&2; exit 1; }
[ ! -e "$output" ] || { echo 'Output root already exists' >&2; exit 1; }
umask 077
mkdir -p "$output"
output=$(cd "$output" && pwd)
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$output/suite.log"; }
child=
forward() {
    signal=$1
    status=$2
    # Ignore further catchable signals while waiting for runner cleanup.
    trap '' INT TERM HUP
    log "INTERRUPTED signal=$signal child=${child:-none}"
    if [ -n "$child" ]; then
        kill -TERM "$child" 2>/dev/null || :
        wait "$child" 2>/dev/null || :
    fi
    log "STOP status=$status; inspect last stage cleanup cap evidence"
    exit "$status"
}
trap 'forward INT 130' INT
trap 'forward TERM 143' TERM
trap 'forward HUP 129' HUP
stage() {
    label=$1 rate=$2 seconds=$3 work=$4
    log "START stage=$label requested_khz=$rate duration_seconds=$seconds workload=$work boot=$boot"
    set -- --frequency-khz "$rate" --duration-seconds "$seconds" --boot-id "$boot" \
        --output "$output/$label" --workload "$work"
    [ "$rate" != 1500000 ] || set -- "$@" --allow-overclock
    [ "$work" != mixed ] || set -- "$@" --network "$network" --temp-parent "$temp_parent"
    sh "$runner" "$@" >"$output/$label.console.log" 2>&1 &
    child=$!
    if wait "$child"; then
        child=
        log "PASS stage=$label"
    else
        status=$?
        child=
        log "FAIL stage=$label status=$status; stopping suite"
        exit "$status"
    fi
}
log "BEGIN suite=$suite boot=$boot network=$network temp_parent=$temp_parent"
case "$suite" in
    smoke)
        stage 01-800-cpu 800000 5 cpu
        stage 02-1300-mixed 1300000 5 mixed
        stage 03-800-idle 800000 5 idle ;;
    minute)
        stage 01-800-cpu 800000 60 cpu
        stage 02-1300-mixed 1300000 60 mixed
        stage 03-1500-mixed 1500000 60 mixed ;;
    rated)
        stage 01-800-cpu 800000 900 cpu
        stage 02-1300-cpu 1300000 900 cpu
        pair=1
        while [ "$pair" -le 15 ]; do
            serial=$(printf '%02d' "$pair")
            stage "alt-$serial-800-idle" 800000 30 idle
            stage "alt-$serial-1300-mixed" 1300000 30 mixed
            pair=$((pair + 1))
        done ;;
    oc1500)
        stage 01-1500-cpu-1min 1500000 60 cpu
        stage 02-1500-cpu-5min 1500000 300 cpu
        stage 03-1500-cpu-30min 1500000 1800 cpu
        stage 04-1500-mixed-60min 1500000 3600 mixed ;;
esac
log "PASS suite=$suite complete; no reboot requested"
