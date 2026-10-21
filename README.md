# Debian on the Azure Percept DK

Run a current Debian (13 "trixie", stock Debian kernel 6.12) on the Azure
Percept DK, with the GPU, hardware video decode, USB-C, Wi-Fi, Bluetooth and
all 4 GiB of RAM working, and your own SSH keys, Wi-Fi and network settings
built in.

> **Status: work in progress.** The boot method below is proven on one board.
> The turnkey `percept` installer is being built in the open: today it can
> check your PC (`doctor`), collect and validate your per-board settings
> (`configure`) and validate OS profiles. Image building and flashing are the
> next milestones - see [Roadmap](#roadmap). Nothing here is affiliated with
> or endorsed by Microsoft.

## How it works

The DK's firmware only boots a Microsoft-signed chain
(UEFI → shim → GRUB → Microsoft's Linux 5.4.3). Instead of fighting that, this
project keeps the signed chain and uses the stock kernel only as a *launcher*:

1. GRUB boots Microsoft's kernel with a small initramfs (the *launcher*) from
   the EFI partition.
2. The launcher reads `percept/launcher.conf`, applies a few device-tree fixes
   to the live firmware tree, loads two small `kexec` modules, and jumps into
   **your** kernel (proven: Debian's unmodified `6.12.113+deb13-arm64`).
3. If anything fails three times in a row, or you ask for it, the launcher
   drops into an SSH **rescue mode** (keys, and optionally a password) on the stock kernel instead of
   leaving you with a brick. A "boot OK" service on the installed OS clears the
   failure counter.

No kernel patches are needed: the Debian kernel is configured with command-line
switches and the firmware device tree is adapted at boot. Details:
[docs/architecture](docs/architecture/).

## What works (Debian 13, kernel 6.12.113, one board)

| Works | Not working / left alone |
|---|---|
| 4 GiB RAM; CPU/PMIC scaling at 800–1300 MHz, optional experimental 1500 MHz | Deep idle states (workaround retained) |
| Vivante GPU (etnaviv, GLES verified) | External RTC, AK audio codec |
| Hantro G1/G2 video decode (H.264, VP8, MPEG-2, HEVC, VP9, bit-exact) | Ethernet FEC (unused on this board) |
| USB-C port (host mode only), USB 3 | USB-C device/peripheral mode |
| Gigabit Ethernet, Wi-Fi (rtw88), Bluetooth, thermal sensor, TPM | |
| Vision camera via Microsoft's extracted runtime ([docs/camera.md](docs/camera.md)) | Detector accuracy not validated |

CPU power-management sources and installer hooks are integrated; select `os.cpu_profile`
for future builds: [docs/cpu-power-management.md](docs/cpu-power-management.md).

Only Debian 6.12.113 is tested. Other kernels may work if they meet the
[kernel contract](docs/profiles.md); treat them as experimental. Board 2 has not
been tested yet - please report results ([CONTRIBUTING.md](CONTRIBUTING.md)).

## Quick start (Windows + WSL2 or Linux)

Requirements: the Azure Percept DK, a USB-C cable, ~30 GB free disk, Python 3.9+.
On Windows install WSL2 with a Debian/Ubuntu distro first (`wsl --install`).

```bash
git clone https://github.com/nlpeeee/azure-percept-dk-debian
cd azure-percept-dk-debian
python percept doctor        # what is missing on this PC, with exact fix commands
python percept configure     # asks for SSH key, Wi-Fi, network, hostname; writes boards/<name>/
```

`percept build`, `percept flash` and `percept install-over-ssh` land with the
next milestones. Until then the proven manual procedure is in
[docs/legacy/trixie-install-lab.md](docs/legacy/trixie-install-lab.md) (written
for the first board; expect board-specific values).

Your settings never leave your machine: they live in `boards/` (git-ignored)
and are injected into the image you build. See
[docs/configuration.md](docs/configuration.md).

## Recovery

You can always return to the factory image over USB with Microsoft's recovery
package: [docs/recovery.md](docs/recovery.md). If a boot goes wrong, the board
falls back to SSH rescue mode on its own after three failed boots.

## Repository map

| Path | What |
|---|---|
| `src/percept/` | The `percept` command (config, validation, doctor; build/flash to come) |
| `launcher/` | Launcher init script, GRUB config, device-tree helpers |
| `kexecmod/` | kexec kernel-module patches and build helpers (GPL-2.0) |
| `target/` | Scripts that run on the board (boot confirmation, installer) |
| `profiles/` | OS/kernel profiles (`debian-trixie`; `_template` to add your own) |
| `board-tests/` | Acceptance tests to run against a board over SSH |
| `camera/` | Optional Vision camera runtime helpers |
| `vendor/` | Manifest of third-party downloads (URLs + SHA-256) |
| `docs/` | Documentation; `docs/lab/` holds raw engineering notebooks; `legacy/` is the old Bookworm flow |

## Roadmap

- [x] Boot method proven (Debian 13 on stock 6.12 via launcher + kexec)
- [x] Per-board config schema, validation, redaction, `doctor`
- [ ] Reproducible launcher and kexec-module build (WSL2/Linux)
- [ ] `percept build` (personalised disk image) and `percept flash` (via `uuu`)
- [ ] `percept install-over-ssh` for boards that are already running
- [ ] Second-board verification, cold-boot tests, prebuilt release assets

## Licence

Installer code and docs: MIT ([LICENSE](LICENSE)). Kernel-module patches and
device-tree helpers are GPL-2.0 derivatives ([LICENSES/](LICENSES/),
[NOTICE.md](NOTICE.md)). Microsoft's recovery image, kernel and firmware are
downloaded from Microsoft onto *your* machine and are not part of this project.
