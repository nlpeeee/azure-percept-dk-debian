# Percept SPL authentication review

Reviewed 2026-10-20. Status: **ACTIONABLE-RESEARCH; applicability unresolved**.

The installed SPL and its first FIT image match the recovery firmware byte for
byte. The image uses the i.MX8M HAB/SPL/FIT arrangement addressed by NXP's
FIT metadata verification changes. That makes this a specific binary audit target, but
does not establish a vulnerability. The unresolved question is whether this
vendor SPL authenticates FIT metadata before using it to load payloads.

## Inputs and reproduction

`tools/inspect_percept_boot.py` reads ordinary local files. It inventories HAB
IVTs and their pointed CSF commands, validates FDT block boundaries and tokens,
decodes FIT images/configurations, checks supported payload hashes, and compares
recovery firmware with boot-partition dumps. It never opens a device or changes
an input. The optional JSON output uses exclusive creation, so an existing file
cannot be overwritten.

```powershell
python tools/inspect_percept_boot.py `
  sources/ms-image/fast-hab-fw.raw `
  sources/firmware-audit/diagnostics-readonly/diagnostics-20261020/mmcblk0boot0.bin `
  sources/firmware-audit/diagnostics-readonly/diagnostics-20261020/mmcblk0boot1.bin `
  --reference sources/ms-image/fast-hab-fw.raw
```

Saved machine-readable evidence:
`sources/firmware-audit/boot-chain/spl-authentication-inventory.json`.
Offsets in that JSON are decimal file offsets; the table below uses hexadecimal.

| Input | Bytes | SHA-256 |
|---|---:|---|
| Recovery `fast-hab-fw.raw` | 2,710,361 | `1f8725869ee29c0fe55dc166bb8cb07084b61dabe4b153f536e76d5c4b9980d3` |
| Installed `mmcblk0boot0.bin` | 4,194,304 | `e9b2f92dd6ba4c4ef8db14518eadc2b521734cad3eb5fd63cb870155d96e0df4` |
| Installed `mmcblk0boot1.bin` | 4,194,304 | `bb9f8df61474d25e71fa00722318cd387396ca1736605e1248821cc0de3d3af8` |

The parent investigation acquired both dumps read-only; kernel `force_ro` was
reported as 1. This flag is not evidence of permanent hardware write protection.
The actual eMMC boot-selection EXT_CSD setting was not obtained, so the analysis
does not claim boot-ROM execution of a particular partition merely from its name.

## What the bytes establish

Recovery firmware aligns at boot0 offset `0x8400`. Of its 2,710,361 bytes, only
18 differ, all in the small range `0x1f7a00..0x1f7a34` relative to recovery, or
`0x1ffe00..0x1ffe34` in boot0. Installed data there begins `SCFA`; its meaning
has not been established. This is 512 bytes before the UEFI FIT. It is outside
the SPL and all parsed FDT/FIT regions. Boot1 is entirely zero-filled.

| Region | Recovery offset | Boot0 offset | Observed content |
|---|---:|---:|---|
| First IVT/header copy | `0x0` | `0x8400` | Self pointer `0x32c27000`; not a complete linear mapping of its referenced image at this occurrence |
| Matching IVT with pointed CSF | `0x18c00` | `0x21000` | Same IVT bytes; CSF at relative `0x18c40` |
| SPL IVT | `0x1a000` | `0x22400` | Entry `0x007e1000`, self `0x007e0fc0`, CSF pointer `0x00815fc0` |
| SPL configuration FDT | `0x38860` | `0x40c60` | Size `0x5fa`, `secure_version="1"` |
| SPL CSF | `0x4f000` | `0x57400` | Authenticate Data block `0x007e0fc0`, length `0x35000` |
| First FIT metadata | `0x57c00` | `0x60000` | Size `0x395`; U-Boot, DTB and ATF external payloads |
| First FIT IVT / CSF | `0x58c00` / `0x58c20` | `0x61000` / `0x61020` | IVT self `0x401fddc0`; CSF metadata block starts `0x401fcdc0`, length `0x1020` |
| U-Boot payload | `0x5ac00` | `0x63000` | Load address `0x40200000`, size `0xb31d8` |
| U-Boot configuration DTB | `0x10ddd8` | `0x1161d8` | Size `0x5c18`; RSA-4096 `indirection_key` marked required for configurations |
| ATF payload | `0x1139f0` | `0x11bdf0` | Load/entry `0x00910000`, size `0x6020` |
| UEFI FIT | `0x1f7c00` | `0x200000` | Size `0x9df59`; gzip UEFI payload, SHA-256 hash, RSA-4096 configuration signature metadata |
| Nested indirect-key FIT | `0x1f7ce4` | `0x2000e4` | Size `0x12d6`; RSA-4096 configuration signature metadata |
| Nested key DTB | `0x1f7de8` | `0x2001e8` | Size `0xc84`; subsequent UEFI verification key metadata |

The SPL authenticated-data interval `[0x1a000, 0x4f000)` hashes to
`46f8f74e92a8dd1a0640a2f5ae47466377daaa91cc38486c3eb145930e3ba477`
in both recovery and the aligned boot0 dump. This establishes identical bytes,
not successful HAB verification or execution.

All six FDT/FIT region hashes also match across recovery and boot0. The first
FIT metadata hashes to
`6b170e4511c63e5b709b5a6702eff7722d73957c973430f72d7f91cc709eb880`.
Its CSF includes a range covering the complete metadata plus the IVT. **That
does not prove authentication before parsing/loading**, which is the ordering
under review here. Conversely, the absence of ordinary FIT `hash` or
`signature` subnodes in this first FIT is not evidence that HAB omits it.

The UEFI payload and nested key payload SHA-256 values match their FIT hash
properties. Signature nodes and required public-key properties are present;
RSA signatures and the complete key-indirection chain have not been verified
by this tool.

## Comparison with NXP's fixes

[NXP's verification change](https://github.com/nxp-imx/uboot-imx/commit/0746cfd931de8f7591d263ff60dd806ffe23c093)
addresses i.MX8M SPL FIT metadata verification. The
recovery contains a `U-Boot SPL 2019.04 (Jan 21 2022 - 10:24:12 +0000)` banner.
The target is in the relevant hardware/time family, but that banner cannot
identify vendor modifications or prove affected control flow.

NXP documents two remedies. Its
[default verification change](https://github.com/nxp-imx/uboot-imx/commit/0746cfd931de8f7591d263ff60dd806ffe23c093)
checks a FIT metadata digest stored with the ROM-authenticated SPL before
parsing the FIT. The exact metadata digest above occurs nowhere in this recovery
file. This does not match the documented default appended-digest format, while
leaving open other vendor authentication mechanisms and representations.

The [optional verification change](https://github.com/nxp-imx/uboot-imx/commit/07b688228c5817e4d76cdc5484fd50f92e9cf1f0)
uses a separate early authentication of FIT metadata. The associated
[image-format change](https://github.com/nxp-imx/imx-mkimage/commit/5a0faefc223e51e088433663b6e7d6fbce89bf59)
reserves an additional IVT/CSF pair. No additional pair matching that documented
format was found after this first FIT's existing pair. This is a bounded layout
observation, not proof that the vendor SPL lacks early verification.

NXP's older reference guide also shows the original metadata authentication
block at `0x401fcdc0`, length `0x1020`, matching this image's general arrangement:
[i.MX8M secure-boot guide in Google's NXP U-Boot mirror](https://coral.googlesource.com/uboot-imx/+/ca9c6f091095d3bf09cac42c3eb4493490ac8912/doc/imx/habv4/guides/mx8m_mx8mm_secure_boot.txt).
That reinforces why eventual metadata coverage alone cannot distinguish the
old ordering from the fix.

## Remaining proof and scope

The next useful step is an offline code audit of the now-identified SPL bytes:
locate the FIT loader and HAB authentication call, then establish which metadata
is trusted before each destination copy. A source/binary match or equivalent
control-flow evidence is required for an authentication-ordering conclusion. Parsing
metadata, matching a banner or finding an error string cannot supply that proof.

The tool validates FDT v17 and records rejected candidates; other versions and
compressed inner firmware are outside its parsing scope. IVT-derived address
translations are linear mapping candidates. Separately loaded FIT payloads,
especially ATF, require their own load-address mapping; a coincident in-file
range is not a proved runtime mapping. CSF command bytes are decoded without
cryptographic verification. No decompilation, controlled boot replay, fuse
change, boot-area modification or exploit construction was performed here.

Validation passed against all three inputs: 4/4/0 IVTs and 6/6/0 FDTs, exact
cross-image region hashes, expected external-payload offsets, both available
FIT payload hashes, five malformed/truncated FDT cases and two malformed CSF
cases. This is a format-reader validation, not a security assessment of SPL.
