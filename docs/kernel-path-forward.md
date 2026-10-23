# Path to a custom Percept kernel

Planning review: **20 October 2026**, following the first controlled jump attempt.

## Decision

User direction after this plan: proceed directly to a custom-kernel test with
USB recovery available. Retained RAM tracing is optional debugging work, not a
prerequisite. The EFI partition has been backed up; no RAM reservation or boot
configuration change was deployed. See [the custom-kernel test](custom-kernel-test.md).

Keep the working module-loading route as the main path. Investigate the specific
SPL authentication issue in parallel as a fallback. The next device reboot should
be a logged, staging-only shutdown rehearsal, after non-disruptive checks pass.
It should not attempt another unobserved kernel jump.

The intended outcome is a custom kernel running with a recoverable boot path.
Loading a module, staging an image, entering the relocation code, and reaching
the new kernel are separate milestones.

## What is established

- The hello module and patched kexec modules loaded without Microsoft's original
  RANDSTRUCT seed. The stock Image, marked DTB and purgatory staged successfully
  with `execute=0`, and the modules unloaded.
- The execution attempt returned to an ordinary boot without the marker. Its
  retained journal ends before the final hook. We cannot distinguish a skipped
  hook, insertion error, shutdown stall, failed handoff or early second-kernel
  failure. A brief second-kernel boot followed by reset is also not excluded.
- The temporary hook is removed. The original services and eight containers
  recovered. See [the attempt record](kexec-jump-test.md).
- Read-only inspection during this planning review found SecureBoot enabled and
  SetupMode disabled. The firmware `db` contains two X509 certificates named
  `SantaCruz SecureBoot Production Signing`, issued by `Microsoft Testing PCA
  2010`. It has no generic Microsoft third-party UEFI CA entry. `MokListRT`
  contains a SantaCruz certificate too. An ordinary distro-signed shim is therefore
  not justified as an admitted alternative chain by the observed trust store.
- Installed `bootaa64.efi` and `grubaa64.efi` hashes match the recovery image.
  Recovery GRUB contains `2.03`; recovery SPL and U-Boot banners say `2019.04`
  with a 21 January 2022 build date. These strings do not establish vendor patch
  status. The installed SPL has not yet been compared with the recovery SPL.

Evidence: `sources/firmware-audit/boot-chain/inventory-summary.json`, the archived
public EFI variables, and `boot-chain/trust-analysis/variables.json`. No firmware
variables, boot entries or keys were changed during this review.

## Work sequence and gates

| Step | Work | Evidence required to advance |
|---|---|---|
| 1. Preserve recovery and identify artifacts | Retain tested binaries, hashes, boot configuration and current container/service inventory. Identify the installed SPL and its FIT layout without writing boot storage. | Exact artifacts tied to this device; recovery instructions and source-boot-ID disarming retained. |
| 2. Check payload and mapping without a jump | Inspect full purgatory; validate Image placement and DTB reservations; verify staged bytes and identity-map descriptors. | All three staged segments match the bundle, including zero-filled tails; physical mappings and reset routine coverage agree. |
| 3. Prove logging during normal operation | Run a UDP receiver on the PC and send numbered records from the board using fixed addresses. | Received records with experiment ID, stage, source boot ID and time. Receiver remains on the PC. |
| 4. Rehearse final shutdown with staging only | Use a one-boot hook that logs every branch, loads with `execute=0`, unloads both modules, then permits ordinary reboot. | Complete hook/staging/unload records received or durably saved, followed by restored services and original command line. |
| 5. Attempt an observed same-kernel transition | Only after steps 1–4 pass, use the same checked payload and add execution-boundary records. | Marked second-kernel boot, preferably with an early initramfs report; retain logs and compare boot IDs/cmdline. |
| 6. Introduce the custom kernel | First boot a conservative kernel and small diagnostic initramfs; add the production rootfs and optional hardware after boot/SSH are proven. | New kernel release/build ID, expected DTB and command line, working storage/network, then repeated controlled boots and service recovery. |

Steps 1–3 do not require a reboot. Step 4 intentionally causes an ordinary reboot
and service outage, but does not execute a new kernel. This document plans those
steps. Subsequent execution completed the staged-page/mapping checks, PC logging
and step 4 successfully; see [the results](kexec-staging-diagnostics.md). Installed
SPL/FIT identity now matches the recovery artifacts; its authentication ordering
remains under investigation in [the SPL review](spl-authentication-review.md).

### Checks missing from the staging result

Walk the completed relocation list in a diagnostic build and reconstruct the
destination bytes for each segment. Compare them with the intended Image, DTB
and purgatory, including zero padding. Validate list bounds and termination.
This checks allocator/source-page swapping and list construction that a valid
bundle alone cannot prove.

Cross-check the module VA-to-PA walker with the CPU's address-translation result,
with migration prevented and architectural state preserved. Software-walk the
new identity tables and check physical alignment, permissions, memory attributes,
TCR/MAIR assumptions, and the entire reset routine plus literal pool. **Do not
install the experimental TTBR0 during this live diagnostic.**

The retained purgatory entry calls a C function whose complete body was not
previously inspected. Audit its verification and failure paths, not just its
final branch. Check Image `text_offset`, `image_size`, flags, RAM ranges, reserved
regions and all segment boundaries. The capture tool's `/proc/kcore`/VA_BITS
warning is a reason to verify placement explicitly, not proof of bad placement.

Restore the native `pre_disable_mmu_workaround` sequence in the next diagnostic
build and revalidate its disassembly. The target enables the option that expands
this to an ISB, but its omission has not been diagnosed as the failure on this
Cortex-A53. Do not combine this with speculative changes to CPU shutdown or
enabling the unvalidated hyp shim.

### Logging without UART

The first logger should be a bounded userspace UDP sender in the final hook.
Record hook entry, source boot ID, asset checks, root mount options, each module
insertion result and each unload result. Test delivery before shutdown; then
prove whether interface/link/address state survives the actual shutdown phase.
If it does not, qualify a minimal static network setup in the rehearsal.

The stock kernel has netconsole disabled and lacks its netpoll support. Building
only an external `netconsole.ko` is not a ready solution. A functioning pstore
backend is also unproven; `CONFIG_PSTORE=y` and empty directories do not provide
a persistent trace.

If UDP cannot cover the hook, a separate USB/SD data filesystem could retain
numbered hook records. It must be mounted deliberately in that phase, flushed and
unmounted before execution. Opening an existing file on read-only root with
`O_DSYNC` does not make it writable. No raw boot-partition logging is proposed.

**Coverage limit:** `kernel_restart_prepare()` shuts down devices. Neither UDP
nor filesystem writes can be assumed to work after that point. If a later jump
fails after the last observable record, stop repeating the same test. Qualify a
reserved RAM trace or a documented, unowned persistent scratch location across
normal resets before using it for the transition, or obtain a compatible 1.8V
serial console. Reset survival and bootloader preservation must be demonstrated;
neither is presently established.

## Online research and the fallback route

The SPL authentication review concerns FIT processing before authentication on
i.MX8M devices, including this SoC family. Establishing the actual behavior on
Percept requires matching its SPL code, FIT loading path and vendor changes.
Compare the extracted artifacts against NXP's changes before any device
experiment. A 2019.04 banner is a research lead, not a runtime result.
[NXP FIT metadata verification change](https://github.com/nxp-imx/uboot-imx/commit/0746cfd931de8f7591d263ff60dd806ffe23c093).

The recovery GRUB contains a 2.03 version string. GRUB and shim comparisons
should use the actual included modules and vendor changes rather than the age
of a version string alone.

An alternative signed shim normally uses its own embedded vendor certificate to
admit subsequent images. The actual Percept trust inventory above blocks assuming
that a generic Microsoft-signed distro shim will be accepted. PK/KEK certificates
named `Test Secure Boot Signing` do not establish that their private keys are
public or that key changes survive firmware reprovisioning.
[Upstream shim documentation](https://github.com/rhboot/shim/blob/main/README.md).

The SPL route becomes a priority only if offline evidence establishes both
applicability and a recoverable test path. It would address the boot chain, but
would still require a board-compatible kernel and device initialization. Generic
kernel privilege-escalation research adds little: root and execution of our module's
initialization code are already demonstrated.

## Immediate next work

The non-executing diagnostics and staging-only rehearsal passed. Follow the
user's subsequent direction to build and test a custom kernel with a temporary
diagnostic initramfs. RAM tracing remains an optional response to failure. No
physical trace address or firmware RAM retention has been qualified.

Primary references for execution constraints:
[Linux 5.4 ARM64 boot requirements](https://raw.githubusercontent.com/torvalds/linux/v5.4/Documentation/arm64/booting.rst),
[Linux 5.4 reboot path](https://github.com/torvalds/linux/blob/v5.4/kernel/reboot.c),
[systemd 252 shutdown-hook lifecycle](https://www.freedesktop.org/software/systemd/man/252/systemd-shutdown.html).
