# Boot Chain Watchlist (Monthly)

Use this checklist to quickly re-evaluate whether anything changed around:

1. Breaking the Percept DK trust chain
2. Getting an official signed kernel/bootloader update path
3. Recovering the missing RAM via official signed firmware updates

## Sources to Check

- Component release notes for `imx8`, `HAB`, `u-boot`, `edk2`, `shim`, `grub2`
- U-Boot security advisories: <https://github.com/u-boot/u-boot/security/advisories>
- EDK2 advisories: <https://github.com/tianocore/edk2/security/advisories>
- shim releases/advisories: <https://github.com/rhboot/shim/releases>
- GRUB advisories (distro + upstream channels)
- Microsoft Percept docs (retirement/support state)
- Microsoft `azure-percept-advanced-development` releases/tags
- NXP security and i.MX8M advisories

## Triage Rules

Mark each finding with one outcome:

- `NO-IMPACT`: Not in Percept boot path or wrong component/version
- `THEORETICAL`: Same component family, but exploit preconditions unlikely on Percept
- `ACTIONABLE-RESEARCH`: Could plausibly apply; needs version/boot-flow verification
- `BREAKTHROUGH`: Credible chain-of-trust bypass or official signed update path

## Monthly Runbook

1. **Collect:** Add new source links to the bottom of [`boot-chain-status.md`](boot-chain-status.md).
2. **Map:** For each item, map to a Percept boot component (`SPL`, `U-Boot`, `UEFI`, `shim`, `GRUB`, kernel).
3. **Gate-check:** Verify exploit requirements (physical access, netboot, writable EFI, privilege level).
4. **Decide:** Assign one triage outcome.
5. **Summarize:** Update "Current Verdict" in [`boot-chain-status.md`](boot-chain-status.md) if outcome changed.

## Fast Decision Criteria

Treat as **potential breakthrough** only if at least one is true:

- A public exploit bypasses signature enforcement in Percept's actual deployed boot flow.
- Microsoft or NXP publishes a signed Percept DK bootloader/kernel update that changes key constraints.
- A documented official process appears for key enrollment/re-keying on Percept DK hardware.

Otherwise keep verdict as "no practical public path" and continue monthly monitoring.
