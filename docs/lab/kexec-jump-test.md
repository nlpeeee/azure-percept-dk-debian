# Controlled same-kernel jump

Date: 2026-10-20. Attempt launched at **16:19:23 UTC (17:19:23 London)**.

## Plan and preparation

The target is the existing Microsoft kernel and live device tree. kexec-tools
prepared a new bundle with command-line marker:

```text
percept_kexec_test=percept-20261020-01
```

Source boot ID: `39ed1db8-6227-4e80-a9fd-561e400afdae`.

The temporary final shutdown hook was
`/usr/lib/systemd/system-shutdown/90-percept-kexec-test`. It checks that source
boot ID, verifies asset hashes, and requires the root filesystem to be read-only.
It then loads the ARM64 module and core with `execute=1`. Any later boot has a
different boot ID, which disarms this hook and prevents a reboot loop.

Services and filesystems are shut down through ordinary `systemctl reboot`.
Systemd runs final shutdown hooks after stopping processes and attempting to
unmount/remount filesystems. The board's normal signed boot path remains available
after a reset.

## Checks completed before the attempt

- Disassembled the actual vendor Image: `machine_shutdown` calls
  `freeze_secondary_cpus(0)`; the EL2 stub supports HVC selector 1 for soft restart.
- Replaced the module's constant-false stuck-CPU check with the actual kernel
  function, rebuilt, and successfully staged the marked payload with it.
- Checked the purgatory entry: it loads the new kernel entry into x17 and the DTB
  address into x0, clears x1–x3, and branches to the kernel.
- Verified kernel entry `0x52480000`, DTB `0x54873000`, and trampoline entry
  `0x5487e6a0`. The DTB contains the exact marker above.
- Confirmed Cortex-A53 CPU features contain no pointer-authentication support.
- Captured the boot ID, command line, running services and eight Docker container
  names. The final hook passed its check-only mode without inserting modules.

Asset SHA-256 values:

```text
3f9b7351c3d8054a20f6f0d349ba50b945c13c55434a4b433bd853199e3fc059  arch.ko
a7365d5fdb20228d0e7fa4b30626f0c3e2a99c476508003ebee5feb701e8f700  core.ko
25ab4d8d063dc8b8f75b8b5b2e794c8b353c174d98c9f3d0887e244c13a294db  marked.bundle
```

Independent preflight evidence is retained locally in
`sources/firmware-audit/jump-preflight/jump-20261020/` and on the device in
`<work-dir>/jump-20261020/`.

## Result

**The marked kexec boot was not confirmed.** SSH closed after the reboot command.
The next recorded boot began at 16:23:47 UTC, with boot ID
`5f3204c1-5edd-45f3-a256-08c3797b7dec`. Its command line has the original
`BOOT_IMAGE=/boot/vmlinuz` arguments and no `percept_kexec_test` marker. The board
therefore returned through the normal boot path; this does not demonstrate a
successful kexec jump.

The previous journal records orderly service shutdown, unmounting `/boot/efi`,
deactivating swap, and reaching the reboot target. Its last entries at
16:19:42 UTC show systemd-shutdown syncing filesystems and stopping journald.
There is no retained output from the final hook or module execution. Both pstore
locations are empty. The logs mention the hardware watchdog during shutdown,
but do not establish that a watchdog reset caused the recovery. A skipped hook,
an insertion failure, or a later execution failure cannot be distinguished from
these records.

After recovery, the temporary hook was removed. Neither experimental module is
loaded. SSH, Docker and `deq` are active, and all eight original containers are
running, including the healthy mail container. The failed
`systemd-networkd-wait-online` unit was already present before this test.
The user initially suspected a boot loop, then reported that startup was simply
slow; no deliberate power cycle is established by that report.

Post-attempt evidence is retained in
`sources/firmware-audit/jump-post-attempt/jump-20261020/`. Its source archive
`jump-20261020-post-attempt.tar.gz` has SHA-256
`d31eb5c0d6bc973aa88c34845cd28df5ae603d6cc2ddf3b2f1f73992aca7e980`.

Another execution attempt needs evidence that survives the final shutdown phase,
such as a serial console or a validated persistent trace. Repeating the same
unobserved jump cannot identify the failing stage. The successful module-loading
and `execute=0` staging checks remain separate, valid results.

## Acknowledged execution attempts later that day

The staging rehearsal was extended into a one-shot execution hook. For each
attempt, a new bundle used that boot's live device tree and a unique
`percept_kexec_test` command-line marker. The PC acknowledged each UDP record
after syncing it to disk. All three attempts returned through the stock signed
boot path without the marker.

| Experiment | Variation | Last acknowledged boundary |
|---|---|---|
| `percept-jump-20261020-02` | Original EL2 detection | `core_init_begin execute_1`; insertion did not return |
| `percept-jump-20261020-03` | `detect_el2=0` | `core_init_begin execute_1`; insertion did not return |
| `percept-jump-20261020-04` | Matched rebuilt modules; insertion completes, then a sysfs trigger starts a worker | `execution_status value_2`, immediately before the worker calls `kernel_kexec()` |

The third attempt used prepared `arch.ko` SHA-256
`c90f408f7e06c01ca280193f221a6f6fe02548cef62a0fc2eb84c8809d22f6c0`
and `core.ko` SHA-256
`7ad30b94d772dae9b50f1023c68a65b506de8cd9d49b9298e7c65a404286b030`.
Their imported symbol CRCs were checked against the recovered kernel table and
the helper's current exports. `execute=0` staging loaded and unloaded this exact
pair, and the new parameters reported status 0 and trigger `N` before the test.
The one-shot hook's asset, boot-ID, root and network gates passed. The external
record is `sources/firmware-audit/jump-execution-20261020-04.jsonl`; the earlier
records have the corresponding `-02` and `-03` names. The new boot ID was
`9207b95e-6bdf-412f-b424-18ce32173df1`, with stock `BOOT_IMAGE=/boot/vmlinuz`
arguments. The hook was removed after recovery.

The stock kernel has no active lockdown LSM, enforces no module signature, and
has `modules_disabled=0`. IMA appraisal, SELinux and AppArmor do not gate these
loads. `CONFIG_KEXEC` is disabled, so the stock
`/proc/sys/kernel/kexec_load_disabled` sysctl does not exist; the experimental
module has its own zero-initialized variable. The i.MX watchdog remains active
during shutdown. Its driver clamps the requested timeout to 128 seconds and
pings it from the shutdown callback. The delayed stock boot and reset counter
increase fit watchdog recovery, but do not identify whether execution stalled in
kernel shutdown, relocation, or early target startup.

This moves the failure boundary past module loading and the post-init trigger.
It does **not** prove entry into the target kernel. No further identical jump
should be run. The next diagnostic needs an observable milestone after network
shutdown, or an independent proof of the relocation and target-entry path.
# Current result: UART proves Linux startup

The UART-only experiment on 21 October 2026 booted the unmodified stock Image
with its unique kexec command-line marker. It passed MMU/C setup and brought up
four CPUs. Experiment 03 stalled in `imx8_soc_init`. Experiment 04 explicitly
skipped that initcall, detected eMMC and its partitions, then panicked in
`caam_jr_interrupt` with job-ring status `0x103`. These results supersede the
earlier unknown handoff boundaries recorded above. The board recovered
automatically to stock after both tests and the completed hooks were removed.
See [the UART results](kexec-uart-test.md) for evidence and the next failure
boundary to isolate.

