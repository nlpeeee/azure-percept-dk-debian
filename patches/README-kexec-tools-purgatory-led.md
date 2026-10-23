# kexec-tools ARM64 purgatory GPIO LED telemetry

Instruments the kexec-tools `purgatory/arch/arm64` handoff with the verified
GPIO3/bit23 LED so the warm-reboot path can be bisected without UART:

```
relocate_kernel.S  ──▶  purgatory_start  ──▶  verify_sha256_digest  ──▶  br x17 (kernel)
                         [CP1: 1 pulse]        [CP2: 2 pulses]            [CP3: 5 pulses]
```

- **CP1 (1 pulse)** — `entry.S`, right after `mov sp, x19`, before `bl purgatory`.
  CPU transitioned from `relocate_kernel.S` into purgatory.
- **CP2 (2 pulses)** — `purgatory-arm64.c`, first line of
  `post_verification_setup_arch()`, which the generic `purgatory()` calls only
  on the sha256-success path, immediately before returning to `entry.S`.
- **CP3 (5 pulses)** — `entry.S`, after `purgatory` returns, before loading the
  kernel entry and DTB, zeroing x1–x3, and executing `br x17`. This checkpoint
  does not prove the branch executed or Linux started.

## Files

- `kexec-tools-arm64-purgatory-led-telemetry.patch` — apply with `git apply -p1`
  or `patch -p1` from the kexec-tools source root. Touches `entry.S`,
  `purgatory-arm64.c`, the arm64 `Makefile`, and adds `led.S`.
- `kexec-tools-arm64-purgatory-led.S` — standalone copy of the new `led.S` for
  review; the patch creates the same file at `purgatory/arch/arm64/led.S`.

`led_signal(unsigned int count)` is freestanding and scratch-register-only: it
touches no stack or static memory, only the board-verified GPIO MMIO, and
clobbers only x0–x16, so it is AAPCS-safe as a leaf. Its caller must still have
a valid return address and execution context. It pulses `count` times, adds
a trailing dark gap, and **returns** — it does not loop forever like the terminal
`experiments/percept-led/led.S` probe. It does not touch DAIF or the watchdog.

## Checked against the real v2.0.25 source (not assumed)

- **Stack / AAPCS calls:** the brief's `stp x29, x30, [sp, #-192]!` is the C
  function's own prologue, not the entry point. `entry.S` establishes the stack
  with `adr x19, .Lstack; mov sp, x19`. The conclusion stands — a valid stack
  exists before any call — so CP1 is placed **after** that `mov sp`.
- **SHA256 verification:** confirmed. Generic `purgatory()` calls
  `verify_sha256_digest()`; on mismatch it `for(;;)` **hangs inside purgatory**,
  so "1 pulse then frozen" can mean slow verification, checksum failure, a
  fault, or watchdog expiry before CP2. It does not uniquely identify corruption.
- **Correction — there is no secondary-core/state-handling loop in purgatory.**
  Between CP2 (verify success) and CP3 (`br x17`) the only code is
  `post_verification_setup_arch()`'s printf and loading the entry/DTB registers.
  Secondary-core bring-up is in the kernel's `head.S`, **after** the branch. So
  "2 pulses but not 5" places the last observation before CP3. CP2's own delay,
  the return/printf path, or a reset can prevent CP3. It does not establish that
  execution reached `br x17` or any kernel code.

## Diagnostic matrix (as instrumented)

| LED | Reached | Interpretation |
|-----|---------|----------------|
| 0 pulses | no visible checkpoint | pre-entry failure, LED failure or missed observation |
| 1 pulse only | CP1 | slow/failed verification, fault or reset before CP2 |
| 1→2 pulses only | CP1, CP2 | checks passed when `skip_checks=0`; no evidence of reaching CP3 |
| 1→2→5 pulses | CP1, CP2, CP3 | reached final pre-branch checkpoint; Linux execution still unproven |

## Short-signal revision (21 October 2026)

The original deployed code used `DELAY_LOOPS=0x1000000` and six dark units on
both sides of every burst: 52 units for all checkpoints. At the earlier observed
five seconds per unit, that could consume about 260 seconds without counting
SHA256. The i.MX driver programs at most 128 seconds of hardware countdown and
refreshes it during shutdown; a reported 300/600-second userspace timeout does
not provide that long without servicing.

This revision uses `DELAY_LOOPS=0x100000`, no leading gap, and three extra dark
units after each burst: 25 shorter units total. The same observed rate predicts
roughly 0.31-second pulses and 7.8 seconds total. This is an estimate, not measured
timing or a guarantee that SHA256 fits the remaining watchdog budget.

Counts outside 1–8 return before GPIO access. Gap values outside 1–16 are rejected
at compile time; zero would otherwise underflow the decrement loop. The leaf
preserves x18–x30 and SP, uses fresh GPIO RMW, and finishes with the LED off.
The entry stub reloads all Linux arguments after CP3, so the helper's caller-saved
register clobbers do not corrupt them. No ABI bug was found in that existing order.

`experiments/percept-led/build-fast-checkpoints.sh` builds from the retained clean
archive into a separate directory. Its native userspace harness maps anonymous
fake-register pages and verifies return behaviour, x18–x29, invalid counts,
unrelated register bits and final LED state. It never accesses physical MMIO.
`tools/check_instrumented_bundle.py` checks the fresh bundle against the matching
ELF symbols, LED bytes, checksum table/digest, enabled checks and zero UART sink.

## Build and apply

The arm64 purgatory objects are built natively (same toolchain that builds the
kexec_mod modules). Get a source tree matching the installed binary
(`1:2.0.25-3+deb12u3`) and apply:

```bash
# Debian source (enable deb-src first), or upstream tag v2.0.25:
apt-get source kexec-tools            # -> kexec-tools-2.0.25/
cd kexec-tools-2.0.25
patch -p1 < /path/to/kexec-tools-arm64-purgatory-led-telemetry.patch
./configure && make                   # rebuilds purgatory/purgatory.ro
```

The Makefile hunk adds the GPIO `-D` values (identical to
`experiments/percept-led/BUILD.json`) to `arm64_PURGATORY_EXTRA_CFLAGS`, which
reach both the `.c` and `.S` purgatory sources. `led.S` keeps `#error` guards
(no silent defaults) consistent with the standalone probe.

Verified: `led.S` and the patched `entry.S` assemble cleanly on the target with
the Makefile flags (`-mcmodel=large -fno-PIC -fno-asynchronous-unwind-tables`
plus the GPIO defines); `led_signal` resolves, `purgatory_start` references it.

## Caveats

- Pass-through, one-shot bursts: if the kernel boots, CP1/CP2/CP3 flash and boot
  continues (the kernel may repurpose the LED). Watch or record the sequence at
  reboot. Avoid widening delays without accounting for the watchdog budget.
- Same uncalibrated-timing caveats as `experiments/percept-led/README.md`:
  I-cache is disabled on this path, so pulse width depends on fetch latency;
  pick a visible count before a live run.
- Retain and verify the existing watchdog/USB recovery; this code never services,
  reprograms, or disables the watchdog.
