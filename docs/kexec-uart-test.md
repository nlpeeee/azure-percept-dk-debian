# UART-only kexec tests: Linux starts; CAAM panic after SoC-init skip

## Latest result: experiment 04

Experiment `percept-entry-20261021-04` was requested at 09:09:04 UTC
(10:09:04 London) on 21 October 2026. Source boot:
`d062f6a3-84a1-4391-b5de-9c90991d1a63`.

This test used the unchanged stock Image, quiet purgatory, fresh live FDT and
the existing verified module pair. The only diagnostic change from experiment
03 was `initcall_blacklist=imx8_soc_init`. Execution-disabled staging and the
external acknowledged logging check passed before the ordinary reboot.

UART printed the unique marker `percept_kexec_test=percept-entry-20261021-04`
and confirmed that the previous stall was bypassed:

```text
[   10.708317] initcall imx8_soc_init blacklisted
```

The target detected the HS400 eMMC, its 14.6 GiB user area and partitions
`mmcblk0p1`, `mmcblk0p2`, `mmcblk0p3`. This establishes storage detection;
it does not establish a mounted root filesystem or working target SSH.

The next failure was a CAAM crypto accelerator job-ring interrupt:

```text
[   17.497385] calling  jr_driver_init+0x0/0x6c @ 1
[   17.536687] caam_jr 30901000.jr: job ring error: irqstate: 00000103
[   17.548098] kernel BUG at drivers/crypto/caam/jr.c:187!
[   17.590721] pc : caam_jr_interrupt+0x1a4/0x1a8
[   17.764567] Kernel panic - not syncing: Fatal exception in interrupt
```

The local 5.4.3 source's `JRINT_ERR_TYPE_MASK`/shift decode `0x103` as error
type 1 (`JRINT_ERR_TYPE_WRITE`), with the error and interrupt bits set.
Its handler explicitly calls `BUG()` for a job-ring error, consistent with
the observed panic. This identifies the reported hardware error category,
not its underlying cause. Inherited device/DMA state across kexec is a
candidate requiring investigation. This is a runtime accelerator failure;
the trace does not show a boot-image authentication rejection.

The earlier inconsistent CPU boot-mode warning is still present. Skipping
SoC initialization remains a diagnostic omission, not a finished fix.

The board recovered automatically. SSH verified stock release `5.4.3-26.cm1`,
boot ID `ae9116ac-8ccf-4ee6-bac3-b060ba309a07`, and the original command line
without a test marker. Reset reason was `0x1`; watchdog counter remained
`0x16`. These recorded values alone do not identify the complete reset chain.
The completed one-shot hook was archived and removed; only `mdadm.shutdown`
remained in the shutdown-hook directory. The experiment's PC receiver was
stopped. `/boot/vmlinuz` still matches the original SHA256 below.

Evidence: `sources/firmware-audit/uart-20261021-02/`, including
`target-kernel.log`, `execution-uart.log`, `receiver.jsonl`,
`prepared-evidence.tar.gz`, `post-test-boot.txt`, and
`caam-source-excerpt.txt`. The retained bundle belongs to its old source boot
and must not be reused. A next discriminating test should isolate CAAM
job-ring initialization with a fresh bundle and UART capture; it has not
been executed as part of this experiment.

## Previous result: experiment 03

Experiment `percept-entry-20261021-03`, 21 October 2026. Reboot requested at
08:55:19 UTC (09:55:19 London), source boot
`1c5eb7fc-bdc3-4fd5-8c5c-b4e81b5ead0a`.

## Proven result

The unmodified stock Image booted through kexec. UART independently recorded:

```
[    0.000000] Booting Linux on physical CPU 0x0000000000 [0x410fd034]
[    0.000000] Linux version 5.4.3-26.cm1 ...
[    0.000000] earlycon: ec_imx6q0 at MMIO 0x0000000030860000 ...
```

The target's printed command line contains the unique marker
`percept_kexec_test=percept-entry-20261021-03` plus
`earlycon=ec_imx6q,0x30860000 ignore_loglevel initcall_debug`. This establishes
actual new-kernel execution, MMU setup, C initialization and secondary-CPU
bring-up. It does not establish a usable target userspace boot or target SSH.
There were no LED patches in the Image or purgatory. Checksums remained enabled.

## Failure boundary

The target reports all four CPUs online, then:

```
[    0.633655] CPU: CPUs started in inconsistent modes
...
[   10.710293] calling  imx8_soc_init+0x0/0x354 @ 1
[   31.715968] rcu: INFO: rcu_preempt detected stalls on CPUs/tasks:
[   31.719339] rcu:  1-...0: (0 ticks this GP) ...
```

There is no recorded return from `imx8_soc_init`. The stalled-task dump ends
with `__switch_to+0xe4/0x148` and `0x30350000`; that dump does not identify a
precise faulting instruction. `0x30350000` is the OCOTP peripheral's base.

The CPU-mode warning is a separate finding consistent with the selected EL1
handoff and firmware starting secondary CPUs through EL2. The kernel continues
after the warning; its causal relationship to the later stall is not proven.

The actual stock binary's `imx8mq_soc_revision` (Image offset `0x1adaec0`) was
disassembled after recovery. It includes a firmware call with function ID
`0xc2000006`, a fallback OCOTP read at offset `0x40`, and UID reads at offsets
`0x420` and `0x410`. The reconstructed upstream source omits that firmware
query, so its exact sequence must not be substituted for the vendor binary.

The recovered stock kernel reports `ocotp_root_clk` with enable/prepare counts
zero. An inherited clock-gating problem is a candidate, not a confirmed cause:
we have not captured the clock's hardware state at the stall or distinguished
the firmware call from the later register reads. No fuse/provisioning write was
performed or proposed as a fix.

## Recovery and next discriminator

UART records a watchdog reset followed by a firmware attempt to boot "SCZ OS B",
which fails with `PlatformBootManagerUnableToBoot ... Waiting for Watchdog!`.
A subsequent automatic fallback returns to the working stock installation.
This additional firmware cycle explains part of the long observed recovery.

Recovered stock boot: `d062f6a3-84a1-4391-b5de-9c90991d1a63`; no test marker.
Reset reason `0x2`, watchdog counter `0x16`. The executed hook was archived on
the board and removed. `/boot/vmlinuz` retains SHA256
`fec6f292e734ab81c056a28ab0c3940ec7f00fcd39cec417cac9da52bb3f7ef2`.

The next controlled discriminator is a freshly captured UART-only bundle with
the single additional argument `initcall_blacklist=imx8_soc_init`. Support for
that argument and `CONFIG_KALLSYMS=y` was checked in the matching tree. Observe
the skip and the next initcalls over UART; require a unique marker and new boot
ID through SSH before calling it a usable same-kernel boot. This would be a
diagnostic omission of SoC identification/associated setup, not a permanent fix.
If it passes this boundary, investigate the firmware/OCOTP clock handling and
assess the corresponding Debian driver before further kernel changes.

## Evidence

PC directory: `sources/firmware-audit/uart-20261021-01/`.

- `target-kernel.log`: new kernel's UART output through the stall/reset boundary.
- `execution-uart.log`: shutdown, handoff and firmware recovery output.
- `receiver.jsonl`: externally acknowledged execution records.
- `prepared-evidence.tar.gz`: hashes, fresh FDT, bundle checks and staging logs.
- `post-test-boot.txt`: recovered identity, reset indicators and hook cleanup.

The live PuTTY log remains `<LOCAL_PATH>\UART\putty.log` on <COM_PORT>, 115200 8N1,
flow control disabled. The full bundle is retained on the board in
`<LOCAL_PATH>/percept-entry-20261021-03`; it belongs to the old
source boot and must not be re-armed.
