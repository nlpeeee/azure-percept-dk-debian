# Percept restore point

For installer USB entry and the original Microsoft restoration fallback, see
[guided installation](install.md#enter-usb-recovery-and-flash). The notes below
describe an engineering restore point, not a general-purpose recovery wizard.

Before the boot experiments, `tools/capture_percept_restore_point.sh` captures
the boot areas, both EFI-sized partitions, primary/secondary GPT bytes, partition
layout, network/service/container inventory and a file-level root filesystem
archive. It stops the previously running containers and Docker/deq during the
archive, then restarts them even if capture fails.

The capture directory is `/root/percept-restore-20261020-01`. Its complete contents
must be copied to `sources/firmware-audit/restore-20261020-01/` on the PC and its
`SHA256SUMS` verified there. Container inspection metadata may contain credentials;
this ignored backup directory is private recovery material.

## Backup format and coverage

`rootfs.tar.gz` retains numeric ownership, modes, ACLs, extended attributes and
sparse files. It includes Docker images, writable layers, named volumes and the
LibreNMS bind-mounted data. It excludes the reconstructable experimental build
workspace, pseudo-filesystem contents, temporary files and the swapfile. The EFI
partitions are separate raw images because they are separate mounted filesystems.

This is an application-quiesced file backup, not an atomic filesystem snapshot.
`rootfs-tar.exit` and `rootfs-tar.stderr` record concurrent system-file changes.
An exit status of 1 requires reviewing that log; a corrupt archive or hard read
error is not a successful capture. `capture.exit`, `services-after.txt` and
`containers-after.txt` record completion and service restoration.

The original signed recovery firmware remains at
`sources/ms-image/fast-hab-fw.raw`, SHA-256
`1f8725869ee29c0fe55dc166bb8cb07084b61dabe4b153f536e76d5c4b9980d3`.

## Recovery choices

- A failed RAM-only boot normally requires power cycling back to the existing
  installation. No storage restoration is needed if storage was unchanged.
- Restore changed boot files from the original EFI image or file copies. Identify
  the actual partition before any write; GPT labels are not unique here.
- For a full installation restore, use the signed USB recovery firmware to regain
  a boot environment. Reconstruct the disk image or use a Linux recovery system
  to restore the saved partition layout, EFI images and root archive onto an
  offline root filesystem, preserving numeric owners, ACLs and attributes.
- A raw boot-area dump is forensic/backup material, not automatically a valid
  input to the vendor's `fastboot flash bootloader` format. The original signed
  recovery firmware is the known vendor-format input.

`flash.uuu` performs a full reflash and may replace the user partition. It is
separate from the experimental RAM-only scripts and must not be substituted for
a boot probe. Restoring the file archive requires a Linux filesystem environment;
the archive is not itself a flashable disk image.

After recovery verify the kernel, root partition identity, SSH, Docker/deq and
the captured running-container inventory. Restore the swapfile separately if it
is required; its contents were intentionally not archived.
