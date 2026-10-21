# Security

## What this project does and does not protect

- The boot chain is signed UEFI → shim → GRUB → Microsoft's stock kernel. The
  launcher then `kexec`s **your** kernel, which is not signed. Secure boot
  therefore protects the first hop only; do not describe the resulting system
  as having a verified boot chain.
- The installer ships no passwords, SSH keys or host keys. Passwords are never
  defaulted; SSH host keys are generated on the board at first boot.
- Your per-board configuration (`boards/`, `secrets.toml`, `out/`) contains
  secrets (Wi-Fi PSK, password hashes, keys). It is git-ignored; keep it that
  way and do not paste it into issues. `percept` logs are redacted, but check
  before sharing.
- Rescue mode (stock kernel + SSH) accepts the keys in the ESP file
  `percept/authorized_keys`. If you enable `rescue.password_auth` it also accepts
  the `root` password whose hash is in `percept/rescue_password_hash` (your choice;
  a password is easier to use and easier to guess - pick a long one and keep the
  board off untrusted networks). Anyone with physical access to the board's eMMC
  or USB recovery can bypass either; that is inherent to the hardware.
- Services you add (for example the camera RTSP preview) are your
  responsibility; the bundled preview is unauthenticated and unencrypted.

## Reporting a vulnerability

Please report privately through GitHub's *Security → Report a vulnerability* on
this repository. Do not open a public issue for anything that exposes keys,
credentials, or a way to bypass rescue-mode authentication.
