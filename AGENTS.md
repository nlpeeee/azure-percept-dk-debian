# Agent guide: Debian on Azure Percept DK

Scripts that turn Microsoft's Azure Percept DK firmware image into a Debian arm64
system. See `README.md` for the full background and the boot-chain constraints.

## Layout
- `config.sh` – build settings (passwords, hostname, Wi-Fi). Do not commit real secrets.
- `00_build_rootfs.sh` – builds `sources/debian-rootfs.tar.zst` (debootstrap arm64).
- `01_build_image.sh` – patches the MS image, writes `output/debian-percept-dk.raw`.
- `post_flash.sh` – runs on the device after first boot.
- `flash.bat`, `flash.uuu` – flash the board over USB with NXP UUU.
- `docs/`, `experiments/`, `tools/`, `patches/` – research notes, experiments, helpers.
- `sources/` – Microsoft firmware blobs and derived artifacts (many GB, not redistributable).

## Building
Build scripts are Linux-only and need root. From Windows, run them through WSL:
`wsl -d Debian -- sudo bash 00_build_rootfs.sh`. Ask before running a build; it is slow
and uses several GB of disk.

## Hard rules
- **Never commit** anything from `sources/`, `output/`, or other Microsoft firmware
  (raw images, signed kernel, modules, `flash.bin`, Bluetooth firmware).
- **Never run** `flash.bat`, `flash.uuu`, `uuu`, `flagutil`, or anything that writes to
  a USB device, eMMC, or the board without explicit approval.
- Do not SSH into the board or change its state unless asked.
- The kernel and bootloader cannot be replaced (HAB fuses closed). Do not propose
  kernel rebuilds as fixes.
- In an Orca worktree, large blobs are not copied: read them from the main checkout at
  `E:\percept\sources\` and write build output only to your own worktree's `output/`.
