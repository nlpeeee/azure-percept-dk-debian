# Third-party notices

This repository contains original installer code and documentation (MIT, see
[LICENSE](LICENSE)) and derivative works of GPL-2.0 software (see
[LICENSES/GPL-2.0-only.txt](LICENSES/GPL-2.0-only.txt)). Per-file licences are
in [REUSE.toml](REUSE.toml) and SPDX headers.

## Derived or built-from components

| Component | Licence | Where / how used |
|---|---|---|
| [kexec-mod](https://github.com/fabianishere/kexec-mod) @ `4ba956f` | GPL-2.0 | Base of the kexec kernel modules; our changes are `kexecmod/patches/0001-kexec-mod-percept-port.patch`. |
| [kexec-module](https://github.com/amonakov/kexec-module) | GPL-2.0 | Upstream of kexec-mod's kernel-side port. |
| [kexec-tools](https://git.kernel.org/pub/scm/utils/kernel/kexec/kexec-tools.git) 2.0.25 | GPL-2.0 | Built into the launcher; optional LED-telemetry patch in `kexecmod/patches/optional/`. |
| [BusyBox](https://busybox.net) | GPL-2.0 | Launcher userspace (built, not vendored). |
| [Dropbear](https://matt.ucc.asn.au/dropbear/) | MIT-style | Rescue-mode SSH server (built, not vendored). |
| [e2fsprogs](https://e2fsprogs.sourceforge.net) | GPL-2.0 / LGPL-2.0 | `mke2fs` used by the installer (built, not vendored). |
| [libfdt / dtc](https://git.kernel.org/pub/scm/utils/dtc/dtc.git) | GPL-2.0-or-later / BSD-2-Clause | Linked by the device-tree helpers in `launcher/fdt/`. |
| [Linux kernel](https://www.kernel.org) 5.4.3 | GPL-2.0 | Headers/build tree used only to compile the kexec modules. |
| [uuu (mfgtools)](https://github.com/nxp-imx/mfgtools) | BSD-3-Clause | Downloaded by `percept fetch`, not redistributed here. |

Debian packages are downloaded from Debian mirrors at build time under their
own licences.

## Not redistributed (downloaded from the vendor, hash-checked)

The Microsoft Azure Percept DK recovery image and everything inside it (stock
kernel, modules, firmware, boot loader, `flagutil`), the ASUS/Intel/NXP
firmware and the `azureeyemodule` container layers are the property of their
owners and are **never** included in this repository or its releases.
`vendor/vendor-manifest.toml` lists each input with its source URL and SHA-256.

## Trademarks

Azure and Percept are trademarks of Microsoft. Debian is a registered trademark
of Software in the Public Interest, Inc. This project is independent and
unaffiliated.
