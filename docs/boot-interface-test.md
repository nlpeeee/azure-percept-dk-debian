# Ordinary USB recovery and RAM boot test

Prepared 20 October 2026. This is a separate path from the storage-flashing
`flash.uuu` and `flash.bat`. Initial asset preparation used offline checks;
the subsequent live software recovery request is recorded below. The README's historical
`booti` rejection claims have no command/output transcript here and are not the
result of this experiment.

Local validation passed: PowerShell parsing, the wrapper's firmware/command-list
checks in `Validate` mode, and Python parsing/CLI loading. In-memory checks using
the real stock Image and recovery DTB with a synthetic initrd confirmed that the
inspector reports missing live-map qualification and rejects payload overlap and
overlap with the fixed rpmsg reservation. These are offline checks, not boot tests.

## Evidence and recovery entry

The original Microsoft `sources/ms-image/emmc_full.txt` begins with:

```text
SDP: boot -f _flash.bin
SDPV: delay 1000
SDPV: write -f _flash.bin -skipspl
SDPV: jump
```

The new [probe](../experiments/percept-boot/probe.uuu) retains that sequence
and omits all subsequent storage steps. The actual source is the unmodified
`sources/ms-image/fast-hab-fw.raw`, 2,710,361 bytes, SHA-256
`1f8725869ee29c0fe55dc166bb8cb07084b61dabe4b153f536e76d5c4b9980d3`.
The wrapper checks this hash and a fixed command allowlist before doing anything.

NXP distinguishes ROM SDP from SPL's SDPV, whose `write -skipspl` handles the
second stage. The vendor sequence is appropriate evidence for this image;
do not substitute a fixed SPL offset from another board's example.
[NXP protocol reference](https://github.com/nxp-imx/mfgtools/wiki/UUU-default-support-protocol-list).

Microsoft's Mike McCoy documents the ordinary software recovery request
`sudo flagutil -wBfRequestUsbFlash -v1`, followed by reboot, to switch temporarily
to USB mode. The published example uses forced reboot; this experiment instead
uses `sync` and an orderly `systemctl reboot` to shut down services/filesystems.
[Microsoft Percept recovery answer](https://learn.microsoft.com/en-us/answers/questions/365138/reseting-the-percept-to-initial-state).

On this Debian board, the original `/usr/bin/flagutil` was extracted from the
Microsoft image partition `sources/firmware-audit/2.primary.img` and retained at
`sources/firmware-audit/boot-interface-tools/vendor/flagutil`. It is 27,008 bytes,
SHA-256 `8e4a86da44255804d146e6ba74298fa2ae1d498af3058aebb2cb4324be86d07b`.
Its board workspace copy is `<LOCAL_PATH>/flagutil`; it uses the
existing glibc and was not installed as a Debian package or global utility.

The test operator read boot bank A as current partition 1 / backup partition 2,
and bank B `RequestUsbFlash` as zero. The exact vendor write
`<LOCAL_PATH>/flagutil -wBfRequestUsbFlash -v1` succeeded, followed by
readback `0x1`, `sync`, and orderly `systemctl reboot` while the host probe was
listening. This is a recoverable USB boot-request flag write, not fuse
programming. The reboot subsequently entered **fastboot directly**, at USB path
`2:9`, VID:PID `0525:a4a5`, serial `050A81D6F6C99EF5`. The host probe completed
with exit code zero. None of its SDP/SDPV transfer commands ran in this path;
the original recovery firmware file was not downloaded to the board. The direct
FB runtime's exact U-Boot payload hash has not been established.

The guarded Cyres operation and queries `getvar version`, `version`, bare
`help`, `bdinfo`, and `printenv` all returned OKAY. The protocol version was
`0.4`. Console text did not return over USB. The separate environment query
then returned `U-Boot 2019.04`, a maximum download size of `0x40000000`, and
the known literal fallback value `ok`, proving the ordinary volatile
`fastboot.<name>`/getvar path works on this runtime.

| Environment value observed over USB | Value |
| --- | --- |
| loadaddr | `0x40480000` |
| fdt_addr | `0x43000000` |
| initrd_addr | `0x43800000` |
| fdtcontroladdr | `ff519118` (hexadecimal address) |
| fastboot_buffer, bootm_low, bootm_size, ramdisk_addr_r, kernel_addr_r | unset/empty |

The logs are retained in `boot-interface-tools/software-entry-probe-01.log`
and `env-probe-01.log` under `sources/firmware-audit/`. Their SHA-256 values
are respectively
`ae6323b66ce98c1d2b17309fe2243018171a054b04fa605117027feac227546c`
and `1747cdbb0e593c0ba170f869491d09dbbc1f149f0d47f6f7add4097cd013dce9`.
An upper-RAM FDT control pointer and advertised transfer size do not identify
every firmware-owned RAM range.

`help booti` returned FAIL, but follow-up `help version`, `help setenv`,
`help bootm`, and `help bootefi` also returned FAIL, including commands already
demonstrated to execute. Bare `help`, `printenv loadaddr`, and `echo hello`
returned OKAY. Therefore help-with-argument return codes on this USB command
path are **not a command-availability test**. This result establishes neither
missing booti nor an authentication rejection. No kernel attempt had occurred
when these query results were recorded.

The physical fallback uses internal DIP switches, not the previously claimed
external recovery button. Use the official board-revision procedure; no switch
positions are established here. Connect a data cable to the recovery port and
record the actual host interface. An ordinary reboot without the vendor request,
or generic fastboot `reboot-bootloader`, does not establish ROM SDP entry.

NXP's pinned UUU configuration maps i.MX8MQ ROM SDP to VID:PID `1fc9:012b`,
SPL SDPV to `0525:b4a4` with revision `0500..9998`, and includes common FB
IDs `0525:a4a5` and `18d1:0d02`. These identify protocol candidates, not a
verified Percept serial number. Record the actual USB path and IDs.
[NXP UUU configuration](https://github.com/nxp-imx/mfgtools/blob/uuu_1.5.243/libuuu/config.cpp).

## Host preparation and capture

The initial PATH/repository search found no UUU or fastboot executable. The
official UUU binary is now retained in the ignored workspace tool directory;
no tool or driver was installed system-wide. It comes from the
[NXP UUU 1.5.243 release](https://github.com/nxp-imx/mfgtools/releases/tag/uuu_1.5.243)
and its [Windows executable](https://github.com/nxp-imx/mfgtools/releases/download/uuu_1.5.243/uuu.exe),
whose published SHA-256 is
`f6b76a6246befabeadfebdc1cbfe58f35939596caf7b78717ceab599b0c85027`.
[Published asset digests](https://github.com/nxp-imx/mfgtools/releases/expanded_assets/uuu_1.5.243).
If a separate fastboot client is useful, U-Boot points to the official Android
SDK Platform-Tools. UUU already supplies the FB commands used here.
[U-Boot Fastboot documentation](https://docs.u-boot.org/en/latest/android/fastboot.html).

Run the [PowerShell wrapper](../experiments/percept-boot/Invoke-BootInterface.ps1)
from PowerShell. `Validate` performs only local file checks. The next commands
are explicit test-operator actions; they were not executed during preparation.

```powershell
Set-Location <LOCAL_PATH>
.\experiments\percept-boot\Invoke-BootInterface.ps1 -Mode Validate

$uuuTool = '<LOCAL_PATH>\sources\firmware-audit\boot-interface-tools\uuu.exe'
Get-FileHash -LiteralPath $uuuTool -Algorithm SHA256
.\experiments\percept-boot\Invoke-BootInterface.ps1 -Mode DryRun -UuuPath $uuuTool
.\experiments\percept-boot\Invoke-BootInterface.ps1 -Mode Inventory -UuuPath $uuuTool

# Replace 1:2 with this board's exact path from the captured uuu -lsusb output.
.\experiments\percept-boot\Invoke-BootInterface.ps1 -Mode Probe -UuuPath $uuuTool -UsbPath '1:2'
```

`Inventory` saves present USB/HID PnP and CIM records, UUU help and known-device
list, and optional fastboot version/device list. `DryRun` renders the actual
probe and invokes only UUU's local `-dry` check, without USB inventory or transfer.
`Probe` renders a firmware path relative to its command-list directory, invokes
the local `-dry` check, then uses `-v -m` and
30-second initial/stage waits. Each invocation records exact executable hash,
argument array, timestamps, exit code, stdout and stderr under a new ignored
`sources/firmware-audit/boot-interface-tools/capture-*` directory. `-m` scopes
the transfer to one observed USB path. The wrapper's initial inventory lists
devices without transferring firmware.
[UUU command-line options](https://github.com/nxp-imx/mfgtools/blob/uuu_1.5.243/uuu/uuu.cpp).

Actual Windows UUU dry-run testing found that drive-letter absolute file
arguments such as `<LOCAL_PATH>/.../Image` can be prefixed with the command-list
directory and fail lookup. Use forward-slash file arguments relative to each
rendered `.uuu` file for firmware, Image, initrd and DTB. The wrapper continues
to hash the actual firmware through its absolute host path, and rejects a
capture directory on another volume because it cannot form the required
relative firmware argument. Always dry-parse the final rendered list.
The corrected wrapper was dry-run with the hash-verified official UUU 1.5.243
Windows executable: exit code 0, resolving the firmware argument as
`../../../ms-image/fast-hab-fw.raw`. Its captured list/output are under
`sources/firmware-audit/boot-interface-tools/capture-20261020-191814/`.
No transfer or real probe was requested.

The FB phase first retains Microsoft's exact guarded recovery watchdog command:

```text
FB: ucmd if env exists usb_flash_mode; then cyres_wdog unblock_wdog; else echo Skipping Cyres WDOG; fi
```

The original script describes this as turning watchdog maintenance back on to
avoid timeout. The operation's implementation and necessity on this board have
not been established; the command name alone does not establish whether it
enables/disables a watchdog or changes another maintenance state. It is included
as an authorized recoverable hardware-state operation from the original recovery
sequence, with no explicit nonvolatile storage command. If `usb_flash_mode` is
absent, the guard takes the echo branch. If the mode exists but the Cyres command
is missing or fails, UUU may stop; retain that result rather than removing the
guard blindly. A recovery watchdog timeout remains separate from an
authentication or kernel failure.

The remaining FB phase queries version, command help, `bdinfo`, and environment,
then finishes the host script. It requests no kernel execution. A missing query
can stop the script; retain that output and use individually reviewed supported
queries if needed. `FB: done` is UUU script completion, not a board reboot.
UCmd console text may be UART-only; the separate
[environment probe](../experiments/percept-boot/env-probe.md) uses ordinary
volatile environment exports plus getvar responses for USB-only observations.

The probe and template contain no flash, erase, `mmc partconf`, `saveenv`,
environment-save, or storage-write command. SDPV `write` transfers to RAM.
The vendor's eMMC hardware boot partition number 1 normally corresponds to
Linux `mmcblk0boot0`; Linux `mmcblk0boot1` is the second hardware boot area.
Do not interpret vendor comments saying “boot 1” as a Linux node name.

## Qualify an ordinary boot attempt

Use the separate [ordinary boot template](../experiments/percept-boot/ordinary-boot.uuu.template)
only after the signed recovery U-Boot is present as FB. It uses NXP's documented
volatile `fastboot_buffer` environment setting and RAM downloads followed by
`acmd booti`. This is a request to the board's normal boot command; command
presence and signature acceptance remain untested.
[NXP FB kernel example](https://github.com/nxp-imx/mfgtools/wiki/Example).

The prepared Debian Image actually has `text_offset=0`, `image_size=0x2500000`,
and flags `0xa`; its file length is 37,728,192 bytes. The operator's prepared
test ranges are Image `0x52000000..0x54500000`, DTB work area
`0x57000000..0x57200000`, and initrd `0x58000000..0x582044e4`, with ends
exclusive. These are pairwise disjoint in the described lower 3 GiB bank and
avoid the fixed rpmsg range. They are recorded as a recoverable diagnostic
candidate, not proof of a complete live firmware reservation map or successful
kernel entry. The parent operator controls the actual one-shot boot attempt.

Do not fill addresses using the working Linux `/proc/iomem` alone: recovery
U-Boot's relocation, heap, stack, download buffer and firmware usage differ.
Retain its `bdinfo` and `printenv` output, including `loadaddr`, `fdt_addr`,
`initrd_addr`, `fastboot_buffer`, `fastboot_bytes`, `fdt_high`, `initrd_high`,
`bootm_low`, `bootm_size` and `bootm_mapsize` when present. Qualify the buffer
capacity and every automatic relocation destination before download.

The offline [payload inspector](../experiments/percept-boot/inspect-ram-payload.py)
reads the actual uncompressed ARM64 Image header, checks that
`kernel_address - text_offset` is 2 MiB aligned, and checks its full
`max(image_size, file_size)` footprint. It checks RAM-bank membership, pairwise
overlap, DTB fixed reservations, an optional supplied live firmware map, DTB
alignment/size and the kernel/initrd placement window. It reserves 2 MiB around
the staged DTB for growth. It reports dynamic reserved-memory requests and
rejects stale `linux,uefi-*` pointers from an earlier Linux/UEFI boot.
The output remains explicitly subject to live review; it does not invent unknown
firmware ranges. Disabled memory nodes must not be used.
[Linux 5.4 ARM64 boot requirements](https://raw.githubusercontent.com/torvalds/linux/v5.4/Documentation/arm64/booting.rst).

Example invocation with deliberately unqualified placeholders:

```powershell
python .\experiments\percept-boot\inspect-ram-payload.py `
  --image '<staged Image>' --initrd '<staged initramfs.cpio.gz>' --dtb '<recovery-compatible DTB>' `
  --kernel-address '<qualified hex>' --initrd-address '<qualified hex>' --dtb-address '<qualified hex>' `
  --firmware-map '<qualified recovery ranges.json>'
```

The firmware-map JSON is an array of objects such as
`{"start":"0x...","size":"0x...","purpose":"U-Boot relocation/heap/stack from this recovery session"}`.
Record how every range was obtained. A parsed DTB is evidence of described
memory, not proof that recovery firmware initialized every bank. The stock
recovery DTB describes 3 GiB at `0x40000000` and a fixed 4 MiB rpmsg reservation
at `0xb8000000`, plus a dynamic CMA request. It must be checked against the
actual candidate DTB and recovery session.

Keep the RAM-only initramfs's experiment identity, Ethernet report and timed
ordinary reboot. It must not mount the production root filesystem. Review boot
arguments for this path; exclude old EFI memory-map pointers and stale
`linux,initrd-*` properties. Use the inspector's exact hexadecimal initrd byte
count in `booti address initrd:size dtb`. U-Boot documents this explicit size
for a raw initrd. Do not send a raw Image to an Android `fastboot boot` command
and infer an authentication failure from a boot-image format error.
[U-Boot booti syntax](https://docs.u-boot.org/en/v2022.10/usage/cmd/booti.html).

## Bounded offline command/format review

The original recovery U-Boot payload occupies file offset `0x5ac00`, size
`0xb31d8`, with declared load address `0x40200000`. Its SHA-256 is
`4cfac052fb3636593b124ee6159de9536796fc147958cad90f5b68d4e7736a35`.
A bounded byte inspection found these structurally plausible 56-byte
`cmd_tbl_s` records, with name, implementation pointer, usage and help strings:

| Command | Original-file record offset | Implementation pointer | Usage |
| --- | --- | --- | --- |
| booti | `0xfb2a0` | `0x40207888` | ARM64 Linux Image from memory |
| bootm | `0xfb2d8` | `0x4020673c` | Application image from memory |
| bootefi | `0xfb230` | `0x402076a0` | EFI payload from memory |

The table layout follows upstream 2019.04's name/maxargs/padding/cmd_rep/cmd/
usage/help/completion definition. The actual bytes and pointer/string evidence
are retained in `boot-interface-tools/uboot-command-table.json`. This is static
presence evidence in the recovery artifact, not proof of live lookup, execution,
or image acceptance in the direct-FB runtime. No disassembly or runtime action
was performed by this offline check. The REA firmware operation was unavailable
because its Binwalk integration requires Linux and a configured provider.
[Upstream command-table definition](https://github.com/u-boot/u-boot/blob/v2019.04/include/command.h).

An ordinary legacy uImage is a conditional format alternative only if this
runtime supports both `bootm` and `CONFIG_LEGACY_IMAGE_FORMAT`. The standard
64-byte big-endian header uses magic `0x27051956`, header/payload CRC32 values,
Linux OS ID 5, ARM64 architecture ID 22, kernel type 2, and compression ID 0
for an uncompressed Image payload. `ih_load` is the separately qualified final
physical Image address; `ih_ep` points to raw Image offset zero at that address.
It must not point at the 64-byte wrapper or add the kernel's `text_offset`
again. These CRCs provide format integrity, not a signing or authentication
claim. Legacy-format support, raw-initrd support and acceptance by vendor policy
remain unknown; a different container is not a response to an explicit
authentication rejection. No wrapper/helper was built or submitted.
[Legacy image header](https://github.com/u-boot/u-boot/blob/v2019.04/include/image.h),
[ARM64 kernel handoff](https://github.com/u-boot/u-boot/blob/v2019.04/arch/arm/lib/bootm.c),
[bootm legacy-format requirements](https://docs.u-boot.org/en/latest/usage/cmd/bootm.html).

## Result classification

| Observation to retain verbatim | Classification |
| --- | --- |
| No matching USB/PnP device, access/driver error, stage timeout | Interface/transport unavailable; no command or authentication conclusion |
| Fastboot reports unknown command, or U-Boot help/console says command unavailable | Command absent in this firmware/configuration |
| Empty FAIL from `help <name>` on this observed USB path | Unclassified command result; known supported commands also fail this query |
| Explicit bad Image magic, invalid boot-image/FDT/initrd format or size | Format/placement rejection; retain which input was rejected |
| Explicit HAB/signature/authentication failure naming the tested object | Authentication rejection at the identified stage |
| `Starting kernel ...`, then serial kernel banner/experiment network report | Kernel entry/startup; require the expected custom kernel identity to claim success |
| USB disconnect, UUU `acmd` success, silence, or a later normal boot alone | Unclassified transition; does not prove either authentication acceptance or rejection |

Record firmware, Image, initrd and DTB hashes; exact command list and addresses;
USB path/VID/PID; all tool output; serial output if available; first kernel report;
and return to the original boot/services. An early RAM-only failure should be
recovered through the verified physical recovery/power procedure. Never run
`flash.uuu` as a diagnostic step.
