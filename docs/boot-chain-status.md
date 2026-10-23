# Boot Chain Exploit + Signed Update Status

Last reviewed: **2026-10-20** (earlier source matrix retained below)

This document tracks whether any *new public exploit* or *official signed update* changes the Azure Percept DK constraints documented in [`README.md`](../README.md).

## Current Verdict

- **Public trust-chain break path:** No practical public path confirmed for Percept DK.
- **Official signed Microsoft/NXP fix path (kernel/bootloader/keys):** No public path found.
- **Full 4 GB RAM enablement via official signed update:** No evidence found.

## Device-specific update, 20 October 2026

Custom module initialization and stock-kernel staging without the original
RANDSTRUCT seed are now demonstrated. One attempted kexec transition returned
through the normal boot path without the marker; the failing stage is unknown.
This changes the practical path forward without establishing a boot-chain bypass.
See [the staged plan](kernel-path-forward.md) and [test record](kexec-jump-test.md).

Read-only inspection of the running UEFI variables found `SecureBoot=1`,
`SetupMode=0`, and two SantaCruz production signing certificates in `db`.
There is no general Microsoft third-party UEFI CA entry. The installed EFI loader
hashes match the recovery files. An ordinary distro-signed shim is therefore not
a qualified alternative boot chain on this device.

The recovery SPL banner is `2019.04`, built 21 January 2022. NXP's
[FIT metadata verification change](https://github.com/nxp-imx/uboot-imx/commit/0746cfd931de8f7591d263ff60dd806ffe23c093)
is relevant to the i.MX8M SPL authentication review. Actual installed SPL
identity, FIT processing and vendor mitigations still need comparison.
The banner alone does not establish authentication behavior.

The recovery GRUB contains a `2.03` version string. Assess its actual code and
vendor backports when comparing it with later upstream releases.

## Findings Matrix

| Source | Date | Claim | Relevance | Constraints / Notes |
|---|---|---|---|---|
| Microsoft Percept overview | 2023-02-07 | Percept DK retired; after 2023-03-30 no platform/OS support updates | High | Official retirement state strongly suggests no future signed Percept DK platform updates ([link](https://learn.microsoft.com/en-us/previous-versions/azure/azure-percept/overview-azure-percept-dk)) |
| Microsoft Percept security page | 2023-02-07 | Root-of-trust model and retirement state | High | Confirms secure-boot model and lifecycle status ([link](https://learn.microsoft.com/en-us/previous-versions/azure/azure-percept/overview-percept-security)) |
| Microsoft azure-percept-advanced-development releases | 2021-12-15 (latest) | No newer public release stream for Percept artifacts | Medium | Not definitive for firmware, but no public ongoing release cadence ([link](https://github.com/microsoft/azure-percept-advanced-development/releases)) |
| NXP i.MX8M product/security info | Ongoing | Mentions HAB/security features; no public Percept re-key path | Low-Medium | No public OEM/user process found to replace Percept trust anchors ([link](https://www.nxp.com/products/i.MX8M)) |

## Direct Answers

### Q1: Any public exploit likely to break Percept DK trust chain today?

**No confirmed practical path.**

Related boot stacks (`EDK2`, `shim`, `GRUB`) require component-specific review; no authoritative evidence currently shows a directly usable chain-break path on Percept DK with the known locked-signature boot flow.

### Q2: Any official signed update path from Microsoft/NXP likely to fix kernel config/DTB and unlock full RAM?

**No public evidence.**

No public post-retirement signed Percept DK kernel/bootloader update path was found that would enable changing `CONFIG_ZONE_*` kernel behavior or trust anchors.

## Confidence + Unknowns

- **Evidence boundary:** no practical bypass confirmed; this is not proof that none exists.
- **Key unknowns:** installed SPL code and vendor patch status, reachable vulnerable bootloader paths, and any private/OEM update channels.
