# CPU power management in installer builds

The stock Debian 6.12 kernel supports the PE100 CPU regulator and clock drivers.
This port adds boot-time DT adaptation and userspace ordering, without patching
the kernel, firmware or fuse values. It comes from the tested 2026-10-21 setup.

## Per-board selection

Set this in `boards/<name>/board.toml` before generating the installer:

```toml
[os]
profile = "debian-trixie"
cpu_profile = "oc1500"
```

`unchanged` (default) retains the existing PMIC/CPUfreq blacklist and changes
nothing. `rated` exposes the fuse-approved 800/1300 MHz points on the tested
industrial grade. `oc1500` adds experimental 1500 MHz by changing only its
OPP hardware mask from `<8 3>` to `<4 4>`. The excluded 1 GHz OPP stays excluded.
Other grades remain subject to hardware filtering; identify each board's grade
and verify its offered frequencies before accepting the profile. No fuses are
written. 1.5 GHz is above the tested board's factory rating, even after passing.

## Changes over stock Debian

* `launcher/fdt/adapt-pmic-fdt.c` translates the vendor PMIC binding to mainline
  ROHM BD718xx, preserves constraints/phandles and all fifteen rails' hardware
  enable ownership, and connects the four CPUs to actual BUCK2. The inherited
  EVK GPIO1_IO13 voltage regulator is disabled. Voltage selection is I2C, not GPIO.
* BUCK2 operates at 0.9 V for 800 MHz and 1.0 V for 1300/1500 MHz, with a
  5000 uV/us ramp (nominal 20 us for 100 mV). Other rail voltages are unchanged.
  Mainline probe unlocks REGLOCK, initializes IRQs and changes monitor register
  0x24 from 0x00 to 0x30 (LDO5/LDO6 monitoring disabled). This is intentional.
* `launcher/fdt/adapt-cpu-fdt.c` verifies the original four-OPP contract and
  applies only the selected mask edit. Both helpers consume the current boot's
  fresh DT, after existing RAM/thermal/media fixes, and fail into rescue if the
  source contract differs. Never ship a first-board live EFI handover DT.
* The generated command line removes only PMIC/CPUfreq entries from
  `module_blacklist`, keeps unrelated entries, and adds exactly one
  `cpufreq.default_governor=powersave`. Existing GPU/VPU/USB/radio/storage choices
  and board identity remain unchanged.
* `target/cpu/` stages six runtime files, activation marker, max-frequency cap
  and a systemd enablement link. An initramfs hook includes the drivers and guard;
  its early loader loads modular powersave before either CPUfreq driver.
  Alias blacklists remain; explicit guarded loading clears inherited
  `MODPROBE_OPTIONS=-qb`. Do not add same-module softdeps: kmod overrides the
  install guard in that combination.
* The service waits for the shared four-core policy and CPU thermal cooling
  binding, then selects `schedutil` and the chosen 1.3/1.5 GHz cap. Keep the
  existing 80 C passive /90 C critical thermal trips.
* Retain **`cpuidle.off=1 clk_ignore_unused pd_ignore_unused`**. Removing the
  idle workaround caused an early RCU/timer/hard-lockup failure before target
  userspace; its exact firmware/entry-state cause is not established. Reinstating
  it restored boot. Clock/domain workarounds were not changed in this port.

## WSL/Linux build integration

The launcher's existing arm64 Bookworm chroot already supplies gcc, libfdt-dev
and static libfdt. `bash launcher/build.sh` now compiles and embeds both new
helpers alongside the existing ones, with no checked-in binaries or lab paths.
It uses the same chroot/WSL build mechanism as the media helper.

The rootfs installer orchestrator is still a repository milestone. Its contract
for this port is ready: `profiles.resolve()` returns `cpu_profile` and
`rootfs_env.PERCEPT_CPU_PROFILE`, and the Debian profile declares the hook
`20-cpu-power.sh`. Pass that environment to profile hooks INSIDE the target
arm64 chroot, make the repository available at `/src`, and install the kernel,
modules, Python 3, kmod and initramfs-tools before running the hook. It stages
the runtime files and regenerates every installed initramfs. The hook must run
before packaging the rootfs. Do not execute target tooling under the old 5.4
kernel; use the WSL arm64 chroot/qemu build environment.

For preparing an offline rootfs manually (staging only; no initramfs generation):

```bash
python3 target/cpu/stage.py --root /path/to/trixie-root --profile oc1500
```

Then inside that rootfs's arm64 chroot:

```bash
PERCEPT_CPU_PROFILE=oc1500 sh /src/profiles/debian-trixie/hooks/20-cpu-power.sh
```

Build on WSL's Linux filesystem (`~/azure-percept-dk-debian`), not `/mnt/e`,
to preserve ownership, executable bits and symlinks in installers. Installing
this port in the Windows checkout does not synchronize a separate WSL clone;
merge/transfer these repository changes there before building.

## Validation and board qualification

```bash
python3 -m unittest discover -s tests/unit -v
python3 dev/scrub-scan.py
python3 target/cpu/test-guard.py
python3 target/cpu/test-policy.py
# Use your own freshly captured bootstrap DT; helpers must be built for the host:
python3 launcher/fdt/cpu/test-helper.py /path/to/percept-fdt-cpu fresh.dtb
python3 launcher/fdt/cpu/test-pmic.py /path/to/percept-fdt-pmic fresh.dtb
```

For hardware acceptance, require the real BUCK2 supplier, exactly one four-core
CPU policy, the expected offered frequencies, changing actual clock, correct
voltage and registered CPU cooling. `board-tests/cpu/test-suite.sh --help`
documents the one-minute-per-frequency suite and its required boot ID, peer
and temporary storage path. The test stops on faults or 80 C and leaves a
1.3 GHz cap. Longer soak testing remains optional/deferred.

On the first board all three minute tests passed (peaks 35/37/38 C). Paired
sysbench 1.0.20 at 1300/1500 MHz measured 2490.54/2852.86 CPU events/sec
(4 threads, max-prime 10000, 60 s). Four-thread cached 1 KiB sequential-write
memory measured 4458.96/5391.95 MiB/sec (10 s); this is cache-sensitive and
not raw DRAM bandwidth. Scaling and the policy survived reboot. Three cold
boots and longer soak tests must not be inferred from those results.

## Rollback

```bash
printf '1300000\n' > /etc/percept-cpu/max-khz
systemctl restart percept-cpu-policy.service
```

For persistent rated boot, select `os.cpu_profile = "rated"`, regenerate the
launcher config and stage the rated runtime policy. Keep the PMIC adaptation.
For a complete return to the older installation restore its launcher config
and target initramfs/runtime files as a set; changing only to `unchanged` on
an already modified root is not an uninstall. The default unchanged hook is a
no-op intended for fresh rootfs builds. Retain the existing factory recovery
procedure and the clone's own prior working artifact set.
