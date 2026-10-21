> Current status (21 October 2026): the module pair was independently rebuilt
> twice in WSL and the resulting launcher booted Debian successfully, confirmed
> over UART and SSH. These are historical bring-up notes; their earlier
> unconfirmed-jump statements are superseded by docs/build-wsl.md.

# Experimental Percept frontend

On 2026-10-20, this port's two modules **loaded without Microsoft's seed,
staged three stock-kernel segments with `execute=0`, and unloaded successfully**
on a Percept running `5.4.3-26.cm1`. A separate hello module also loaded and
unloaded. A later controlled reboot attempted execution with a marked payload,
but the board returned through its normal boot path without that marker.
**A successful MMU-off handoff and kernel jump remain unconfirmed.** No output
from the final shutdown hook survived, so the failing stage is unknown. The
temporary hook was removed and the board's services and containers recovered.

Subsequent non-executing diagnostics passed on the same device: all 9,218
staged source pages matched the intended Image, DTB and purgatory, including
zero padding. The address walker agreed with CPU translations for the reset
and table pages; the inactive identity-map descriptors passed validation.
The diagnostic module insertions and removals all returned zero. These checks
do not install TTBR0 or establish that the MMU-off transition works.

The running kernel consumes a randomized `struct module` before initialization.
The experiment rebuilds that zero-initialized descriptor using the name/init/exit
positions observed in stock ELF bytes and relocations. Merely changing the two
driver interfaces or copying vermagic is insufficient.

The upstream base is commit `4ba956fd60b29d2fea324515596b392afdcfa2c5`.

## Changes

- Resolve the running kernel's `init_mm` as an opaque pointer. Resolve
  `swapper_pg_dir` independently, avoiding `pgd_offset_k()` and its hidden
  `init_mm.pgd` access. Resolve `__boot_cpu_mode` directly instead of decoding
  instructions from another function. Resolve the host's real
  `cpus_are_stuck_in_kernel()` guard rather than returning constant false.
- Build a three- or four-level identity map for 4K pages. The Percept has four
  levels and 48-bit VA. Align the MMU-off reset routine to a page and assert it
  fits there. Flush the page tables before use.
- Check the inactive identity map and compare module VA-to-PA results against
  `AT S1E1R`, preserving PAR with interrupts masked. Reject unsupported or
  inconsistent mappings during initialization. Restore the native pre-MMU-off
  workaround sequence; this is not a diagnosed fix for the earlier attempt.
- Correct the instruction-cache flush's end address and the Linux 5.4
  `totalram_pages()` API.
- Add an optional `PARAM_LOADER=1` frontend which constructs no `file_operations`
  and registers no character device or custom sysfs file. It uses `kernel_read`
  and kernel buffers, with no user-copy payload path.
- Before publishing a staged image, validate its bounded relocation list and
  compare every source page against the bundle plus zero padding. The diagnostic
  reads source pages, never writes destination addresses, and bounds total
  destination memory to 512 MiB. It trusts module-generated list pointers;
  `pfn_valid()` alone does not establish ownership of an indirection page.
- Disable stack protection in this experimental frontend's two modules because
  the host enables per-task canaries, which otherwise embed a randomized
  `task_struct` offset. This is a deliberate experimental tradeoff, not a
  claim that all implicit header accesses have been eliminated.
- Use direct-map page copying on ARM64 to avoid `copy_highpage()`'s hidden
  `current->pagefault_disabled` access. The final core and ARM64 disassemblies
  contain no `sp_el0` or stack-canary accesses.
- Reject `shim_hyp=1`: the upstream shim has unresolved dispatch/cache issues.

## Prepared segments, not a raw Image

The relocation assembly clears x0 before jumping to the image entry. ARM64 Linux
needs a DTB address in x0. A normal `kexec-tools` load prepares a trampoline and
DTB arrangement which must be preserved. The new frontend therefore reads a
bundle of **already prepared kexec segments**, not just an Image and command line.

Build the capture library on an ARM64 Linux system:

```sh
make -C user capture.so
```

With a compatible `kexec-tools` build, the following captures its legacy
`kexec_load` request. The library writes a new file with mode 0600 and refuses
to overwrite an existing file. It never forwards a kexec syscall or reboot:

```sh
KEXEC_BUNDLE=/root/same-kernel.bundle LD_PRELOAD="$PWD/user/capture.so" \
  kexec -c -l /boot/vmlinuz --reuse-cmdline --dtb=/sys/firmware/fdt
```

The capture library fails other direct calls through `syscall()` with ENOSYS.
Some `kexec-tools` builds may need a more targeted interposer. Run the offline
bundle checker before considering module loading:

```sh
python3 ../../tools/check_kexec_bundle.py /root/same-kernel.bundle
```

A bundle is tied to the board's memory reservations and selected boot payload.
Its structural validity does not prove its destinations or bootability.

## Format

All integers are little endian, with no padding:

| Part | Fields |
|---|---|
| 24-byte header | 8 bytes `KXMBNDL1`, u32 version=1, u32 count, u64 entry |
| count Ã— 24-byte descriptors | u64 payload length, u64 destination, u64 destination length |
| payload | segment buffers in descriptor order, with no alignment padding |

Only normal loads are supported, with 1â€“16 segments. Each buffer is limited to
256 MiB and total payload to 512 MiB. Destination alignment, overlap, overflow,
buffer lengths, entry containment, short reads and trailing bytes are checked.
Zero-byte buffers represent zero-filled destination segments.

## Kernel build and loading gate

```sh
make -C kernel KDIR=/path/to/matching/kernel PARAM_LOADER=1
```

This builds both `kexec_mod_arm64.ko` and `kexec_mod.ko`. It does **not** repair
their generated `__this_module` descriptors, the RANDSTRUCT vermagic hash, symbol
CRCs or any remaining vendor ABI differences. Do not load an arbitrary rebuild
just by copying the stock vermagic string or CRCs into it.

The narrowly scoped `tools/prepare_hello_probe.py` helper accepts these two
modules only with `--kexec-experiment`. It checks every imported CRC against the
recovered kernel exports and, for the core, the arch module's `Module.symvers`.
It rejects unexpected frontends, rebuilds the descriptor, and copies the stock
vermagic. It never changes imported CRCs or executable code. This demonstrated
method is not a general compatibility guarantee for other kernel modules.

After preparing and reviewing the descriptor, the frontend parameters are
`bundle=/absolute/path` and `execute=0` (default). Staging allocates and copies
pages; it does not deliberately jump to another kernel. Unloading frees the
staged image. `execute=1` arms a worker during module initialization. Once
`insmod` returns, writing `1` to `/sys/module/kexec_mod/parameters/trigger`
starts `kernel_kexec()` from that worker. The read-only `execution_status`
parameter reports 0 while waiting, 1 after the trigger, 2 before entering
`kernel_kexec()`, or a negative error if it returns. A jump still requires a
separately planned shutdown/recovery procedure.

The stock ELF relocations reveal `module.init=728`, `module.exit=464` and
`module.name=640` in a 768-byte object. These are useful evidence for a minimal
ABI probe; they do not establish the full randomized layout. The Wi-Fi module's
DWARF contradicts those values and must not be used as a final layout header.
