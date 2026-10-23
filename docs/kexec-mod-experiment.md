# Percept kexec module experiment

Date: **2026-10-20**. Target: Percept DK, `5.4.3-26.cm1`, ARM64.

## Observed result

Custom modules built without Microsoft's RANDSTRUCT seed ran on the device:

| Check | Result |
|---|---|
| Minimal hello module insert/remove | Both exit status 0; init and exit logged |
| Patched ARM64 kexec module insert | Exit status 0; boot CPU modes `0xe12 0xe12` |
| Patched core insert with `execute=0` | Exit status 0; three prepared segments staged |
| Core and ARM64 module removal | Both exit status 0 |
| Staged source-page comparison | All 9,218 pages match bundle plus zero padding |
| Inactive identity map | Walker/CPU translations and descriptor checks pass |
| Staging-only final shutdown rehearsal | All 20 external records; load/unload status 0 |
| Controlled reboot with marked payload | Attempted; **no marked boot confirmed** |

The final kernel log includes:

```text
percept_hello: init reached
percept_hello: exit reached
kexec_mod_arm64: Detected boot CPU mode: 0xe12 0xe12.
kexec_mod: Staged 3 prepared segments; execute=0.
```

The staging test left the original kernel running and the modules were removed.
A later controlled reboot attempted execution through a temporary shutdown hook.
The board returned with its original command line and no payload marker; the hook
was then removed. All eight original containers and the main services are back.
See [the jump-test record](kexec-jump-test.md) for timestamps, evidence and the
unresolved failure boundary. No bootloader, boot files or boot configuration were
changed. Loading unsigned external modules taints the running kernel, as usual.

This establishes a working module-loading and image-staging path for this exact
target. It does not establish that kexec execution, another kernel, or arbitrary
external modules will work.

## What the earlier proposal missed

The proposal to remove only `file_operations` and a local `mm_struct` was
incomplete:

1. Linux 5.4 vermagic contains `RANDSTRUCT_PLUGIN_` plus the hashed seed.
2. The generated `__this_module` is a randomized `struct module`, consumed before
   the driver's initialization function runs. Module parameters do not avoid it.
3. `pgd_offset_k()` indirectly dereferences `init_mm.pgd`.
4. The host enables per-task stack canaries, embedding a `task_struct` offset.
5. `copy_highpage()` uses `kmap_atomic()` and writes
   `current->pagefault_disabled`. This was found in compiled disassembly, despite
   the source not containing that dereference.
6. The old identity map has insufficient levels for this host's 4K pages and
   48-bit virtual addresses.
7. The relocation stub clears x0. A raw ARM64 Image needs a DTB address there;
   preserving kexec-tools' prepared trampoline and DTB segments avoids inventing
   an incomplete raw-Image loader.

Primary source references:
[vermagic.h](https://raw.githubusercontent.com/torvalds/linux/v5.4/include/linux/vermagic.h),
[module.h](https://raw.githubusercontent.com/torvalds/linux/v5.4/include/linux/module.h),
[ARM64 mmu_context.h](https://raw.githubusercontent.com/torvalds/linux/v5.4/arch/arm64/include/asm/mmu_context.h),
[ARM64 pgtable.h](https://raw.githubusercontent.com/torvalds/linux/v5.4/arch/arm64/include/asm/pgtable.h).

## Stock evidence recovered

The local recovery image contains `/boot/vmlinuz`, its System.map and config,
and 647 compressed kernel modules. The running device confirmed the same release
and relevant config.

```text
Compiler: GCC 9.1.0
vermagic: 5.4.3-26.cm1 SMP preempt mod_unload modversions aarch64RANDSTRUCT_PLUGIN_1f71cfdf1d02143edadc41196b7f830efd254ca64e4e030e1267ac5b2759220b
module_layout CRC: 0x1765e38a
printk CRC:        0xc5850110
```

All 647 modules have a 768-byte module descriptor, with these observed initializer
positions:

| Field | Evidence | Byte offset |
|---|---|---:|
| `module.name` | Embedded name bytes | 640 |
| `module.init` | `init_module` ELF relocation | 728 |
| `module.exit` | `cleanup_module` ELF relocation, when present | 464 |

The Wi-Fi module retains DWARF. Its DWARF puts these fields at 24, 336 and 752,
respectively, contradicting the actual bytes/relocations. The DWARF cannot be
treated as the final randomized ABI; the precise cause of the discrepancy was
not established. It also does not provide a complete `file_operations` layout.

The module-import census recovered 4,948 CRCs. Parsing the signed ARM64 Image's
PREL32 export entries and CRC tables recovered **14,053 built-in exports**.
All **4,091** CRCs shared with the independent stock-module census matched.
`Module.symvers.kernel` uses Linux 5.4's column order:
CRC, symbol, namespace, module, export kind. It excludes exports supplied by
loadable modules and is not a reconstruction of the source build environment.

Image SHA-256:
`fec6f292e734ab81c056a28ab0c3940ec7f00fcd39cec417cac9da52bb3f7ef2`.

System.map SHA-256:
`1caaca34473399c4cff30148b3b31a4bddb63c025c3e81151171c8ebd90c0eeb`.

## Implementation

Upstream: [fabianishere/kexec-mod](https://github.com/fabianishere/kexec-mod),
commit `4ba956fd60b29d2fea324515596b392afdcfa2c5`.

The patch is saved in `patches/kexec-mod-percept-experimental.patch`; its complete
frontend and bundle format documentation is included as `PERCEPT.md`.

- Resolve the host's real `init_mm` and `swapper_pg_dir` separately, keeping the
  mm object opaque. Resolve `__boot_cpu_mode` directly and call the host's real
  `cpus_are_stuck_in_kernel()` guard.
- Replace the char-device/sysfs frontend when built with `PARAM_LOADER=1`.
  Parameters select a prepared bundle and optional execution; execution defaults
  to false. Read with `kernel_read`, stage kernel buffers, and validate lengths,
  alignment, overlap, entry containment and truncated/trailing input.
- Capture the legacy request from kexec-tools using an LD_PRELOAD library.
  It never forwards kexec or reboot. The actual Debian ARM64 kexec-tools 2.0.25
  binary successfully produced the three-segment stock-kernel bundle.
- Build a proper PGD→PUD→PMD block hierarchy for the Percept. Keep the reset
  routine and literal pool within one aligned page and flush the tables.
- Correct the cache-flush end address and Linux 5.4 `totalram_pages()` API.
- Disable per-task stack protection in these experimental modules and replace
  temporary page mappings used by `copy_highpage()` with ARM64 direct-map copies.
  The final disassemblies have no `sp_el0` or stack-canary references.
- Reject the preexisting `shim_hyp=1` option, whose dispatch/cache behavior needs
  separate work.

The generated module descriptor starts otherwise zero-initialized. A narrow ELF
preparation tool reconstructs it at the three observed initializer positions and
copies the stock vermagic. It verifies every imported CRC against the recovered
kernel table, plus the new arch module's exports for the core. **It does not
alter imported CRCs or executable code.** The hello probe imports only printk
and module_layout; its disassembly was checked before its successful load test.

## Files and reproduction

Local, retained under `sources/firmware-audit/` (ignored by Git):

- `metadata/summary.json`, `modules.json`, `imported-symbol-crcs.csv`.
- `metadata/Module.symvers.kernel`, `kernel-exports.json`, `dwarf-crosscheck.json`.
- `metadata/percept_hello.prepared.ko` and its preparation manifest.
- `validation-final/`: tested kexec binaries, preparation manifest, compile logs,
  disassemblies, captured-bundle manifest and runtime logs.

Reproducible analysis tools are under `tools/`; hello source is under
`experiments/percept-hello/`. The public source patch is separate from the
ignored firmware and compiled artifacts.

The device workspace is `<LOCAL_PATH>`. It retains the patched
checkout, tested prepared modules, stock-kernel bundle, logs and a Linux 5.4.3
source tree. The build used the board's GCC 12.2, with the running config adapted
by `olddefconfig`, GCC plugins and signing disabled, and no per-task stack
protector in the experimental module code. This is **not** Microsoft's exact
vendor source/config/toolchain reconstruction.

The old DTC host build needed `HOSTCFLAGS='-O2 -fcommon'` with GCC 12.
`CONFIG_SYSTEM_TRUSTED_KEYRING=n` was passed to Make for the compile check to
avoid its unused host certificate-extraction dependency. Build dependencies were
extracted into the workspace from Debian packages; kexec-tools and its libraries
were also extracted there, without installing its shutdown integration.

Representative compile and descriptor preparation commands, from the device
workspace after applying the patch and recovering the export table:

```sh
cp metadata/Module.symvers.kernel linux-5.4.3/Module.symvers
make -C linux-5.4.3 M="$PWD/sources/kexec-mod/kernel" PARAM_LOADER=1 \
  CONFIG_SYSTEM_TRUSTED_KEYRING=n HOSTCFLAGS='-O2 -fcommon' -j2 modules

python3 tools/prepare_hello_probe.py \
  sources/kexec-mod/kernel/arch/arm64/kexec_mod_arm64.ko \
  metadata/stock-sample.ko metadata/Module.symvers.kernel \
  kexec_mod_arm64.prepared.ko --kexec-experiment

python3 tools/prepare_hello_probe.py \
  sources/kexec-mod/kernel/kexec_mod.ko \
  metadata/stock-sample.ko metadata/Module.symvers.kernel \
  kexec_mod.prepared.ko --kexec-experiment \
  --extra-symvers sources/kexec-mod/kernel/Module.symvers
```

The tool refuses to overwrite outputs. The successful runtime check used:

```sh
insmod ./kexec_mod_arm64.prepared.ko
insmod ./kexec_mod.prepared.ko \
  bundle=<LOCAL_PATH>/same-kernel.bundle execute=0
rmmod kexec_mod
rmmod kexec_mod_arm64
```

Do not generalize these instructions to another firmware build. Matching metadata
does not prove arbitrary source/header compatibility.

## Remaining gate

Three later one-shot same-kernel attempts also returned through the normal boot
path without the marker. The last used `patches/kexec-mod-post-init-trigger.patch`
on top of `patches/kexec-mod-percept-experimental.patch`, and proved that module
insertion returned before the trigger was written. The final acknowledged record
was immediately before the worker called `kernel_kexec()`. See the
[execution record](kexec-jump-test.md) and
[staging diagnostics](kexec-staging-diagnostics.md). Before another execution
attempt, obtain an observable milestone after network shutdown or independently
validate the relocation and target-entry path.
CPU shutdown/PSCI, EL2 handling, MMU/cache transitions and device reinitialization
remain unvalidated by the staging tests. The Cortex-A53 reports no pointer-auth
support. The optional upstream EL2 shim remains disabled.

No exact kernel-devel/source RPM or original seed was recovered. Direct requests
to three old Microsoft RPM URLs returned HTTP 403; the bounded public search
also did not verify an exact package. These access failures do not establish that
development packages or the seed were never published.
