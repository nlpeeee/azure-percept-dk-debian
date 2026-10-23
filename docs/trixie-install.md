# Clean Debian trixie install (replacing Bookworm)

For the current changes over stock Debian and second-device procedure, see
[Debian 13 reproduction](debian13-reproduction.md). This document retains the
historical build/test sequence; its earlier missing-firmware/thermal notes
are superseded by [hardware support](percept-hardware-support.md).

User direction, 21 October 2026: replace Bookworm entirely with a clean Debian
trixie. Keep the Debian kernel stock and use switches rather than patches.

## Boot chain

```text
UEFI → shim → GRUB (ESP grub.cfg) → stock 5.4.3-26.cm1 + launcher initramfs (ESP)
     → kexec_mod → Debian 6.12.113+deb13-arm64 + Debian initramfs (p3) → trixie
```

The launcher replaces the Bookworm shutdown hook. It runs in RAM from
`/boot/efi/percept/launcher.cpio.gz`, keeps a failure counter in
`/boot/efi/percept/failcount`, and falls back to a rescue SSH environment on the
stock kernel after three failed boots. On trixie, `percept-boot-ok.service`
resets that counter about 60 s after SSH and the network are up.

## Trixie rootfs

Built natively on the board by `experiments/percept-trixie/build-trixie-rootfs.sh`:

- **Base:** debootstrap of trixie arm64 with systemd.
- **Kernel:** the exact tested kernel `.deb`, `linux-image-6.12.113+deb13-arm64`
  `6.12.113-1` (SHA-256 `fb1d4ff8…`), held at that version.
- **Initramfs:** Debian's own initramfs-tools image, which also loads `imx2_wdt`,
  `sdhci-esdhc-imx` and `ext4`.
- **Root:** UUID `<BOARD_UUID>`. fstab is by UUID, with
  `nofail` on the ESP.
- **Network and SSH:** systemd-networkd DHCP on `eth* en*`, systemd-resolved,
  timesyncd, and OpenSSH. Credentials follow `config.sh`, plus the PC keys in
  `authorized_keys`.
- **Watchdog:** `RuntimeWatchdogSec=60`.
- **Stock kernel file:** the stock kernel kept as `/boot/vmlinuz-5.4.3-mariner`
  (and hard-linked as `/boot/vmlinuz`) so GRUB can still load it.

The 6.12 command line, passed by the launcher, uses switches only:

```text
root=UUID=<BOARD_UUID> ro console=ttymxc0,115200
cpuidle.off=1 clk_ignore_unused pd_ignore_unused efi=noruntime net.ifnames=0
module_blacklist=rohm_bd718x7,bd718x7_regulator,imx_cpufreq_dt
```

## Finding: trixie userspace cannot create threads on the stock 5.4 kernel

The first native builds under Bookworm (with Bookworm's debootstrap 1.0.128, then
trixie's 1.0.141, verified via InRelease → Packages.xz → `.deb`) both failed at
`dpkg --install base-passwd`:

```text
dpkg-deb: error: <decompress> subprocess was killed by signal (Segmentation fault)
dpkg-deb[24791]: unhandled exception: DABT (lower EL), ESR 0x92000004,
  level 0 translation fault in libc.so.6[f8d978b60000+19c000]
```

The fault is not specific to xz. Inside the trixie chroot,
`seq 1 3000000 | sort --parallel=4` also segfaults (exit 139), with or without
`GLIBC_TUNABLES=glibc.pthread.rseq=0`. Single-threaded trixie programs
(`tar --version`, `dpkg-deb --version`) run. Trixie's glibc thread creation
therefore fails on the vendor `5.4.3-26.cm1` kernel. Consequences:

- The launcher on the stock kernel must contain only Bookworm-built binaries.
- Any build step that runs trixie binaries (debootstrap second stage, dpkg,
  update-initramfs, locale-gen) must run under the Debian 6.12 kernel.

## Two-part build (experiment 09)

1. **Stage A, on Bookworm** (`build-trixie-rootfs.sh`): trixie's debootstrap
   1.0.141 runs `--foreign` with every package included. It unpacks 207 packages
   (392 MB) using Bookworm's tools only, and stages the inputs under
   `/percept-build`.
2. **Stage B, under 6.12** (`stage-b.sh`, run by `builder-init`):
   `percept-entry-20261021-09` executed at 10:56:02 UTC from stock boot
   `8810bf12-2ede-4b82-b724-0b34584ceded`. It used the experiment 08 path and
   command line plus the `ext4` modules.
   - The builder found the Bookworm rootfs at `/dev/mmcblk1p3` by its ext4
     superblock UUID (the static BusyBox has no `blkid`) and mounted it
     read-write.
   - It ran the second stage, installed the tested kernel `.deb` (held), and
     configured the system with no network.
   - It printed `STAGE B DONE`, unmounted cleanly at 593 s, and rebooted. The
     board was back on stock (`2eb09155-…`) 656 s after the request. Reset
     reason `0x1` and watchdog counter `0x16` were unchanged.
3. **Stage C, on Bookworm** (`pack-trixie-rootfs.sh`): Bookworm's GNU tar, with
   xattrs, ACLs and numeric owners, writes `trixie-root.tar.gz`. It is 260 MB
   with 21,341 entries; SHA-256 is in `trixie-root.tar.gz.sha256`.

Result: Debian 13 trixie, 208 packages, 713 MB unpacked.
`/boot/vmlinuz-6.12.113+deb13-arm64` matches the tested Image (`391a3b39…`).
Debian's `initrd.img-6.12.113+deb13-arm64` (`c3e999a7…`) contains `imx2_wdt`,
`sdhci-esdhc-imx` and `ext4`. Evidence and the build record are in
`sources/firmware-audit/trixie-builder-20261021-09/`, and the tarball is
kept there too.

Known follow-ups for the first trixie boot:
- The initramfs fsck hook warned that it couldn't identify the type of root
  `UUID=a842734f…`, because that filesystem doesn't exist yet. Root fsck then
  falls to `systemd-fsck-root`. Run `update-initramfs -u` once trixie is running.
- The builder had no RTC/NTP time, so files written in stage B carry 1970
  timestamps. timesyncd corrects the clock at runtime.

## Launcher test (21 October 2026, 11:17–11:35 UTC)

ESP before install: `sources/firmware-audit/launcher-test-20261021/esp-before-launcher.img`,
hash matched on board and PC.

The ESP got `/percept/` (launcher `f930311d…`, `launcher.conf` pointing at the
experiment 08 RAM-only test, rescue keys and host key). `grub.cfg` became
`experiments/percept-launcher/grub.cfg.test`: entry 0 is the launcher and the
fallback is the byte-identical Bookworm entry (kept as `grub.cfg.bookworm`). A
1024-byte `boot/grub2/grubenv` holds `percept_tries=4`.

Result, from UART and 54 acknowledged UDP records:

| Boot | GRUB | Launcher | Outcome |
|---|---|---|---|
| 1 | launcher (tries 4→3) | attempt 1/3, capture OK, jump | 6.12 test, self-reboot at 180 s |
| 2 | launcher (3→2) | attempt 2/3, jump **delayed 61 s** | early "rescue" at 43 s, then jump at 75 s |
| 3 | launcher (2→1) | attempt 3/3, same delay | same |
| 4 | launcher (1→0) | `rescue_mode failcount_3_limit_3` | rescue: dropbear SSH works, no kexec modules |

- GRUB loads an unsigned initrd for the stock kernel, and its `load_env` and
  `save_env` work on the FAT ESP.
- The countdown reached 0, so a further boot would have gone to Bookworm.
- From rescue: `grub.cfg.bookworm` was restored as `grub.cfg` (the test config
  is kept as `grub.cfg.launcher-test`), `failcount` reset to 0, and the board
  rebooted. Bookworm returned in 122 s (`8e7fd18e-…`, original command line).
  Reset reason `0x1` and watchdog counter `0x16` were unchanged.

**Launcher bug found and fixed** (in `experiments/percept-launcher/init`, not
yet rebuilt or installed):
- At 1.7 s the stock kernel's imx-sdma driver falls back to user-helper firmware
  loading with a 60 s timer, and the launcher has no udev.
- Device shutdown cancels that request and the driver asks again. In boots 2
  and 3 the second request held `kernel_restart_prepare()` for 60 s.
- The launcher's 30 s execution wait then started rescue mode while the kernel
  was still going to jump.

Fixes:
1. Write 1 s to `/sys/class/firmware/timeout` and abort pending
   `/sys/class/firmware/*/loading` requests at startup.
2. After the trigger, never enter rescue unless `kernel_kexec()` returns an
   error. If no jump happens within 300 s, request a normal reboot.

## Launcher retest with the fixes (build 20261021-02, 11:38–11:53 UTC)

Build `launcher-20261021-02/launcher.cpio.gz`: 4,931,101 bytes, SHA-256
`68020cd2…3857`, the same member list as build 01, `init` `d6edb741…`. It was
installed with `failcount=0` and `percept_tries=4`; config and rescue keys were
unchanged.

| Attempt | `Entering kernel_kexec` | `Starting new kernel` |
|---|---|---|
| 1/3 | 14.115 s | 14.521 s |
| 2/3 | 14.087 s | 14.489 s |
| 3/3 | 14.087 s | 14.450 s |

All three jumps took about 0.4 s, with no early rescue. The three 6.12 boots
rebooted themselves at 180 s, and boot 4 entered `rescue_mode
failcount_3_limit_3` with dropbear SSH working. The PC received 46 records.
From rescue, `grub.cfg.bookworm` was restored and `failcount` reset. Bookworm
returned in 57 s (`6c208162-…`, original command line, reset reason `0x1`,
watchdog counter `0x16`). Evidence: `sources/firmware-audit/launcher-retest-20261021/`.

## Install procedure (step 4)

Files: `experiments/percept-trixie/rescue-install.sh` (runs in launcher rescue,
Bookworm tools only), `experiments/percept-launcher/launcher.conf.{rescue,trixie}`,
`grub.cfg.production`, and the updated `percept-boot-ok`, which also re-arms
`percept_tries`.

1. Boot rescue: ESP `launcher.conf` = `mode=rescue`, the test `grub.cfg`
   (Bookworm fallback), `percept_tries=2`. The previous test config is kept as
   `percept/launcher.conf.test`.
2. Backup. In rescue p3 is never mounted.
   - PC: `ssh rescue 'dd if=/dev/mmcblk0p3 bs=1M | gzip -1' > p3-bookworm.img.gz`.
   - Board: `rescue-install.sh hash-p3`.
   - PC: `gzip -dc | sha256sum` must equal the board hash. **Stop and confirm
     before formatting.**
3. `rescue-install.sh install < trixie-root.tar.gz` runs
   `mke2fs -t ext4 -U a842734f… -L trixie` with Bookworm defaults (the same
   features as the old p3, which GRUB 2.03 can read). It extracts with GNU tar
   (xattrs, ACLs, numeric owners) while hashing the stream, checks the kernels,
   symlinks and fstab, and installs the new `percept-boot-ok`.
4. `rescue-install.sh arm` installs the production `launcher.conf`
   (`/vmlinuz`, `/initrd.img`, switches only, no hash pins, so Debian kernel and
   initramfs updates keep working) and `grub.cfg.production` (trixie entry plus
   rescue entry; an exhausted countdown means rescue). It also sets
   `failcount=0` and `percept_tries=4`.
5. Reboot → launcher → Debian 6.12 → trixie. `percept-boot-ok.service` resets
   both counters about 60 s after SSH and the network are up.

Restore path: from rescue, `gzip -dc p3-bookworm.img.gz | ssh rescue 'dd of=/dev/mmcblk0p3 bs=1M'`
(after `blockdev --setrw`), then put back `grub.cfg.bookworm`.

## Install and first trixie boot (21 October 2026)

- The p3 backup was skipped at the user's direction: USB (uuu) restore of the
  default image is the recovery path. A partial stream was deleted.
- In rescue (boot `8e40eefe-…`), `rescue-install.sh install` formatted p3 and
  extracted the tarball in 47 s. Its stream hash `cc20b2f4…` matched, and the
  kernel, symlink and fstab checks passed. One warning: tar could not restore
  the named-group ACL on `/var/log/journal` (rescue has no `/etc/group`);
  systemd-tmpfiles reapplies it at boot. `arm` then installed the production
  `launcher.conf` and `grub.cfg`.
- **First production boot fell back to rescue** (`capture_failed`, counter 1).
  kexec had written a valid 73.8 MB bundle, but `emit()` stored the UDP
  sender's status in the global `$result`. With no PC receiver, the sender
  returned 4 and overwrote kexec's 0. Both earlier tests had a receiver running.
  The fix uses its own `send_status`.
- With no Bookworm build host left, build 03 was made by
  `tools/replace_initramfs_member.py`. It swapped only `init` (`d6edb741…` →
  `c62863e2…`) into build 02; the other 59 members are byte-identical.
  `launcher.cpio.gz` SHA-256 is `0833eab2…c012`, 4,931,154 bytes.
- **Second production boot, with no receiver running:** GRUB → stock kernel →
  launcher (`kexec_mod: Starting new kernel` at 19.3 s) → Debian 6.12 →
  Debian initramfs → systemd 257 → `percept-dk login:` on ttymxc0. SSH was up
  103 s after the reboot (boot `d538c732-…`).
  - It reports `6.12.113+deb13-arm64` and Debian 13 (trixie), with `/` on
    UUID `a842734f…` mounted rw.
  - `eth0` got <BOARD_IP> by DHCP, DNS resolves, and NTP is synchronised.
  - `imx2_wdt` is loaded with `RuntimeWatchdogUSec=1min`. The PMIC and
    CPU-frequency modules are blacklisted as intended.
  - `percept-boot-ok` reset `failcount` to 0 and `percept_tries` to 4.
  - The only failed unit is `systemd-networkd-wait-online`, which also failed
    on every stock Bookworm boot.
  - 632 MB of the 15 GB root is used.

Known gaps (boot-time errors), none of which block SSH:
- The vendor DT's 960 MiB CMA reservation fails.
- No thermal sensor (`qoriq_thermal` cannot parse the vendor sensor cells), and
  CPU frequency scaling is deliberately off.
- Wi-Fi `rtw_8822ce` firmware is missing (`firmware-realtek` is not installed).
- USB `dwc3` is deferred (`failed to get extcon`).
- SPI flash on `spi3` is not registered (chip select in use).
- The initramfs fsck hook still lacks the root type: run `update-initramfs -u`.

## Upper 1 GB RAM probe (21 October 2026, trixie boot `d538c732-…`)

Initially Linux sees 3 GB, and `pe100.dtb` only describes
`0x40000000–0xFFFFFFFF`. U-Boot also prints `DRAM: 3 GiB`. The initial
assumption that Debian consumed the EFI map was later corrected: this boot
rejects incomplete EFI handover and uses the DT memory bank instead.
Debian 6.12,
unlike the vendor kernel, can address the i.MX8MQ's second window
`0x100000000–0x13FFFFFFF`.

`experiments/percept-trixie/probe-upper-ram.pl` runs a static BusyBox `devmem`
(mmap of `/dev/mem`), because arm64 `read()` on `/dev/mem` refuses memory the
kernel doesn't manage. Results:

- **No aliasing:** a 768 MiB tagged buffer in lower RAM. For 150 of its pages
  (99 in `0x4–0x8…`, 51 in `0x8–0xC…`), the matching upper addresses under
  both likely wrap schemes did not contain the tag.
- **Stable contents:** 128 samples across the upper GB were all re-read
  identically, with mixed values (39 zero, 36 all-ones, 29 distinct others),
  as expected for unused DRAM.
- **Writable:** 64 write/read-back/restore cycles at 16 MiB spacing all
  succeeded. No kernel errors followed, and the system stayed healthy.

Conclusion: the 4th GB appears to be real, separate, accessible DRAM. It is not
yet given to Linux. Doing that without kernel changes means passing an
extended memory description at kexec: either a patched UEFI memory map with an
added `EfiConventionalMemory` descriptor for the upper GB, or a DTB second
`/memory` bank. That should be followed by a full memory test of the region.

### Upper-memory boot demonstrated

The target-only live DT memory bank was extended to 4 GiB through the launcher,
without a kernel patch. Boot `5e09d6ac-7d41-44b2-9f8f-6234225c27cd` reports
System RAM through `0x13fffffff`, 4 GiB physical memory and 4,008,368 KiB
`MemTotal`. SSH, Ethernet and the eMMC root filesystem work. The stock
bootstrap/rescue DT remains unchanged. See [the upper-RAM implementation and
test record](percept-upper-ram.md) for details and memory-test results.

A second boot with the production configuration retained the 4 GiB map
(`a2897fef-892d-4743-8a9c-9f9b705aa72f`, 4,008,364 KiB `MemTotal`).
The production launcher config now includes `upper_ram=1`; the kernel remains
stock. The RAM test was stopped during the remaining sweeps at the user's
direction after the completed patterns passed.

## Status

- [x] Trixie rootfs built and tarball archived on the PC
- [x] Launcher initramfs built (4.9 MB, fits ESP): `launcher-20261021-01`, `f930311d…`
- [x] Launcher test: 3 kexec cycles → rescue SSH, Bookworm untouched
      (rescue-timing bug found and fixed; retest with build 02 passed)
- [x] Trixie installed from rescue mode (backup skipped by user; USB restore is the fallback)
- [x] First trixie boot reachable over SSH (launcher build 03)
- [x] Upper 1 GiB enabled through the launcher; persistence reboot and automatic counter reset verified
- [x] Three consecutive warm reboots, all hardware checks passing
      (`experiments/percept-hardware/reboot-soak.sh`, 3/3; see `gpu-vpu-plan.md`)
- [ ] Three power-disconnected cold boots (needs a person at the power connector)
