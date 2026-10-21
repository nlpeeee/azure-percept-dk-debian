# CAAM shutdown and SoC identification during kexec

## Superseded by the working trixie launcher

The user subsequently confirmed a working Debian trixie installation and
stock-kernel rescue shell, documented in `trixie-install.md`. That is the
current boot path. Subsequent work demonstrated the OCOTP-clock module in
experiment 06 and incorporated it into the working launcher, as recorded below.
The upper-RAM investigation retains that module pair. Experiment 05 remains
a historical negative result for the ring-reset-only approach.

## Latest result: experiment 06 reaches userspace

On 21 October 2026 at 09:49:41 UTC, `percept-entry-20261021-06` executed from
source boot `01a7578d-1475-4549-979c-8e175adb523f`. It used the unchanged stock
Image (SHA256 `fec6f292…7ef2`), quiet purgatory, UART tracing and core module
`caam-20261021-02/core.ko` (SHA256 `03cd9ebb…c4e9`) with
`percept_caam_reset=1 percept_ocotp_clock=1`. The command line had **no**
`initcall_blacklist`. All 25 hook records up to `execution_status value_2`
were acknowledged by the PC receiver.

UART shows, before the jump: `OCOTP clock pinned`, CAAM hwrng unregistered,
and JR0–JR2 reset with status/command zero (JR0 cfg `0xa0103`, JR1/JR2 `0x1`).
The target then printed:

```text
[   10.708273] calling  imx8_soc_init+0x0/0x354 @ 1
[   10.713598] initcall imx8_soc_init+0x0/0x354 returned 0 after 523 usecs
[   17.556401] caam_jr 30901000.jr: registering rng-caam
[   17.583792] initcall jr_driver_init+0x0/0x6c returned 0 after 65818 usecs
[   22.185185] EXT4-fs (mmcblk0p3): mounted filesystem with ordered data mode.
percept-dk login:
```

SSH reached the target about 59 s after the reboot request. It reported boot
`251af845-e3a3-4265-bdd4-0d0e90e76d31`, the experiment marker in
`/proc/cmdline`, `soc0` = i.MX8MQ revision 2.1, and `rng-caam` as the current
hwrng. The imx2 watchdog driver bound and kept the inherited hardware watchdog
fed. Docker containers started. `systemctl` reports `degraded` only because
`systemd-networkd-wait-online` failed; the journal shows the same failure on
the three preceding stock cold boots. The reset reason (`0x1`) and watchdog
counter (`0x16`) were unchanged: no watchdog reset or firmware A/B fallback
occurred.

This is the first same-kernel kexec boot to userspace. It supports the
inherited-OCOTP-clock explanation for the experiment 03 stall and the
SoC-identification dependency for the experiment 04/05 CAAM panic. It does not
isolate whether the ring reset is still required; that would need a run with
`percept_ocotp_clock=1` alone. The `CPUs started in inconsistent modes` warning
(EL1 handoff) remains.

The executed hook was archived to the experiment directory on the board and
removed from `/usr/lib/systemd/system-shutdown/`. The board is still running the
kexec'd kernel; a later ordinary reboot returns to the stock boot path.
PC evidence: `sources/firmware-audit/caam-20261021-02/`.

## Ring cleanup implemented

`sources/kexec-mod/kernel/percept_caam.c` implements opt-in Percept cleanup
with `percept_caam_reset=1`. Module initialization maps the three known
job-ring pages, resolves opaque host RNG and endian symbols, and performs
no reset. Immediately before device shutdown, the execution path unregisters
the CAAM hardware RNG through the host hwrng API, allowing pending jobs to
complete while interrupts still work. It leaves driver allocations alive.

After secondary CPUs stop, local interrupts and preemption are disabled.
All three rings are masked; each receives flush/halt and reset commands,
with 100 ms bounded waits per phase. Pending status is acknowledged and
interrupts remain masked. Failure aborts the jump and calls emergency restart.
UART records before/after registers for all three rings. No CAAM global reset
or security-provisioning change is performed.

The native fake-MMIO harness exercises the same reset C implementation for
little/big-endian accesses, mask ordering, W1C acknowledgement, timeout failures
and disabled mode. Both native builds and execution-disabled staging passed.

## Reset alone: experiment 05

On 21 October 2026 at 09:29:14 UTC, `percept-entry-20261021-05` executed from
source boot `ae9116ac-8ccf-4ee6-bac3-b060ba309a07`. It retained the stock
Image, UART tracing and `initcall_blacklist=imx8_soc_init` from experiment 04.
New prepared core SHA256:
`d90652a6c7d05d3e0b19903c9bb770683a21bc73075ac39485ade913d82f9254`.
The prior verified architecture module was unchanged.

UART confirmed RNG unregistration and successful resets at `0x30901000`,
`0x30902000` and `0x30903000`, each ending with status/command zero. The
uniquely marked target kernel nevertheless reproduced the same job-ring
error `0x103` and `caam_jr_interrupt` panic at 17.5 seconds. Therefore ring
cleanup alone is not a demonstrated fix for this panic.

Automatic recovery returned to stock boot
`01a7578d-1475-4549-979c-8e175adb523f`, original command line and unchanged
stock Image hash. The completed hook was removed. Recorded reset reason
was `0x1`, watchdog counter `0x16`.
PC evidence: `sources/firmware-audit/caam-20261021-01/`.

## Dependency found in SoC-init skip

The reconstructed CAAM source sets `caam_imx` from
`soc_device_match(caam_imx_soc_table)`. That flag selects i.MX-specific
high-word/low-word DMA address register ordering, and a successful match also
enables the SoC's CAAM clocks. The skipped `imx8_soc_init` normally registers
the SoC identification used by this lookup.

The actual stock Image confirms the match-to-flag dependency:
at Image offset `0xd9c55c`, `caam_probe` calls `soc_device_match`; at
`0xd9c570`, it stores the boolean result to `caam_imx`. The retained source
excerpt and vendor disassembly are `soc-caam-dependency.txt`. Thus the
diagnostic SoC-init skip can itself break CAAM initialization. The exact
failure transaction has not been captured; the write-error status alone
does not prove which DMA address was attempted.

The follow-up build adds `percept_ocotp_clock=1`. It obtains the existing
OCOTP clock through the host clock API, enables it only during execution,
and retains it across handoff. The fresh target command line restores normal
SoC initialization by omitting the blacklist. This tests the inherited
OCOTP clock-gating hypothesis while retaining the ring cleanup. The vendor
SoC-revision routine also calls firmware, so clock gating remains a hypothesis
until a successful target SoC init is observed.
