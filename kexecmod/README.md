# kexec modules

The launcher runs on Microsoft's stock Linux 5.4.3 and has to jump into another
kernel. The stock kernel has no `kexec`, so two small modules (`arch.ko`,
`core.ko`) bring one. They are a port of
[kexec-mod](https://github.com/fabianishere/kexec-mod) (GPL-2.0).

- `patches/0001-kexec-mod-percept-port.patch`: **all** our changes to upstream
  commit `4ba956fd60b29d2fea324515596b392afdcfa2c5`, including the CAAM crypto
  engine and OCOTP warm-handoff code that the Percept needs. Apply with
  `git apply` (or `patch -p1`) to a checkout of that commit. It was verified to
  reproduce the working tree byte for byte.
- `patches/optional/`: a kexec-tools purgatory LED-blink patch used while bringing
  the board up. Not needed for normal builds.
- `NOTES.md`: engineering notes on the port (what was changed and why).
- `extract_kernel_exports.py`, `inspect_stock_modules.py`, `prepare_hello_probe.py`:
  rebuild the symbol table and the randomised `struct module` descriptor that the
  stock kernel insists on. They need files from Microsoft's recovery image, so they
  run on **your** machine against **your** download (`percept fetch`, milestone M4).
  A module built this way loads only on a stock kernel with the same Image hash
  (`fec6f292...`, see `vendor/vendor-manifest.toml`).
- `tests/test_reset.c`: host-side test of the CAAM reset logic with a fake register file.
- `SOURCE-OFFER.md`: where the corresponding source for any binary release lives.

Build with `bash kexecmod/build.sh` in WSL/Linux after `percept fetch`. This
uses the pinned upstream/Linux sources and recovered stock export evidence,
validates the descriptor and disassembly, and writes hashes plus provenance.
Two independent builds were byte-identical and boot-tested in M4; see
[WSL build validation](../docs/build-wsl.md).
