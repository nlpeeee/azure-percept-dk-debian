#!/bin/bash
# PC-side warm-reboot soak: N consecutive reboots, each followed by the full
# hardware check. Records time-to-SSH and when the launcher's boot-confirmation
# resets the failure counters. Stops at the first failure.
#   reboot-soak.sh [N] [--vpu]
# Warm reboots only: this is not the power-disconnected cold-boot gate.
set -u
n=${1:-3}
vpu=${2:-}
here=$(cd "$(dirname "$0")" && pwd)
host=${PERCEPT_HOST:?set PERCEPT_HOST to the board address}
key=${PERCEPT_KEY:-$HOME/.ssh/id_ed25519}
kh=${PERCEPT_KNOWN_HOSTS:-$HOME/.ssh/percept_known_hosts}
opts=(-i "$key" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5
      -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$kh" -o LogLevel=ERROR)
rs() { timeout 15 ssh "${opts[@]}" "root@$host" "$@" 2>/dev/null; }
log=${SOAK_LOG:-soak-$(date -u +%Y%m%dT%H%MZ).log}
say() { printf '%s\n' "$*" | tee -a "$log"; }

for i in $(seq 1 "$n"); do
    before=$(rs 'cat /proc/sys/kernel/random/boot_id') || { say "cycle $i: board unreachable before reboot"; exit 2; }
    # Refuse to reboot while the countdown is not armed: a reboot at percept_tries=0
    # would (correctly) land in rescue and invalidate the cycle.
    armed=$(rs 'grep -a -c "percept_tries=4" /boot/efi/boot/grub2/grubenv; cat /boot/efi/percept/failcount' | tr '\n' ' ')
    if [ "$armed" != "1 0 " ]; then say "cycle $i: counters not reset yet ($armed); waiting";
        for _ in $(seq 1 30); do sleep 5; armed=$(rs 'grep -a -c "percept_tries=4" /boot/efi/boot/grub2/grubenv; cat /boot/efi/percept/failcount' | tr '\n' ' '); [ "$armed" = "1 0 " ] && break; done
        [ "$armed" = "1 0 " ] || { say "cycle $i: counters never reset ($armed)"; exit 3; }
    fi
    say "=== cycle $i/$n  $(date -u +%H:%M:%SZ)  reboot from boot $before"
    rs '(sleep 1; systemctl reboot) >/dev/null 2>&1 & echo issued' >/dev/null
    t0=$SECONDS
    sleep 30
    new=''
    while [ $((SECONDS - t0)) -lt 600 ]; do
        r=$(rs 'cat /proc/sys/kernel/random/boot_id; uname -r; grep -c rescue_ready /run/launcher.log 2>/dev/null')
        id=$(echo "$r" | sed -n 1p); k=$(echo "$r" | sed -n 2p); resc=$(echo "$r" | sed -n 3p)
        if [ -n "$id" ] && [ "$id" != "$before" ]; then
            if [ "$k" = 6.12.113+deb13-arm64 ]; then new=$id; break; fi
            say "cycle $i: came up on '$k' (rescue_ready=$resc), not trixie"; exit 4
        fi
        sleep 5
    done
    [ -n "$new" ] || { say "cycle $i: no new trixie boot within 10 minutes"; exit 5; }
    ssh_s=$((SECONDS - t0))
    say "cycle $i: SSH up ${ssh_s}s after reboot request, boot $new"
    # Wait for the launcher counters to be reset by boot confirmation.
    confirmed=''
    while [ $((SECONDS - t0)) -lt 600 ]; do
        c=$(rs 'grep -a -c "percept_tries=4" /boot/efi/boot/grub2/grubenv; cat /boot/efi/percept/failcount' | tr '\n' ' ')
        if [ "$c" = "1 0 " ]; then confirmed=$((SECONDS - t0)); break; fi
        sleep 4
    done
    [ -n "$confirmed" ] && say "cycle $i: boot confirmed (counters reset) ${confirmed}s after reboot request" \
                        || { say "cycle $i: boot was NEVER confirmed"; exit 6; }
    if bash "$here/verify-boot.sh" $vpu | tee -a "$log"; then say "cycle $i: ALL PASS"; else say "cycle $i: FAILURES above"; exit 7; fi
done
say "SOAK COMPLETE: $n/$n cycles passed"
