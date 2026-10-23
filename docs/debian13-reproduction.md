# Debian 13 on a second Azure Percept DK

This is the current change ledger and reproduction checklist, rather than
the chronological experiment log. The first device runs a clean trixie
filesystem with Debian's **unmodified** `6.12.113+deb13-arm64` Image and
matching Debian modules. Its signed factory kernel remains a bootstrap.
The boot route and upper-memory change have passed warm reboots. Radios and
CPU thermal sensing passed the combined reboot; USB-C now binds and enumerates
the camera's controller and MyriadX. Video/inference remains a separate task.
The full procedure has not yet
been run on the second device.

## Changes over a generic stock Debian 13 installation

| Area | Percept-specific change | Source / record |
|---|---|---|
| Boot chain | Keep Microsoft's signed 5.4.3-26.cm1 Image; GRUB loads it with a small ESP launcher initramfs, which captures a fresh bundle and kexecs Debian | `experiments/percept-launcher/`, `docs/trixie-install.md` |
| Bootstrap modules | Patched `arch.ko` / `core.ko` built for that vendor kernel; post-init trigger, CAAM job-ring reset and OCOTP clock handling | `docs/kexec-mod-experiment.md`, `docs/kexec-caam-fix.md` |
| Bootstrap tools | Bookworm-compatible dynamic tools and static BusyBox/helpers; Trixie thread creation fails on the old vendor kernel | `build-launcher.sh`, `tools/build_percept_initramfs.py` |
| Boot recovery | ESP failure counter, GRUB countdown, stock-kernel Dropbear/serial rescue; factory USB restore remains the restoration method | launcher `init`, `grub.cfg.production`, `docs/percept-restore.md` |
| Debian kernel | Standard Debian package 6.12.113-1, held during bring-up; no kernel or driver source patches | `experiments/percept-trixie/stage-b.sh` |
| Debian initramfs | Standard initramfs-tools generation with `imx2_wdt`, `sdhci-esdhc-imx`, `ext4` in `/etc/initramfs-tools/modules` | `stage-b.sh` |
| Kernel command line | Percept serial console plus tested clock, power, idle, EFI and module workarounds below | `launcher.conf.trixie` |
| RAM | `upper_ram=1`: extend the fresh target DT memory bank from 3 to 4 GiB; original bootstrap/rescue DT unchanged | `experiments/percept-upper-ram/`, `docs/percept-upper-ram.md` |
| Thermal | `thermal_fix=1`: fresh target DT's TMU sensor cell count 0→1; use stock `qoriq_thermal` | `experiments/percept-hardware/`, `docs/percept-hardware-support.md` |
| CPU supply and DVFS | `cpu_pmic=1` corrects the CPU supply to PMIC BUCK2 and adapts its bindings; guarded early powersave loading precedes CPUfreq, then a systemd service selects schedutil | `experiments/percept-cpu/`, `docs/cpu-voltage-contract.md` |
| Experimental CPU clock | `cpu_profile=oc1500` explicitly admits 1.5 GHz at 1.0 V; rated alternative is 800/1300 MHz. Each rate passed a one-minute test; long soak deferred | `docs/cpu-power-status.md`, `docs/cpu-test-procedure.md` |
| USB-C | Separate DTB with one unusable extcon reference removed; normal GRUB entry selects it, rescue retains the original DTB | `tools/strip_dtb_property.py`, `docs/usb-c.md` |
| Radios | Debian `firmware-realtek`, `wireless-regdb`, `iw`, `bluez`; stock `rtw88_8822ce` / `btusb` / `btrtl` drivers | `install-radio-firmware.sh`, hardware support record |
| Filesystems | ext4 root and FAT ESP mounted by each device's UUID; retain signed kernel as `/boot/vmlinuz-5.4.3-mariner` | `stage-b.sh`, `rescue-install.sh` |
| Network | systemd-networkd DHCP on `eth* en*`; resolved and timesyncd; no Wi-Fi credentials installed | `stage-b.sh` |
| Access | OpenSSH, supplied authorized public keys, local users/passwords, serial getty on `ttymxc0` | local `config.sh`, `stage-b.sh` |
| Watchdog | `RuntimeWatchdogSec=60`; early watchdog module in Debian initramfs | `stage-b.sh` |
| Successful boot marker | `percept-boot-ok.service` resets launcher/GRUB attempt counters after network-online and a 60-second delay | `percept-boot-ok`, `.service` |
| Other policy | 50 MB journal limit, UTC timezone, en_US.UTF-8 locale | `stage-b.sh` |

GCC, musl-tools, memtester, device-tree-compiler and libfdt-dev installed during
investigation are build/diagnostic tools. The final thermal helper requires
neither libfdt nor a compiler at runtime. Docker/DEQ or accessory applications
are not part of this clean Debian base. There are no SPL, fuse, TPM or
security-provisioning changes in this route.

The currently tested Debian command line is:

```text
root=UUID=YOUR_ROOT_UUID ro console=ttymxc0,115200 earlycon=ec_imx6q,0x30860000 cpuidle.off=1 clk_ignore_unused pd_ignore_unused efi=noruntime net.ifnames=0 cma=256M cpufreq.default_governor=powersave
```

CPU PMIC/frequency blacklists are now removed after supplier integration and
testing. Keep the separate idle/clock/domain workarounds until their own tests.
The PMIC probe intentionally unlocks its regulator registers, initializes IRQs
and changes register 0x24 from 0x00 to 0x30 (LDO5/LDO6 monitoring); it preserves
other rail voltage selectors and hardware enable ownership. Read the detailed
[CPU installation and rollback procedure](cpu-power-install.md) before copying
this change to another board. Each board needs its own grade identification
and short frequency tests; 1.5 GHz is above the identified industrial rating.

## Values that must belong to the second device

Record these while the second board still boots its existing installation:

```sh
uname -r
sha256sum /boot/vmlinuz
lsblk -o NAME,SIZE,FSTYPE,UUID,PARTUUID,MOUNTPOINTS
ip -br link
cat /proc/cmdline
```

Choose its own hostname, rescue IP/netmask, PC logging IP, SSH authorization
keys, passwords and new root UUID. Keep its ESP UUID unless deliberately
reformatting the ESP. Preserve its original DTB and factory firmware files.
Do not copy this board's Ethernet/Wi-Fi/BT addresses, SSH host private keys,
machine-id or firmware handover addresses to another board.

Historic scripts contain first-board constants. Before using a copied working
set, replace **all** of the following, keeping originals in the record:

| File | Fields to personalize |
|---|---|
| `percept-trixie/config.sh` | Create from `config.sh.example`; set hostname, users, passwords; this file is ignored by Git |
| `build-trixie-rootfs.sh` | Supply new root UUID and authorized_keys as its two arguments; verify its expected stock/debian package hashes |
| `stage-b.sh` | `esp_uuid`; it reads the root UUID supplied by stage A |
| `rescue-install.sh` | `UUID` must equal stage A's chosen new root UUID; verify `P3` and `ESP_DEV` for the vendor bootstrap |
| `builder-init` (only if using the historical builder boot) | `BOOKWORM_UUID`, its no-hyphen `BOOKWORM_UUID_HEX`, `TARGET_MAC`, `SOURCE_IP`, `SOURCE_PREFIX`, `RECEIVER_IP` |
| Launcher `init` | `TARGET_MAC`, `SOURCE_IP`, `SOURCE_PREFIX`, `RECEIVER_IP`, and actual bootstrap `ESP_DEVICE`/`ROOT_DEVICE` |
| `launcher.conf` | Root UUID in `cmdline`; paths to Debian's own `/vmlinuz` and `/initrd.img` symlinks; desired `upper_ram` / `thermal_fix` switches |
| `grub.cfg.production` | Verify partition numbering and paths, retain the USB-C DTB selection in the normal entry and original DTB in rescue |

Device names can differ between the vendor and Debian kernels. Use UUIDs in
Debian configuration. Do not infer the bootstrap's partition names from a
different kernel's enumeration. The first board currently uses eMMC p3 as
root and p1 as ESP; all p3-formatting commands are destructive to that root.

## Reproduce the installed system

1. Preserve the second device's data and its own boot/ESP artifacts. Keep the
   existing Microsoft factory-image restore procedure available. No new
   recovery tooling or restoration rehearsal is needed.
2. Check the signed stock kernel against the expected release and Image hash
   below. Reuse the retained bootstrap modules only for the matching vendor
   build and symbol versions. For a different build, follow the module build
   record and reconstruct its metadata rather than forcing mismatched modules.
3. Build a fresh trixie root tree with the scripts in
   `experiments/percept-trixie/`, after personalizing the table above. Create
   local `config.sh` from the example before stage A. Stage A downloads and
   unpacks packages; stage B must execute under Debian 6.12, either on a native
   arm64 Linux build host or using the documented RAM-only builder boot.
   Running stage B under the old vendor kernel reproduces the glibc crash.
4. The historical stage-A setup expects the verified kernel `.deb` and
   debootstrap 1.0.141 at the paths stated in `build-trixie-rootfs.sh`. Their
   download/signature verification and builder boot are recorded in
   `docs/trixie-install.md` and `docs/debian-kernel-test.md`. Use the exact
   retained artifacts for the tested baseline; archive new inputs if changing
   package versions. Debian mirror contents are not frozen by these scripts.
5. Run `pack-trixie-rootfs.sh` after stage B and retain its hash/build record.
   A fresh build generates its own SSH host keys and starts with empty
   machine-id. If adapting the retained first-board rootfs tarball instead,
   mount/extract it separately, change fstab/hostname/credentials/authorized_keys,
   remove its old SSH host keys, run `ssh-keygen -A` **inside that target
   root under 6.12**, empty `/etc/machine-id`, and remove
   `/var/lib/dbus/machine-id`. Repack and hash it. Do not deploy a direct clone
   carrying the first board's host keys or credentials.
6. Build/personalize the ESP launcher with Bookworm-compatible tools using
   `build-launcher.sh`. Its input binaries and retained hashes are listed in
   that script; its `<LOCAL_PATH>/` paths are build-host paths,
   not files supplied by a generic Debian installation. The working archive
   can also be unpacked and updated with `tools/replace_initramfs_member.py`,
   replacing `init` and `etc/percept-launcher/authorized_keys` for the new
   board. Generate its own Dropbear host key for the ESP. Keep a manifest of
   every changed archive member. Do not reuse the first board's rescue key.
7. Compile the static upper-RAM helper if rebuilding the launcher. Apply the
   thermal integration using `prepare-thermal.sh` / `prepare-launcher.py`.
   The latter requires the actual input archive SHA256 and consumes that
   archive's own init. If an existing integration already has the helper,
   merge explicitly instead of adding it again. Thermal can be left disabled
   until its live result is accepted. Keep both transformations sequential.
8. Generate the USB-C DTB from the **second device's original** `pe100.dtb`
   using the documented property-removal tool. Preserve the original DTB for
   rescue. Use the current production GRUB configuration, which includes the
   USB-C normal-entry change; a stale copy silently drops that fix.
9. Install the launcher/keys on the ESP and verify rescue access on the new
   device. Use the personalized `rescue-install.sh` from stock-kernel rescue
   to install the prepared rootfs on p3, then `arm` with the personalized
   configuration and current production GRUB file. The existing script's
   comments list its required `/run/` inputs and streaming installation.
10. Boot trixie; run `update-initramfs -u -k 6.12.113+deb13-arm64` now that its
    root filesystem exists. Install standard radio packages using
    `install-radio-firmware.sh`. Keep Debian's versioned kernel/initrd files
    and `/vmlinuz`/`/initrd.img` symlinks together. Record resulting hashes.

Fresh DT capture is mandatory to correctness: actual launcher boots always
start from that stock boot's `/sys/firmware/fdt`. An archived DT or bundle is
an offline test input, not a transferable firmware handover for another boot.
The RAM helper currently refuses a complete EFI handover because that would
require a separate EFI memory-map design; do not suppress this check.

## Tested artifacts and provenance

SHA256:

```text
fec6f292e734ab81c056a28ab0c3940ec7f00fcd39cec417cac9da52bb3f7ef2  signed stock Image
fb1d4ff8bffc992b9b7e073f9a07d1ce378c041cfba78bb8e039c15a504b3129  Debian linux-image .deb
391a3b39b265585ed094fba56994c4613a3c41fc65b9670e42da5a66d63ca07e  unmodified Debian Image
c90f408f7e06c01ca280193f221a6f6fe02548cef62a0fc2eb84c8809d22f6c0  arch.ko
03cd9ebb8a79ac53d093e46bb0994e251a8487ca618e4ada2efe8d066dcac4e9  core.ko
46e4bd0dd84336f9d7c290e3a73a1da1a74f8647f6c04c073e2f0512b2dfba27  first-board RAM launcher baseline
8b77383ae74cebce6b1967e3d1344a98eff819916b7b457a421ed32340134918  first-board thermal launcher
cc20b2f48e822e3e893f84f8a748383708439f4596d6abca49ad5e8a08c27900  original first-board trixie rootfs tarball
```

Personalizing keys/networking changes the launcher hash; personalizing a rootfs
changes its tarball hash. Rebuilding an initrd can also change its hash without
modifying the kernel. These hashes identify retained evidence, not universal
second-board output expectations.

Retained PC input directories:

- `sources/firmware-audit/debian-kernel/packages/`: kernel package.
- `sources/firmware-audit/trixie-builder-20261021-09/`: initial rootfs tarball
  and stage-B record; no subsequent RAM/radio/thermal configuration assumed.
- `sources/firmware-audit/upper-ram-20261021-01/`: working RAM launcher,
  prior launcher, static helper and persistence evidence.
- `sources/firmware-audit/hardware-support-20261021/`: firmware packages,
  package inventory before/after, thermal source/build/results and candidate.
- `sources/firmware-audit/usbc-20261021/`: independent USB-C DTB/GRUB record.

Large artifacts and local firmware/module source trees are ignored by Git.
Copy these retained directories with the repository when preparing another
machine; a Git clone alone does not supply them. Build scripts, manifests and
documentation identify their dependencies. Existing factory restore remains
documented in `docs/percept-restore.md`.

## Acceptance and updates

Planned GPU/VPU enablement is tracked in `docs/gpu-vpu-plan.md`. Its proposed
changes are not part of the installed baseline until the individual rendering
and decoding tests pass.

For each new device, record boot ID, actual release, command line, RAM map,
root mount, DHCP/SSH and watchdog. Check Wi-Fi scanning, Bluetooth controller
initialization, CPU temperature and the independent USB-C test. USB-A/eMMC/SD
passed on the first board; accessories and other unbound devices are covered
by `docs/trixie-device-audit.md`, not assumed from a populated vendor DT.

Require three real power-disconnected cold boots and a tested kernel update
with rollback before calling unattended deployment qualified. Those gates
have not yet been completed. The current kernel is held; a future update
needs its matching modules and regenerated initrd, plus review of the DT/EFI
assumptions. Keep the preceding kernel/initrd and launcher/config pair.
Normal startup follows Debian's symlinks; rollback can point launcher
`kernel`/`initrd` at the preceding versioned files. Restore both old launcher
and its matching config when undoing a launcher format change.
