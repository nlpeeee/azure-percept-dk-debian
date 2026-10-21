# Source for the kexec kernel modules and launcher

The launcher archive and `arch.ko` / `core.ko` are built from this repository:

- Kernel modules: upstream [kexec-mod](https://github.com/fabianishere/kexec-mod)
  at commit `4ba956fd60b29d2fea324515596b392afdcfa2c5` plus
  `patches/0001-kexec-mod-percept-port.patch` (all of our changes, including the
  CAAM/OCOTP warm-handoff code), built against mainline Linux 5.4.3 with the
  stock kernel's symbols (`extract_kernel_exports.py`, `prepare_hello_probe.py`).
- Launcher userspace: BusyBox, kexec-tools 2.0.25, Dropbear, e2fsprogs and the
  device-tree helpers in `launcher/fdt/`, built by `launcher/build.sh`
  (pinned versions in `vendor/vendor-manifest.toml`).

Anyone who receives these binaries from this project may obtain the complete
corresponding source from the matching tagged commit of this repository, or by
asking in a GitHub issue. Licence texts are in `LICENSES/`.
