# Percept upper 1 GiB on Debian trixie

## Boot result

The first upper-memory boot succeeded on 21 October 2026. It uses the stock
Debian `6.12.113+deb13-arm64` Image and normal Debian initramfs, with the
existing stock-kernel launcher/rescue path.

- Previous boot: `d538c732-1621-4a56-974b-6805b5fb5a28`.
- Reboot requested: 12:47:57 UTC (13:47:57 London).
- Upper-memory boot: `5e09d6ac-7d41-44b2-9f8f-6234225c27cd`.
- Marker: `percept_upper_ram=20261021-01`.
- Linux reports 1,048,576 physical pages: 4 GiB.
- `/proc/iomem` includes System RAM through `0x13fffffff`.
- The Normal zone is `0x100000000–0x13fffffff`.
- `MemTotal` increased from 3,040,388 to 4,008,368 KiB. Kernel reservations,
  memory-management metadata and DMA buffers account for unavailable memory.
- SSH and Ethernet work; `/` is the existing ext4 filesystem on eMMC p3, rw.

This establishes a successful warm boot with the additional memory online.
The subsequent reboot and partial memory-pattern coverage are recorded below.

## Persistence check

After stopping the remaining RAM tests at the user's direction, the production
`launcher.conf.trixie` was installed with `upper_ram=1` and no temporary
command-line marker. A normal reboot was requested at 13:07:54 UTC.

Boot `a2897fef-892d-4743-8a9c-9f9b705aa72f` again runs
`6.12.113+deb13-arm64`, recognizes System RAM through `0x13fffffff`, and
reports 4,008,364 KiB `MemTotal`. SSH, DHCP Ethernet and the rw eMMC root
filesystem work. Launcher and configuration hashes match their installed
versions; GRUB's original `pe100.dtb` is unchanged.

Production configuration SHA256:
`79743f406f65dc89a5d0eed6be319ca9a0ec270b7407bbb620d463a9e7c48344`.
This verifies persistence across an ordinary reboot. A power-disconnected
cold boot was not part of this check.

At 13:12:27 UTC, the existing `percept-boot-ok.service` completed automatically
and restored `failcount=0` and `percept_tries=4`. A subsequent SSH check verified
those values with the same boot ID and 4 GiB memory map. The stock rescue
route remains configured. The service's delay included the existing
network-online wait; no manual counter reset was used for this check.

## Memory-test result and scope

`memtester 1100M 1` obtained and locked 1,100 MiB. Pagemap inspection counted
195,584 unique pages (764 MiB) from `0x100000000–0x13fffffff` inside its test
allocation. Address, random-value, XOR/SUB/MUL/DIV/OR/AND comparisons,
sequential increment, solid bits, block sequential, checkerboard and bit-spread
tests all reported `ok`.

At the user's direction, the remaining sweeps were stopped during bit-flip
testing to proceed with persistence checking. The recorded status is 143
(intentional SIGTERM), not a completed-test success code. No memory mismatch
was reported before stopping. This is partial pattern coverage of 764 MiB of
the upper bank, not a full physical-bank test; kernel-held pages were not tested.

## Actual memory-description path

The running Debian boot logs `Can't find property 'linux,uefi-secure-boot'
in DT!` and exposes no `/sys/firmware/efi`. EFI initialization returns before
using the firmware memory map. The effective memory description for this
tested kernel is the DT memory bank, despite other EFI properties remaining
in `/chosen`. The earlier assumption that this Debian boot consumed the
UEFI map was incorrect.

Debian's [EFI FDT parameter source](https://sources.debian.org/src/linux/6.12.94-1~bpo12%2B1/drivers/firmware/efi/fdtparams.c/)
and [arm64 EFI patch](https://sources.debian.org/patches/linux/6.12.107-1/features/all/lockdown/arm64-add-kernel-config-option-to-lock-down-when.patch/)
explain the missing-property return. These nearby source versions corroborate
the actual selected kernel's observed log and memory-map behavior; they are
not a substitute for its runtime evidence.

## Implementation

`experiments/percept-upper-ram/extend-fdt.c` is a static musl AArch64 helper.
The launcher calls it only when `upper_ram=1` appears in `launcher.conf`,
and only after the rescue-mode checks. It reads that stock bootstrap boot's
fresh `/sys/firmware/fdt`, then changes the memory bank from
`<0 0x40000000 0 0xc0000000>` to `<0 0x40000000 1 0>` in a new `/run` file.
Kexec consumes that target-only copy. GRUB's `pe100.dtb`, the signed stock
kernel and its own memory map remain unchanged.

The helper changes exactly two bytes. DTB length, phandles, all other
properties and reservation-map entries remain identical. It requires the
expected bank/cell layout, refuses existing output files and rejects an input
with `linux,uefi-secure-boot` present: a future complete EFI handover needs a
separately designed EFI map extension. It does not remove or fabricate that
property. No kernel patch or firmware/provisioning change is involved.

Native tests passed for the current live DTB and rejection of truncated input,
an already-extended bank, wrong cell sizes, a complete-EFI fixture, and existing
output. The launcher passed static BusyBox shell syntax checking.

## Artifacts and rollback

PC evidence: `sources/firmware-audit/upper-ram-20261021-01/`.
Device evidence and prior launcher: `/root/percept-upper-ram/`.

- Previous launcher SHA256:
  `0833eab2bff3889aeb4d92bb3efea4df65486942b8934f652412fad4ccd6c012`.
- Upper-memory launcher SHA256:
  `46e4bd0dd84336f9d7c290e3a73a1da1a74f8647f6c04c073e2f0512b2dfba27`.
- New helper SHA256:
  `f917b933c288061a792e42680d7a0f566164950c93d18ad9a6f7ed81969bf33b`.

`build-launcher.py` replaces only `init` and adds the helper. All other 59
archive members remain byte-identical with unchanged metadata. The installed
archive is 4,962,849 bytes. The ESP cannot retain two full launchers, so the
prior archive is retained on p3 and the PC.

For a RAM-only rollback, remove `upper_ram=1` from the installed launcher
configuration and reboot. For a complete launcher rollback, restore
`launcher-before.cpio.gz` and `launcher-before.conf` from the device evidence
directory to `/boot/efi/percept/launcher.cpio.gz` and `launcher.conf`, then
reset the existing failure/countdown counters. From stock rescue, mount p3
to access these backups; its normal startup leaves p3 unmounted.

The first experiment was armed with `failcount=2` and `percept_tries=1`, giving
one attempt before stock rescue. Trixie's existing boot-ok service resets
these after its normal startup delay when the boot succeeds.
