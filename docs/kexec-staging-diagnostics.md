# Non-executing kexec diagnostics and shutdown rehearsal

Date: **20 October 2026**. Target: `5.4.3-26.cm1`, Percept DK.

## Live diagnostics

The diagnostic ARM64 and core modules loaded, staged the retained marked bundle
with `execute=0`, and unloaded. All four operations returned status zero. Source
boot ID was `5f3204c1-5edd-45f3-a256-08c3797b7dec`.

The ARM64 initialization compared the module's page-table walker with CPU
`AT S1E1R` results, preserving PAR with interrupts masked. All four aligned 4 KiB
objects passed: reset routine, PGD, PUD and PMD. Exact descriptor links,
attributes, unused entries, physical continuity and TCR/MAIR assumptions passed.
These checks did not install the custom TTBR0.

```text
TCR=00000032b5503510
MAIR=0000bbff440c0400
SCTLR=0000000034d4d91d
idmap_t0sz=16
idmap check: PASS; inactive map only, TTBR0 unchanged.
```

The core walked 9,241 relocation-list entries covering 9,218 source pages.
All Image (9,203 pages), DTB (11 pages) and purgatory (4 pages) bytes matched
the intended bundle, including the zero-filled tails. It did not copy pages to
their final destination addresses.

The actual verifier C function also passed 15 userspace harness cases: valid
payload, changed content, changed padding, changed zero-only segment, missing
page, duplicate destination, source outside simulated RAM, mixed flags,
reserved low bits, invalid DONE, indirection cycle, truncated payload, memory
limit, zero entry and destination outside the segments. This checks parser
behavior; it does not emulate ARM hardware or establish arbitrary-pointer safety.

The module descriptor preparation checked every imported CRC against the
recovered export tables. Final disassemblies contain no `sp_el0` or stack-canary
references. The AT save/read/restore sequence contains no calls while IRQs are
masked, and the reset code now has the native ISB workaround before writing
SCTLR_EL1. No actual reset-code execution was performed by these diagnostics.

Prepared binary SHA-256:

```text
5f747e2ce2776caf6f96b185d2ff4378a4107c8534e1e90d9ef3fc3b3df2689d  arch.ko
81a1d7db87b8fb7d559440022c9c6dae6055f9bfec3f2ba46e7921d4c71e244e  core.ko
```

## Offline payload audit

The complete purgatory disassembly includes a SHA-verification failure loop.
Its embedded expected digest matches the retained Image and DTB, including
zero-filled tails:

```text
02ca22e2dca320a9d08ed5d2047ad059247cdf55eeaee99265bf1f4e96504975
```

`skip_checks` is zero. The Image header specifies text offset `0x80000`, image
size `0x23f3000` and flags `0xa`. All three segment ranges satisfy their checked
placement constraints, lie inside DTB RAM, and avoid its fixed reservation at
`0xb8000000` (4 MiB). The DTB also requests a dynamically allocated CMA region;
this check does not establish where a new kernel will allocate it.

The retained DTB contains EFI memory-map and system-table physical references.
Linux 5.4 reserves the memory-map bytes and marks non-usable EFI regions NOMAP,
so retained references are not automatically wrong within the same firmware
boot. However, **an execution candidate must be regenerated from the current
live DTB after every normal firmware reboot**, and its EFI references must be
qualified. The old bundle here is used only for staging diagnostics.
[Linux 5.4 EFI initialization](https://raw.githubusercontent.com/torvalds/linux/v5.4/drivers/firmware/efi/arm-init.c).

## External logging and rehearsal

The PC receiver bound `<HOST_IP>:6666`. The board at `<BOARD_IP>` received
an ACK after the receiver flushed and fsynced its record. No firewall changes
were made. Interface `eth1` uses the `igb` driver and MAC `<BOARD_MAC>`.

The prepared hook's check-only run emitted all 11 expected records: hook entry,
boot ID, asset hashes, manifest, configuration, MAC, no network changes,
network gates, modules absent, root-RO gate deferred, and successful end. It
performed no module operations or network changes. Linux shell syntax and the
native sender build passed with compiler warnings treated as errors.

The staging-only shutdown rehearsal was launched at **16:53:28 UTC
(17:53:28 London)**. Its temporary hook is
`/usr/lib/systemd/system-shutdown/90-percept-staging-test`, SHA-256
`df9a7ae9b18a6f4a768f53ddccf0af559d801c3cdbb3c0740d38228394c22d55`.
It is tied to the source boot ID above and passes only `execute=0`.
The verified configuration permits bounded restoration of the exact Ethernet
address and a direct receiver route after network-service shutdown. Root must
be read-only before this or module insertion; the hook performs no remounts.

**Rehearsal passed.** The receiver saved all 20 consecutive records, from hook
entry at 16:53:51.212 UTC to `staging_complete_normal_reboot` at
16:53:52.225 UTC. Root was read-only. The verified network restoration returned
zero. Both module insertions and removals returned zero. No kernel jump occurred.

SSH was reachable by 16:55:46 UTC. The subsequent boot ID is
`82bb3525-7e83-4f80-82dc-a8f437cb5262`; command line and kernel are original.
The temporary hook was removed and the PC receiver stopped. Docker, `deq`, SSH
and all eight containers recovered; the mail container is healthy. The existing
network-online unit timed out before Docker and `deq` started, accounting for a
startup delay. That unrelated configuration was not changed.

External record SHA-256:
`0f22ecb65d3f76b6b8d948678b62fdc44e7f97b6aa73dfb92922da743fc2fe16`.
The parsed successful sequence is saved in `staging-rehearsal-result.json`.

## Next gate: retained execution trace

Before another jump, qualify a dedicated RAM trace region. No physical address
has yet been qualified. Inventory the live DT/EFI maps and firmware load ranges;
prepare an alternative DTB with a fixed, non-reusable reservation and a proved
recovery/fallback selection. Preserve the original boot files. Boot reservation
only, and prove the region is excluded from the allocator before writing to it.
Both writer and reader boots must reserve it.

Then test alternating nonce/sequence/stage/CRC records with cache cleaning and
barriers. Require exact recovery after normal reboot, and separately qualify
watchdog-reset retention with filesystems read-only. A Linux reservation does not
prove the bootloader preserves RAM. Module-time reservation is too late for pages
already managed by the allocator. Do not reuse rpmsg/CMA or guess SNVS scratch
registers. External ramoops alone would not restore the compiled-out pstore
console frontend or record an arbitrary silent MMU-off hang.

If retention passes, add explicit markers around device/CPU shutdown, identity-map
installation, reset, relocation and new-kernel entry. Generate a fresh bundle
from that source boot's live DTB. If a recoverable reservation or retention cannot
be established, a compatible 1.8V serial console is the practical alternative.
[Reserved-memory binding](https://raw.githubusercontent.com/torvalds/linux/v5.4/Documentation/devicetree/bindings/reserved-memory/reserved-memory.txt),
[ramoops requirements](https://raw.githubusercontent.com/torvalds/linux/v5.4/Documentation/admin-guide/ramoops.rst).

Evidence is retained locally under `sources/firmware-audit/`, including
`payload-review.json`, `diagnostics-udp-live.jsonl`, boot-partition copies and
SPL inventory. The device retains compiler, preparation, disassembly and runtime
logs in `<LOCAL_PATH>/diagnostics-20261020/`.
