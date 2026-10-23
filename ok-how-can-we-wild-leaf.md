# Clean Debian trixie on the Percept, reachable over SSH

## Context

Experiment 08 proved that Debian's stock `6.12.113+deb13-arm64` kernel boots on the
Percept via our kexec path. Every driver loaded, PCIe Ethernet worked, and the eMMC
was detected. It needed only command-line switches (`cpuidle.off=1`, …).

The user now wants a **clean Debian trixie install, replacing Bookworm entirely**,
with SSH reliably up on the new kernel. Constraints:
- Keep the kernel stock Debian. Use switches, not patches (see memory).
- The signed boot chain is fixed: UEFI → shim → GRUB → **stock 5.4 kernel**. GRUB's
  config on the ESP is editable. It already loads `pe100.dtb` from the ESP, and the
  binary contains `initrd`, `load_env`/`save_env` and `fallback`.
- Today the Bookworm rootfs (p3) is also the kexec "launcher". If p3 is wiped, the
  launcher has to move.

Facts from read-only checks:
- ESP (p1) is 11 MB with 8.9 MB free.
- The stock kernel has igb, the i.MX eSDHC driver, ext4, initrd and gzip built in,
  with the eMMC at `mmcblk0`.
- Under 6.12 the eMMC is `mmcblk1`, so the new system must use `root=UUID=` and a
  UUID-based fstab.
- The experiment 08 hook `90-percept-kexec-test` is **still installed** on the board.
  It's disarmed by its boot-ID check, but it needs removing.

## Design

**Launcher = stock kernel + small initramfs on the ESP.** GRUB boots the stock kernel
with `initrd $efiroot/percept/launcher.cpio.gz`. The launcher runs entirely in RAM:
1. Mount proc, sys and dev. Read `/boot/efi/percept/launcher.conf`: target kernel and
   initrd paths on p3, the 6.12 switches, and the mode.
2. **Failure counter** in `/boot/efi/percept/failcount`. If it's ≥ 3, or the GRUB
   entry passes `percept.mode=rescue`, go to **rescue mode**: built-in igb with the
   static address <BOARD_IP>/24, dropbear SSH on port 22, UDP report, no kexec.
   Otherwise increment the counter, sync, and unmount the ESP.
3. Mount p3 read-only. Capture the bundle with the existing quiet-purgatory
   `kexec -c -l` + `capture.so`, using trixie's own `/boot/vmlinuz-6.12…` and
   `/boot/initrd.img-6.12…`, `--dtb=/sys/firmware/fdt`, and
   `--append="root=UUID=<trixie> ro console=ttymxc0,115200 cpuidle.off=1 clk_ignore_unused pd_ignore_unused efi=noruntime net.ifnames=0 module_blacklist=rohm_bd718x7,bd718x7_regulator,imx_cpufreq_dt"`.
   This module blacklist keeps the unqualified PMIC and CPU-frequency drivers out,
   which is a switch, not a kernel change. Then unmount p3.
4. Run `insmod arch.ko detect_el2=0`, then
   `insmod core.ko bundle=… execute=1 percept_caam_reset=1 percept_ocotp_clock=1`,
   then write 1 to `trigger`. This is the experiment 06 path, without systemd
   shutdown.

**Trixie rootfs (p3)**: a plain debootstrap build of Debian trixie arm64.
- **Kernel:** Debian's `linux-image-arm64`, pinned to the tested `6.12.113-1`. Its
  initramfs comes from Debian's own initramfs-tools. `/etc/initramfs-tools/modules`
  adds `imx2_wdt` so the inherited watchdog gets fed early.
- **Packages:** openssh-server, systemd-networkd DHCP (`eth* en*`, as in
  `00_build_rootfs.sh`), systemd-timesyncd.
- **System config:**
  - fstab by UUID.
  - `RuntimeWatchdogSec=60`, so a userspace hang resets the board.
  - `authorized_keys`: your `id_ed25519.pub` and the test key.
  - Hostname and passwords per `config.sh`.
- **Stock kernel file:** the stock `vmlinuz-5.4.3-mariner` copied into `/boot`, so
  GRUB can still load it.
- **Boot-confirmation unit** `percept-boot-ok.service`: starts after `ssh.service`
  and `network-online.target` (+60 s), mounts the ESP and resets `failcount` to 0.

**GRUB** (`grub.cfg`; keep the current file as `grub.cfg.bookworm`):
- entry 0: "Debian trixie": stock kernel + launcher initrd + pe100.dtb.
- entry 1: "rescue": the same with `percept.mode=rescue`.
- `set fallback=1`.

During testing, before the wipe, the fallback is the existing plain Bookworm entry
instead.

## Files to create (in `<LOCAL_PATH>`)

- `experiments/percept-launcher/init`: launcher PID1, modelled on
  `experiments/percept-custom/init`. It reuses that file's identity, UDP `emit()`,
  MAC-matching and timer patterns.
- `tools/build_percept_initramfs.py`: extend it so it can also package arbitrary
  dynamic ARM64 binaries with their library dependencies (`--binary SRC`, the same
  logic it already uses for `udp_log_sender`). Its existing 6.12 module mode stays
  unchanged.
- `experiments/percept-launcher/launcher.conf.example` and the `grub.cfg` template.
- `experiments/percept-trixie/build-trixie-rootfs.sh`: native debootstrap on the
  board plus chroot configuration, reusing the config steps of `00_build_rootfs.sh`
  and `config.sh`. It produces `trixie-root.tar.zst`.
- `experiments/percept-trixie/percept-boot-ok.service` + script.
- `docs/trixie-install.md`: the procedure and results; update the
  `docs/debian-kernel-test.md` status.

Reused as-is: `core.ko` from `caam-20261021-02` (`03cd9ebb…`) and `arch.ko`
(`c90f408f…`), the quiet-purgatory kexec-tools 2.0.25 build, `capture.so`,
`udp_log_sender`, `udp_log.py`, and static BusyBox.

## Steps, each with a gate

0. **Housekeeping.** Remove the leftover experiment 08 hook. Record the
   experiment 08 result in `docs/debian-kernel-test.md`.
1. **Build trixie on the board** under Bookworm (`apt install debootstrap`;
   debootstrap into `/root/trixie-root`). Check that it contains
   `vmlinuz/initrd.img-6.12.113+deb13-arm64` and that `sshd -t` passes in a chroot.
   Copy the tarball to the PC.
2. **Build the launcher** on the board and check that it fits the ESP (< 6 MB).
   Add the Bookworm fallback entry to GRUB.
3. **Launcher test, without the wipe.** Point `launcher.conf` at the proven
   experiment 08 RAM-only Debian initramfs, which reboots itself at 180 s.
   - Expect 3 kexec cycles over UART/UDP, then the counter reaches 3 and the
     launcher drops to **rescue mode**.
   - Gates: SSH into rescue works; the counter resets cleanly. This proves loading
     an initrd from GRUB, the counter and rescue mode before anything is destroyed.
   - **Ask the user before this reboot.**
4. **Backup, then install. Ask the user before the reboot.**
   - Boot into rescue mode. p3 is unmounted there, so the copy is consistent.
   - Stream `dd if=/dev/mmcblk0p3 | gzip` to the PC, plus a fresh ESP image.
     Gate: hashes match on board and PC.
   - In rescue: `mkfs.ext4 -U <trixie-uuid> -L trixie /dev/mmcblk0p3`, then fetch
     the tarball from a PC HTTP server and extract it with xattrs. The bundled GNU
     tar and mke2fs come from step 2.
   - Set `mode=kexec` and `failcount=0`. Switch GRUB to the final trixie and rescue
     entries.
5. **First trixie boot. Ask the user before the reboot.**

## Verification (end-to-end)

- UART shows: stock kernel → launcher → `Starting new kernel` →
  `Linux version 6.12.113+deb13-arm64` → Debian initramfs → systemd.
- From the PC: `ssh root@<BOARD_IP>` (DHCP-reserved address) reports
  - `uname -r` = `6.12.113+deb13-arm64`;
  - `/etc/os-release` = trixie;
  - `systemctl is-system-running`, `systemctl --failed`;
  - `findmnt /` = the trixie UUID;
  - `failcount` = 0 after the boot-confirmation unit runs.
- Run `systemctl reboot` three times and get SSH each time (the acceptance criterion
  in `docs/debian-kernel-test.md`).
- Failure path: after three failed boots the board lands in rescue SSH on the stock
  kernel. From there, restoring is `gunzip | dd` of the p3 backup and putting back
  `grub.cfg.bookworm`. USB `uuu` recovery (`flash.bat`) remains the last resort.
