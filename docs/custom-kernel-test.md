# Direct custom-kernel test

Date: 20 October 2026. The user chose direct testing with USB recovery available,
without making retained-RAM debugging a prerequisite.

## Preparation

The first candidate uses the verified mainline Linux 5.4.3 source already used
for the module builds, with release suffix `-percept-test1`. This keeps the
starting hardware configuration close to the working firmware kernel. It is
not a vendor-source reconstruction or a claim of a maintained production kernel.

The configuration enables native kexec, file-based kexec, initrd/gzip support,
devtmpfs and netconsole/netpoll. Intel igb, i.MX PCIe, i.MX eSDHC and ext4 remain
built in. RANDSTRUCT plugins, module signing and debug information are disabled.
The first wired diagnostic build disables cfg80211/mac80211; this also removes
the regulatory signature chain's unnecessary OpenSSL host-tool dependency.

Build dependencies are extracted in the device workspace. Kernel compilation
uses its GCC 12.2 with host `-fcommon`, two jobs, and reduced CPU/I/O priority.
The existing source tree is reused after saving its prior config and export
table under `custom-kernel/`; an interrupted duplicate source extraction is not
used for this build.

Debian's static ARM64 BusyBox package was downloaded and unpacked in the workspace,
not installed system-wide:

```text
busybox-static 1:1.35.0-4+deb12u1+b1
SHA256 732c9135564fc71337e0e05fb4da4d11e6c28c1834bce3e405e575afef2a52f5
```

It includes the required shell, init, mount, IP, timeout and reboot applets,
plus HTTP serving. The initramfs builder checked ELF architecture and static
BusyBox linkage, shell syntax and applet availability. It packages the existing
UDP sender with its loader/libc dependencies, initial device nodes, and experiment
identity. Nothing is installed in the production boot path.

## Test behavior

The external initramfs runs entirely in RAM. It finds the Ethernet adapter by
MAC, assigns the existing board address `<BOARD_IP>/24`, sends records to
`<HOST_IP>:6666`, and exposes `/status.txt` on HTTP port 8080 when available.
The report includes kernel build identity, command line, boot ID, links and log.
It never mounts or modifies the production root filesystem. A timer requests
ordinary firmware reboot at 180 seconds of kernel uptime.

The execution bundle must be generated from this boot's live DTB and contain
the custom Image, initramfs, DTB and purgatory. Before execution, use the tested
module loader's non-executing page/mapping verification. Capture the existing
services/container inventory and use external logging for the final shutdown
hook. A new boot ID alone is not success: require a report identifying the
`5.4.3-percept-test1` kernel and the experiment marker.

After the temporary test, verify the original kernel and services return and
remove the temporary hook. A successful custom-kernel boot does not yet prove
production hardware support or justify replacing the signed boot path.

## Recovery and current status

The complete 11 MiB EFI partition was copied off the board. Its SHA-256 is
`ab9cdab550d44859754e653ed0e7665f9211a47fe8f3241673ca65be9c3c8223`.
The original GRUB configuration and DTB also remain unchanged and backed up.
No RAM-trace module, reservation DTB or boot-guard configuration was deployed.

Compilation and candidate preparation are in progress. No custom-kernel jump
has been attempted yet.
