# Debian arm64 kernel test

## Guiding principle (user direction, 21 October 2026)

Keep the Debian kernel as close to stock as possible. Prefer kernel command-line
switches and other boot-time configuration over rebuilding or patching the
Debian kernel. Workarounds such as `cpuidle.off=1` are the preferred form.

## Latest result: experiment 08, Debian 6.12 boots to its initramfs

On 21 October 2026 at 10:13:52 UTC, `percept-entry-20261021-08` executed from
stock boot `a01ac3ce-a97a-418c-b4ca-a795476f562a`. It was identical to experiment
07 plus the single switch `cpuidle.off=1`. UART and the target's own report show:

```text
[   13.037869] hw perfevents: enabled with armv8_cortex_a53 PMU driver, 7 (0,8000003f) counters available
[   16.087675] imx6q-pcie 33800000.pcie: PCIe Gen.1 x1 link up
[   17.065181] igb 0000:01:00.0: eth0: (PCIe:2.5Gb/s:Width x1) <board-mac>
[   17.454315] mmc1: new HS400 MMC card at address 0001
[   17.460745] mmcblk1: mmc1:0001 AJTD4R 14.6 GiB
```

The initramfs reported `6.12.113+deb13-arm64`, 4 CPUs, 3,040,388 kB RAM, and
12/12 modules loaded (with `imx2_wdt` first). Both PCIe links trained. Ethernet
came up as `eth0` with the board MAC. The PC received 9 UDP records and fetched
`/status.txt` over HTTP twice. This confirms the idle-state diagnosis for
experiment 07. Under 6.12 the **eMMC is `mmcblk1`** because the SD controller
takes `mmc0`, so a 6.12 root must be given by UUID, not `/dev/mmcblk0p3`.

Recovery: the initramfs timer requested a reboot at 182 s
(`reboot: Restarting system`). Firmware booted OS A directly, and the board
returned on stock boot `8810bf12-2ede-4b82-b724-0b34584ceded`. Reset reason
`0x1` and watchdog counter `0x16` were unchanged. The executed hook was archived
and removed. PC evidence: `sources/firmware-audit/debian-20261021-08/`
(`status-*.txt`, `target-dmesg.txt`, `receiver.jsonl`).

Next: a clean trixie install replacing Bookworm, with the kexec launcher moved
into an ESP initramfs for the stock kernel. See `docs/trixie-install.md`.

## Experiment 07 (kexec), hang after CPU idle registration

On 21 October 2026 at 10:04:04 UTC, `percept-entry-20261021-07` executed from
stock boot `c5f308fe-c298-4da9-8f87-7913e05d2b38` through the kexec path proven
in experiment 06 (`percept_caam_reset=1 percept_ocotp_clock=1`). The bundle held
the Debian Image (`391a3b39…`), a RAM-only initramfs built for that boot
(`experiments/percept-debian/prepare-debian-test.sh`, `imx2_wdt` loaded first),
the boot's live FDT with fresh EFI memory-map references, and quiet purgatory.
Command line: `console=ttymxc0,115200 earlycon=ec_imx6q,0x30860000
ignore_loglevel initcall_debug clk_ignore_unused pd_ignore_unused efi=noruntime`
plus the marker.

UART proves Debian kernel execution:

```text
[    0.000000] Linux version 6.12.113+deb13-arm64 (debian-kernel@lists.debian.org) ...
[    0.702555] smp: Brought up 1 node, 4 CPUs
[    0.767775] CPU: CPUs started in inconsistent modes
[   12.619650] probe of psci-cpuidle returned 0 after 426 usecs
[   13.032619] calling  armv8_pmu_driver_init+0x0/0x70 @ 1
```

Output stops there with no RCU stall report, so the initramfs never ran and no
target UDP/HTTP report was produced. The board's DT gives every CPU one idle
state, `cpus/idle-states/cpu-sleep` (`arm,psci-suspend-param = 0x00010033`,
`local-timer-stop`). The stock vendor kernel never uses it:

```text
irq-imx-gpcv2: EL3 does not support FSL_SIP_CONFIG_GPC_CORE_WAKE, disabling cpuidle.
failed to register cpuidle driver
```

Mainline 6.12 has no such firmware check and registered PSCI cpuidle. The
leading explanation is that CPUs entered that power-down state and the
firmware/GPC could not wake them, consistent with silence from every CPU.
Next discriminator: identical experiment plus `cpuidle.off=1` (experiment 08).
Per the guiding principle, that switch is the preferred fix if it works; a DTB
edit removing `cpu-idle-states` is a fallback, not a kernel change.

Recovery: the hung kernel had not loaded `imx2_wdt`, so the inherited hardware
watchdog reset the board (POR). Firmware booted OS A directly and the stock
kernel returned 201 s after the request: boot
`a01ac3ce-a97a-418c-b4ca-a795476f562a`, original command line, unchanged
`/boot/vmlinuz`, reset reason `0x1`, watchdog counter `0x16`. The executed hook
was archived and removed. PC evidence: `sources/firmware-audit/debian-20261021-07/`.

Target: Debian trixie's standard 4 KiB arm64 kernel with the existing Bookworm
root filesystem. Debian userspace and container configuration are retained.

## Prepared candidate

- Release: `6.12.113+deb13-arm64`; package version: `6.12.113-1`.
- Image: 37,728,192 bytes; SHA-256
  `391a3b39b265585ed094fba56994c4613a3c41fc65b9670e42da5a66d63ca07e`.
- Kernel package SHA-256:
  `fb1d4ff8bffc992b9b7e073f9a07d1ce378c041cfba78bb8e039c15a504b3129`.
- The repository signatures and Release/index/package hash chain were checked.
  Archive keys were downloaded over HTTPS and checked against published primary
  fingerprints; this is not an independently provisioned offline trust anchor.
- The package contains the required i.MX8MQ platform support, 4,347 matching
  modules and generic board DTBs. It does not contain a Percept DTB.

`tools/stage_debian_kernel.py` reproduces the isolated package staging. It runs
no package maintainer scripts or production kernel-install hooks. Full metadata,
configuration checks and artifacts are under
`sources/firmware-audit/debian-kernel/` (ignored local evidence).

The extracted package uses `usr/lib/modules`. On the board, an isolated staging
directory has `lib -> usr/lib`; native `depmod -b STAGE RELEASE` generates its
dependency indexes without modifying the running kernel's module tree.

## Diagnostic boot

The diagnostic initramfs includes exact matching module dependencies, with
compressed modules unpacked and loaded in a recorded order. Requested roots are
the i.MX OTP reader, reset controller, fixed/GPIO regulators, I2C, Intel igb and
i.MX eSDHC. PCIe host, GPC, clocks and pinctrl are built in.

The bootstrap reports its actual and expected kernel release, experiment token,
boot identity, CPU count, memory and module-loading results over UDP and HTTP.
It keeps production storage unmounted and requests normal reboot after 180
seconds. A kernel hang before PID1 remains recoverable through physical reset
or USB recovery, rather than this userspace timer.

The first native-boot DTB preserves the existing board wiring and memory
description. See [the device-tree record](percept-device-tree.md) for binding
checks and remaining limitations. The selected boot method determines whether
fresh UEFI handover properties must be retained; a DTB from a previous firmware
boot must not be reused for kexec without refreshing that state.

## Execution and acceptance

1. Keep the restore point on the PC before leaving the current working boot.
2. Probe the signed recovery bootloader's ordinary interfaces, recording exact
   responses. See [the USB test](boot-interface-test.md).
3. Download and boot the diagnostic candidate through an admitted interface;
   retain command list, addresses, hashes and all external observations.
4. Require actual `6.12.113+deb13-arm64` identity in the external report before
   declaring a successful Debian kernel boot.
5. Qualify the existing root filesystem, services and containers, then persistent
   startup. Retain the previous artifact set for rollback and update testing.

Three successful cold boots and an update/rollback rehearsal remain the final
acceptance criteria. Preparation and successful staging alone do not meet them.

## Current status

Package staging and native dependency generation completed. Diagnostic archive
validation and the application-quiesced restore-point capture are in progress.
No Debian kernel boot has yet been demonstrated.
