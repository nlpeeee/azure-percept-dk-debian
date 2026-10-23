#!/bin/bash
# SPDX-License-Identifier: MIT
# PC-side audio check of the Azure Percept Ear SoM (hw:PerceptEar,0). Writes only temp WAVs on the
# board, removed afterwards.
#   audio-check.sh [SECONDS]    records SECONDS (default 8), then records again while playing a
#                               -20 dBFS 1 kHz tone; prints PASS/FAIL lines, exits non-zero on FAIL
#
# Needs key-based root (or sudo) SSH to the board: set PERCEPT_HOST and optionally PERCEPT_KEY.
# The board needs alsa-utils and python3 (the installer's `audio` feature installs alsa-utils).
# ch0-3 only need to be above digital silence (about -62 dBFS in a quiet room).
set -u
host=${PERCEPT_HOST:?set PERCEPT_HOST to the board address}
key=${PERCEPT_KEY:-$HOME/.ssh/id_ed25519}
kh=${PERCEPT_KNOWN_HOSTS:-$HOME/.ssh/percept_known_hosts}
secs=${1:-8}
case $secs in ''|*[!0-9]*|0) echo "usage: $0 [SECONDS]" >&2; exit 2 ;; esac
ssh_opts=(-i "$key" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8
          -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$kh" -o LogLevel=ERROR)

out=$(ssh "${ssh_opts[@]}" "root@$host" "SECS=$secs sh -s" <<'REMOTE' 2>&1
tmp=$(mktemp -d /tmp/audio-check.XXXXXX) || exit 1
trap 'rm -rf "$tmp"' EXIT
dev=hw:PerceptEar,0
cat >"$tmp/an.py" <<'PY'
import sys, wave, math, array
w = wave.open(sys.argv[1], 'rb')
ch, sw, n = w.getnchannels(), w.getsampwidth(), w.getnframes()
raw = w.readframes(n)
print("fmt=ch%d sw%d rate%d frames%d" % (ch, sw, w.getframerate(), n))
if sw != 4 or n == 0:
    print("bad=1")
    sys.exit(0)
a = array.array('i')
a.frombytes(raw[:len(raw) // 4 * 4])
if sys.byteorder == 'big':
    a.byteswap()
full = 2147483648.0
def db(v):
    return -200.0 if v <= 0 else 20 * math.log10(v / full)
for c in range(ch):
    s = a[c::ch]
    peak = max(abs(x) for x in s) if s else 0
    rms = math.sqrt(sum(float(x) * x for x in s) / len(s)) if s else 0.0
    print("ch%d rms=%.1f peak=%.1f zero=%d" % (c, db(rms), db(peak), 1 if peak == 0 else 0))
PY
cat >"$tmp/tone.py" <<'PY'
import sys, wave, math, struct
rate, secs = 16000, int(sys.argv[2]) + 3
amp = 10 ** (-20 / 20.0) * 2147483647
w = wave.open(sys.argv[1], 'wb')
w.setnchannels(2)
w.setsampwidth(4)
w.setframerate(rate)
fr = bytearray()
for i in range(rate * secs):
    v = int(amp * math.sin(2 * math.pi * 1000 * i / rate))
    fr += struct.pack('<ii', v, v)
w.writeframes(bytes(fr))
w.close()
PY
python3 "$tmp/tone.py" "$tmp/tone.wav" "$SECS"
if arecord -q -D "$dev" -c 5 -f S32_LE -r 16000 -d "$SECS" "$tmp/idle.wav" 2>"$tmp/e1"; then
    python3 "$tmp/an.py" "$tmp/idle.wav" | sed 's/^/idle./'
else
    echo "idle.error=$(tr '\n' ' ' <"$tmp/e1")"
fi
aplay -q -D "$dev" "$tmp/tone.wav" 2>"$tmp/e2" &
ap=$!
sleep 1
if arecord -q -D "$dev" -c 5 -f S32_LE -r 16000 -d "$SECS" "$tmp/tone_rec.wav" 2>"$tmp/e3"; then
    python3 "$tmp/an.py" "$tmp/tone_rec.wav" | sed 's/^/tone./'
else
    echo "tone.error=$(tr '\n' ' ' <"$tmp/e3")"
fi
kill "$ap" 2>/dev/null
wait "$ap" 2>/dev/null
[ -s "$tmp/e2" ] && echo "aplay.error=$(tr '\n' ' ' <"$tmp/e2")"
exit 0
REMOTE
) || { echo "FAIL ssh: cannot reach $host"; exit 2; }

get() { printf '%s\n' "$out" | sed -n "s/^$1=//p" | head -1; }
fails=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; fails=$((fails + 1)); }
info() { printf 'INFO  %s\n' "$1"; }
check() { if [ "$2" = 1 ]; then pass "$1"; else fail "$1"; fi; }
# field LINEPREFIX KEY -> value of key= on the line "LINEPREFIX key=v key=v ..."
field() { printf '%s\n' "$out" | grep "^$1 " | head -1 | tr ' ' '\n' | sed -n "s/^$2=//p"; }
gt() { awk -v a="$1" -v b="$2" 'BEGIN{exit !(a > b)}'; }

info "recording ${secs}s per pass from hw:PerceptEar,0 on $host"
for ph in idle tone; do
    [ -n "$(get "$ph.error")" ] && fail "$ph capture failed: $(get "$ph.error")"
done
[ -n "$(get aplay.error)" ] && fail "aplay failed: $(get aplay.error)"

for c in 0 1 2 3; do
    rms=$(field "idle.ch$c" rms); z=$(field "idle.ch$c" zero)
    if [ -z "$rms" ]; then fail "mic ch$c: no idle data"; continue; fi
    check "mic ch$c not silent (idle rms ${rms} dBFS, > -90, not all zeros)" \
        "$([ "$z" = 0 ] && gt "$rms" -90 && echo 1)"
done
info "ch4 reference idle rms $(field idle.ch4 rms) dBFS"
p4=$(field "tone.ch4" peak)
if [ -z "$p4" ]; then
    fail "ch4: no data while playing"
else
    check "ch4 reference peak ${p4} dBFS within 1 dB of -20 dBFS while playing" \
        "$(awk -v p="$p4" 'BEGIN{d=p+20; if (d<0) d=-d; exit !(d<=1)}' && echo 1)"
fi
[ "$fails" = 0 ] && echo "RESULT: ALL PASS" || echo "RESULT: $fails FAIL"
exit $((fails > 0))
