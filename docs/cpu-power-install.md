# Reproduce Percept CPU power control and the 1.5 GHz profile

Tested with Debian's unmodified 6.12.113+deb13-arm64 kernel and modules. All
changes are launcher/target-DT adaptation, initramfs configuration and policy.
Keep the existing signed bootstrap, original rescue DTB and USB restore path.

## Artifacts and supplier

Use the current launcher, not an older RAM/media-only archive. Build both static
helpers with `experiments/percept-cpu/build.sh` on arm64 with musl-tools. The
script uses the retained dtc 1.7.2 source archive. Package using
`package-launcher.py` with its required current-launcher SHA256 and
`--pmic-helper`; it checks static arm64 binaries and preserves unrelated archive
members. Validate copied DTs with `validate-pmic.py` and `validate-dtb.py`.

The live bootstrap DT must match the guarded factory structure. The helpers
fail on an unexpected supply, IRQ, rail constraint, OPP or phandle; investigate
a different board/image rather than removing guards. Each boot captures a fresh
firmware DT. Never install an archived captured DT with old EFI addresses.

Add `cpu_pmic=1` to the launcher. First boot with `cpu_profile=unchanged` and
keep `module_blacklist=imx_cpufreq_dt`, removing the old PMIC blacklist entries.
Verify all fifteen rails, CPU BUCK2 RUN=1.0 V, existing rail voltages and IRQ.
The GPIO1_IO13 regulator inherited from the EVK tree is disabled. ASUS's actual
CPU supplier is PMIC BUCK2. Mainline probe preserves hardware enable control
but intentionally changes monitor register 0x24 to 0x30 and unlocks REGLOCK.
See `cpu-voltage-contract.md` for source evidence, readbacks and probe audit.

## Install the boot and runtime components

After confirming the supplier, install these files from `experiments/percept-cpu/`:

| Source | Installed path / mode |
|---|---|
| `cpufreq-load-guard` | `/usr/lib/percept/cpufreq-load-guard`, 0755 |
| `percept-cpu.conf` | `/etc/modprobe.d/percept-cpu.conf`, 0644 |
| `initramfs-hook` | `/etc/initramfs-tools/hooks/percept-cpu`, 0755 |
| `init-top-cpu` | `/etc/initramfs-tools/scripts/init-top/00-percept-cpu`, 0755 |
| `cpu-policy.sh` | `/usr/lib/percept/cpu-policy.sh`, 0755 |
| `percept-cpu-policy.service` | `/etc/systemd/system/percept-cpu-policy.service`, 0644 |

Normalize shell files to LF. Create `/etc/percept-cpu/enable-cpufreq` containing
`voltage-contract-approved-v1` after the supplier check. This is an internal
activation marker, not a separate user-approval requirement. The guard also
requires the powersave module and exactly one
`cpufreq.default_governor=powersave` command-line argument. Do not reintroduce
same-module softdep directives: real kmod gives those precedence over install
guards. Both loader and guard clear initramfs-tools' inherited `-qb` options
for their explicit guarded loads; alias blacklists remain.

Preserve the original initramfs, run `update-initramfs -u -k 6.12.113+deb13-arm64`,
and verify the generated archive contains the hook's modules, guard, config,
marker and `scripts/init-top/00-percept-cpu` before udev in `ORDER`.
Use `/vmlinuz` and `/initrd.img` in the launcher for normal Debian updates.
Remove the CPUfreq kernel blacklist and add the powersave parameter.

Use `cpu_profile=rated` for factory-filtered 800/1300 MHz. For this board's
speed/market masks `<4 4>`, `cpu_profile=oc1500` changes only the existing
1500 MHz OPP mask from `<8 3>` to `<4 4>` and retains its 1.0 V target.
The 1 GHz OPP remains filtered. Do not copy a grade assumption to another unit.

## Test and persist

Boot initially into powersave; require one four-core policy, expected available
frequencies and a `cpufreq-cpu0` cooling device bound to the CPU thermal zone.
Run the one-minute suite from `experiments/percept-cpu-tests/`, supplying that
boot's ID, a new output directory, reachable peer and disposable storage parent:

```sh
./test-suite.sh --suite minute --allow-overclock --boot-id BOOT_ID \
  --output-root NEW_LOG_DIRECTORY --network PC_IP --temp-parent STORAGE_DIRECTORY
```

The user selected one minute per rate, with longer soak testing deferred.
Successful first-device tests peaked at 35/37/38 C for 800/1300/1500 MHz.
Keep the 80 C passive and 90 C critical thermal settings. The runner stops and
caps at 1300 MHz on failure or 80 C; all normal exits also leave that cap.

Set `/etc/percept-cpu/max-khz` to `1300000`, or to `1500000` after the short OC
tests pass, then `systemctl daemon-reload` and
`systemctl enable --now percept-cpu-policy`. The service waits for CPU cooling
and selects min=800000, the configured maximum and schedutil. Verify a reboot;
record physical cold boots separately. No physical cold-boot qualification or
long-term stability claim is implied by a warm reboot and short tests.

## Rollback

For an immediate rated cap, write `1300000` to `/etc/percept-cpu/max-khz` and
restart `percept-cpu-policy`. For factory-filtered future boots, also change
`cpu_profile=oc1500` to `cpu_profile=rated` in the ESP launcher configuration.
The 1300 limit must be selected before the rated reboot.

To revert the supplier conversion entirely, restore the matching original
launcher/configuration backup, including its PMIC/CPUfreq blacklists and
original initramfs; disable the policy service. The first device's originals
are under `/root/percept-cpu-build/` and
`sources/firmware-audit/cpu-power-20261021/` on the PC. The ESP is too small to
hold two full launchers simultaneously; preserve the backup on root/PC and
verify the installed archive after copying. GRUB and its USB-C DTB selection
are unchanged by the CPU implementation.
