# CPU power handoff — 21 October 2026

## Immediate state: recovered and verified working

Normal Debian boot was verified after recovery: kernel
`6.12.113+deb13-arm64`, boot ID `4cc6e675-5705-49e9-8c46-09a0b9a2fa1f`.
Policy is min 800000 / max 1500000 kHz, schedutil; the policy service succeeded.
CPU temperature 34 C; no RCU-stall/hard-lockup/Oops/BUG lines in this boot.
`cpuidle.off=1`, `clk_ignore_unused` and `pd_ignore_unused` are retained.
Evidence: `recovered-working-state.txt`. There is no pending recovery action.

Recovery SSH was reached on the signed 5.4.3 kernel, rescue boot
`41dc6c9b-30e6-4f88-9790-ffdb7269e21c`. Failcount was 3 and GRUB tries were 0,
confirming the persistent fallback worked. The ESP was mounted at `/esp` and
only `cpuidle.off=1` was restored. The resulting config SHA256 matches the saved
working copy: `adaba0e030589505f3e476837fe71314d1a083f31fb1257492f31a2e0ca41e38`.
Counters were reset to failcount 0 / tries 4 and a reboot completed.
Normal Debian boot verification passed. See `idle-rollback.json` in the
evidence directory. No further idle, unused-clock or unused-domain tests.

Earlier UART observation: bootstrap attempt **2 of 3**, source boot
`a596f5cf-2fd1-40ad-ae0b-696479fba1c8`, then kexec. This was not yet rescue.
The launcher enters rescue once its saved failcount is already >=3; GRUB also
has its own countdown. User is physically rebooting and has serial/PuTTY open.
UART log: `<LOCAL_PATH>/UART/putty2.log`, <COM_PORT> 115200 8N1/no flow. Do not seize
the port from PuTTY or initiate more reboots without coordinating this recovery.

CPU-idle failure trace: secondary CPU startup warning (inconsistent modes),
initialization proceeds to ~1.528 seconds, then RCU stalls and timer-wakeup
failures on CPUs 1/3; watchdog reports hard lockup on CPU1 at ~43 seconds.
No modules were loaded and target initramfs/userspace had not started. The
1.5 GHz runtime policy therefore had not been selected. The only change from
the successful benchmark boot was removing `cpuidle.off=1`. Treat this as a
failed firmware/CPU-idle integration test, not evidence of an OC load failure.
Exact root cause is unproven. Vendor bootstrap also reports missing EL3 GPC
core-wake support; retain that as a lead, not a completed diagnosis.

## Known working configuration and rollback reference

PC working file:
`sources/firmware-audit/cpu-power-20261021/launcher-oc1500-production.conf`.
It has `cpu_pmic=1`, `cpu_profile=oc1500`, `/vmlinuz`, `/initrd.img`,
`cpuidle.off=1 clk_ignore_unused pd_ignore_unused`, and
`cpufreq.default_governor=powersave`. Kernel PMIC/CPUfreq blacklists are removed.

Device working backup (on the Debian root filesystem):
`/root/percept-cpu-build/launcher-oc1500-noidle-working.conf`.
Despite its name, "noidle" means CPU idle DISABLED: it contains `cpuidle.off=1`.
Other originals are in the same directory. Prefer the verified PC config if
root is mounted read-only in rescue. Restore only the ESP launcher config;
the launcher archive, root filesystem, initramfs and service are already good.
Reset the existing boot counters using the established procedure when restoring.

SSH at <BOARD_IP>, existing supplied credentials. Normal Debian host key:
`SHA256:mdeCrZVXqFVWhkCXWiPAbnJ3YSL4W3/mKdLS/ND7Wec`.
Stock-kernel rescue host key:
`SHA256:lH/dp0R/RVdAew6Ytg5eY72peGn6g7o9ja8/htShBJk`.
Use the correct host key; do not bypass host-key checking. PuTTY executables:
`C:/Program Files/PuTTY/plink.exe` and `pscp.exe`.

## Completed and demonstrated

* Stock Debian 6.12.113+deb13-arm64; no kernel-source changes.
* Real CPU supplier is PMIC BUCK2, proven from ASUS PE100A source. GPIO regulator
  inherited from an EVK was wrong. PMIC integration boot passed; 15 rails at
  expected voltages. Review: `docs/cpu-voltage-contract.md`.
* CPUfreq exposes 800/1300/1500 MHz with experimental opt-in for 1500, 0.9 V
  at 800 and 1.0 V at 1300/1500. Factory grade remains industrial 1.3 GHz.
* All three one-minute tests passed, peak 35/37/38 C respectively. Longer soak
  testing explicitly deferred by user. The long rated suite was interrupted
  at user request, not a computation failure.
* Automatic powersave initialization then 800–1500 MHz schedutil survived a
  reboot, boot `8a18bd6d-0f49-4e9a-8f50-45ba8397cfd9`.
* CPU cooling registered/bound; unchanged 80 C passive /90 C critical trips.
* `/etc/percept-cpu/max-khz`=1500000; `percept-cpu-policy.service` enabled.
  Writing 1300000 and restarting the service was verified as runtime rollback.

Post-reboot benchmarks (sysbench1.0.20):

| Metric | Trixie1.3GHz | Trixie1.5GHz | OldBookworm |
|---|---:|---:|---:|
| CPU4threads, prime10000,60s,events/sec |2490.54|2852.86|~2455|
| Memory4threads,1KiBwrite/seq/global,10s,MiB/sec |4458.96|5391.95|~4423|
| Memory1thread,sameparameters,MiB/sec |1176.89|1360.69|unknown|

CPU gain at 1.5 versus 1.3 GHz is 14.5%; the historical CPU gain is 16.2% and
historical memory gain 21.9%, but original memory parameters are unrecorded.
This is cache-sensitive, not raw DRAM bandwidth. Peak benchmark temperature
was 38 C. Raw archives and JSON reports are under
`sources/firmware-audit/cpu-power-20261021/`; report `docs/cpu-benchmarks.md`.

## Installed components and hashes

`experiments/percept-cpu/`: CPU/PMIC static helpers, two-helper launcher packager,
validators, initramfs hooks/guard, runtime policy. Reproducibility and rollback:
`docs/cpu-power-install.md`. Test runners: `experiments/percept-cpu-tests/`.

Installed launcher SHA256:
`b18c4c8dd969d9c46de00b39933448f2f6a91a6224d479e6dd782a82393afe07`.
CPU helper: `f593e7db0587322fcf3a7ef7b172a2fe2b3be7cec6af682b94c46cd170195fd9`.
PMIC helper: `553647f364829a474f0da9ed4936fa672505da4a80f71cc57ccddce77ff48143`.
Normal `/initrd.img` SHA256:
`9259f19f29b71c297d428653f9c38ca4f71c1232fd0b3679a28b20184b52d731`.
Original normal initramfs backed up on device as
`/root/percept-cpu-build/initrd-original.img`.

Powersave is modular. Early init-top loads it before CPUfreq. Important fixes:
same-module softdep bypasses kmod install guards, so softdep lines were removed;
initramfs exports MODPROBE_OPTIONS=-qb, so explicit loader/guard unset it.
Marker `/etc/percept-cpu/enable-cpufreq` is an internal activation gate already
installed after supplier verification; no new human approval is needed.

PMIC integration intentionally changes register0x24 00->30 (LDO5/LDO6 monitoring)
and REGLOCK 11->00, initializes IRQs, preserves all other rail voltages/hardware
enable ownership. Existing userspace/hardware fixes, GRUB and USB-C DTB retained.

## Scope and user preferences

GPU/VPU implementation was discontinued in this task; preserve other agents'
working fixes. SPL route remains cancelled. User wants practical recoverable
tests, no elaborate recovery framework or repeated approval questions. USB
factory recovery is available. Root1.5GHz profile is explicitly experimental,
no voltage tuning above1.0V. Do not resume the long soak automatically.
The PC production template `experiments/percept-launcher/launcher.conf.trixie`
has been synced to the proven working configuration with `cpuidle.off=1`.
The same config has now been restored on the board's ESP through rescue SSH.
Clock/domain switches only affect idle peripheral power and are unnecessary
for CPU scaling; recommend retaining their existing workarounds now.
No physical cold boots have been qualified. Do not claim complete power
management restoration: DVFS works, deeper CPU idle failed, clock/domain tests
were not performed.
