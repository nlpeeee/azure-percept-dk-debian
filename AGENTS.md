# Agent guide: Debian on Azure Percept DK

The installer builds Debian arm64 images and prepares portable installation
bundles. See `README.md`, `docs/install.md` and `docs/portable-installer.md`
for the installation paths and boot-chain constraints.

## Layout
- `percept`, `percept.cmd`, `src/percept/` - CLI, GUI and shared installer backend.
- `boards/` - private board settings and secrets; never commit them.
- `build/`, `profiles/`, `kexecmod/` - source-build scripts, OS profiles and kexec helpers.
- `launcher/`, `target/` - signed-route launcher and target-side provisioning helpers.
- `vendor/` - pinned download metadata; Microsoft binaries are not distributable.
- `cache/`, `out/` - ignored downloaded inputs and generated artifacts.
- `tests/`, `board-tests/` - software checks and separately authorized hardware checks.
- `legacy/`, `docs/legacy/` - historical scripts and procedures, not the default installer.

## Building and validation
Source builds need Linux or Windows with WSL2; see `docs/build-wsl.md`.
Portable preparation runs natively on Windows/Linux without WSL. Ask before a
full image build unless the user has already authorized it; builds use several
GB and must not interfere with another checkout's active build or outputs.
Run `python -m unittest discover -s tests/unit -v` and
`python dev/scrub-scan.py` for applicable software changes.

## Hard rules
- Never commit private board settings, credentials, private keys, generated
  personal images, downloaded Microsoft firmware or other non-redistributable binaries.
- Never run `uuu`, `flagutil`, historical flash scripts or anything that writes
  to a USB device, eMMC or the board without explicit approval.
- Do not SSH into the board or change its state unless asked.
- Preserve the demonstrated signed boot route: HAB fuses are closed. Do not
  replace the signed factory bootloader/kernel. Debian kernel and initramfs
  preparation through the existing launcher/kexec route is supported.
- Work only in the current checkout. Do not edit, reset or delete sibling
  worktrees or their caches and outputs. Merge into main or push only when asked.
- In an Orca worktree, legacy source blobs may be read from the existing
  legacy checkout's `sources/` directory. Keep generated outputs in the current
  worktree's `out/` directory; do not modify shared inputs.
- Keep publishing and hardware qualification separate from software checks.
  Never label an image hardware-qualified from host-side package checks alone.
