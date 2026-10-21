# GPU and VPU enablement plan

Prepared 21 October 2026 against the running stock Debian
`6.12.113+deb13-arm64`. **Status: GPU and VPU are working and tested**; see
[Progress](#progress) below for results, the failed first VPU attempt, its root
cause and the benchmark data. The sections up to there are the original plan.

## Evidence and intended result

- Debian enables `CONFIG_DRM_ETNAVIV=m`, `CONFIG_VIDEO_HANTRO=m`,
  `CONFIG_VIDEO_HANTRO_IMX8M=y`, `CONFIG_IMX8M_BLK_CTRL=y` and GPC power domains.
  Both matching modules are installed. No external firmware is declared by
  either module's firmware metadata; start with the stock drivers.
- `/gpu3d@38000000` is an enabled vendor node. The mainline-compatible
  `/soc@0/gpu@38000000` already exists with `vivante,gc`, but is disabled.
  Its named clocks are recognizable. One observed difference from upstream
  is GPU AHB assigned at 800 MHz rather than upstream's 400 MHz. Review clock
  parents/rates and power suppliers before enabling it.
- `/soc@0/vpu@38300000` uses `nxp,imx8mq-hantro`, vendor clock names and a
  single large register window beginning at 0x38300000. It is not the
  mainline G1/G2 topology.
  There is no separate VPU block-controller node in the current DT.
- The vendor's 960 MiB CMA reservation fails. Debian falls back to 64 MiB,
  with about 60 MiB free at inspection. Buffer allocation needs to be tested;
  this does not by itself justify reserving 960 MiB.

Success means headless hardware rendering through etnaviv/Mesa, plus real
hardware video decoding through Hantro's stateless V4L2 interface. Display
output, hardware video encoding and camera/MyriadX inference are separate
capabilities and are not implied by these results.

## 1. Prepare reproducible target-only DT changes

Use the existing launcher route and fresh bootstrap FDT. Extend its DT
adaptation pipeline while retaining upper RAM, thermal, USB-C, reserved
memory and all board wiring. Use libfdt or a compiler-backed transformation
for added nodes/properties; the fixed-byte thermal helper is not a general
DT editor. Any helper executed under the vendor kernel must be static or
Bookworm-compatible.

Resolve every referenced clock, interrupt and power provider by path and
specifier meaning, not copied numeric phandles from an unrelated DTB.
Compare against the exact Linux v6.12.113 DTS/bindings. Keep GPU and VPU as
separate selectable changes so a failed test can be isolated. Keep the
existing rescue entry and original DTB. Retain the previous working
launcher/config on p3 and the PC, using the current factory restore fallback.

## 2. GPU boot and rendering proof

Disable the duplicate vendor GPU node and enable the existing mainline node.
Verify address/interrupt, named clocks, assigned parents/rates, power-domain
provider and any optional operating-point/supply references. Use validated
fixed clock settings initially; do not combine this with PMIC, CPU DVFS or
global power-management changes.

Reboot and inspect UART, etnaviv identification, render-node creation,
interrupts, clocks and power-domain state. A driver symlink alone is not the
acceptance criterion. Install Debian's Mesa etnaviv userspace and a small
headless EGL/GLES test, verifying the package actually contains the needed
driver. Explicitly open the render node and record EGL vendor/renderer and
rendered output. Reject llvmpipe/softpipe or software fallback as a success.
No display connector is needed for this initial offscreen test.

Repeat a render workload, verify output, monitor CPU temperature and check
for MMU faults, GPU resets or hangs. Reboot persistence must retain the
working radios, network, eMMC and 4 GiB memory map.

## 3. VPU boot with the upstream topology

Disable the overlapping vendor VPU node, preserving unrelated reservations.
Introduce the exact mainline i.MX8MQ structure:

| Node | Resource / relationship |
|---|---|
| G1 `video-codec@38300000` | 0x10000 register window, SPI 7, G1 clock, block-controller G1 domain |
| G2 `video-codec@38310000` | 0x10000 register window, SPI 8, G2 clock, block-controller G2 domain |
| `blk-ctrl@38320000` | 0x100 window, `fsl,imx8mq-vpu-blk-ctrl`, G1/G2 clocks, bus/G1/G2 power-domain relationships |

Translate these interrupt specifiers through the existing GIC and use the
existing verified GPC VPU parent domain. Do not merely rename the vendor
compatible or point both codec engines directly at a legacy domain. Validate
parent cell widths, clock IDs, block-controller domain IDs and non-overlap.
Boot with both codec descriptions, then diagnose/test each engine separately.

Require Hantro probe and `/dev/media*` / `/dev/video*` nodes. Inspect with
`media-ctl` and `v4l2-ctl`, recording the actual codec and capture formats for
each engine. The v6.12.113 source advertises MPEG-2/VP8/H.264 decoding for G1
and HEVC/VP9 decoding for G2. Availability of each exact profile/bit depth is
subject to the registered formats and decode tests. The Debian setting
`CONFIG_VIDEO_HANTRO_HEVC_RFC` is disabled; establish what that affects before
claiming a compressed-output capability or proposing a kernel rebuild.

## 4. Decode proof and buffer sizing

Install Debian's V4L2 utilities and GStreamer's `v4l2codecs` plugin. Use its
stateless decoder elements, not an assumed stateful FFmpeg V4L2-M2M path.
Discover elements with `gst-inspect-1.0` on the actual device; they depend on
available kernel devices and formats.

Start with a short known 720p H.264 sample on G1, then 1080p and G2 HEVC/VP9
samples. Explicitly select hardware elements and verify frame counts and
decoded frame content against a software reference, allowing defined
conversion differences. Record caps, sample hashes, throughput, CPU use and
kernel logs. CPU use alone does not prove hardware decode.

Begin with the current CMA allocation for the small test. If allocation or
queue sizing fails, replace the failed vendor CMA declaration with an
explicit, measured DMA-addressable pool, initially considering 128–256 MiB.
Check its address range, RPMsg/no-map reservations, initrd/Image placement and
actual allocation success. Avoid an unmeasured 960 MiB reservation. Repeat
the failed case only after changing the relevant condition.

Once decode works, test DMA-BUF sharing with GPU/userspace where supported;
this is a follow-up optimization, not a prerequisite for separate proofs.

## 5. Persistence, documentation and stop points

Combine only demonstrated changes, boot the normal rootfs and repeat both
workloads. Record matching kernel/Mesa/GStreamer versions, DT edits,
source/binary hashes, sample hashes, settings, measured results and rollback
in `debian13-reproduction.md`. Test a subsequent cold boot. Full deployment
still requires the existing three-cold-boot and kernel-update/rollback gates.

If GPU fails before a render node exists, investigate its probe, clocks,
power/reset and kexec handover. If it registers but renders incorrectly,
separate Mesa capability/version issues from kernel faults. If VPU probes
but fails workloads, distinguish stateless userspace, supported profiles,
buffer formats and CMA from clocks/power faults. Build a custom Debian kernel
only when a specific required missing feature or driver defect is established.

## Progress

### GPU: verified rendering on hardware (21 October 2026, boot `95a1e486-…`)

The launcher's `percept-fdt-media gpu` step (`media=gpu`) disables the vendor
`/gpu3d@38000000` and enables the mainline `/soc@0/gpu@38000000`
(`vivante,gc`, GPU AHB 400 MHz). On the running 6.12.113 kernel:

- `etnaviv-gpu 38000000.gpu: model: GC7000, revision: 6214`; `[drm] Initialized
  etnaviv 1.4.0`; `/dev/dri/renderD128` and `card0`; IRQ 217 on the GPCv2.
- No MMU faults, hangs or resets in the kernel log. No deferred devices.
- Mesa 25.0.7 (`etnaviv_dri.so`): `eglinfo` on both the GBM and surfaceless
  platforms reports driver `etnaviv`, renderer **Vivante GC7000 rev 6214**,
  OpenGL ES 2.0 and compatibility 2.1. No llvmpipe/softpipe.
- `experiments/percept-gpu/gles-offscreen-test.c` opens `renderD128` through
  GBM, requires a "Vivante" renderer, draws a three-colour triangle into an FBO
  and checks pixels read back at three positions (clear colour, red corner,
  centroid). **200 frames, 0 bad, `RESULT: PASS`**, with no GL errors and a
  clean kernel log afterwards.

The GPU idles runtime-suspended with the `gpu` power domain off between jobs.
This test was short (about 2 s); sustained load and temperature are still to
be measured.

On the question of whether the "missing" 4th GB went to the GPU under the
vendor kernel: it did not. The vendor `gpu3d` node's `reg` lists
`phys_baseaddr` = `0x40000000` + 3 GiB (lower 3 GiB only) and a 256 MiB
`contiguous_mem` pool with base 0; the stock kernel's CMA was 320 MiB at
`0xe5800000`. Nothing referenced `0x100000000`.

### VPU: first boot hung, fixed, and verified (21 October 2026)

**First attempt (`media=gpu-vpu`, helper v1): hard reset.** The launcher, helper,
DT adaptation and kexec all worked (`media_dtb gpu-vpu`, `capture_end status_0`),
and 6.12 booted to userspace (GPU, SSH, Wi-Fi, Bluetooth up), then the SoC
**reset silently at about 14.4 s** with no oops or panic, and no `hantro` line
in the log. It repeated on all three launcher attempts; the failcount reached 3
and the board dropped into rescue, as designed. Each failure also cost the
firmware's OS-B watchdog detour, about 4 minutes per attempt.

**Root cause: the vendor VPU power domain has no clocks.** Mainline's
`pgc_vpu: power-domain@6` carries `clocks = <VPU_DEC_ROOT, VPU_G1_ROOT,
VPU_G2_ROOT>` and `assigned-clocks/-parents/-rates` for G1, G2, VPU_BUS and
`VPU_PLL_BYPASS`. The vendor node (checked in the pristine `pe100.dtb`) has only
`#power-domain-cells`, `reg` and `phandle`; the vendor *GPU* domain, `@5`, does
have `clocks`, which is why the GPU came up and the VPU did not. In
`gpcv2.c`'s power-up the driver enables `domain->clks` so reset can propagate
into G1/G2, and the VPU domain has `keep_clocks = true`. With none listed the
first hantro register access hangs the bus. Helper v1 validated only the domain's
`reg` and `#power-domain-cells`, and had put an approximation of the clocks on
the block controller instead.

**Fix (helper v2, `experiments/percept-media/adapt-fdt.c`):** put exactly
mainline's values on the domain node: clocks 223/229/230; assigned-clocks
G1 (120), G2 (121), VPU_BUS (106), VPU_PLL_BYPASS (21); parents VPU_PLL_OUT (22),
VPU_PLL_OUT, SYS1_PLL_800M (78), VPU_PLL (20); rates 600/300/800 MHz/0. G2 is
300 MHz upstream (v1 carried the vendor's 600). The block controller no longer
has its own clock assignments. Decompiled and diffed against the `gpu`-only
output, the change is exactly the three new nodes, the domain properties and the
vendor VPU `status = "disabled"`.

- Helper v2: static musl, built on the board from the current source, retained
  at `sources/firmware-audit/gpu-vpu-20261021/percept-fdt-media.v2`
  (SHA-256 `d0fd4a36cac93f673ba75a519218e1c41a9034d0c0a730ed5be9a8207d7d1003`).
  Its `gpu` output remains byte-identical to the earlier helper's.
- Launcher `8ac00fcf2a985f75bb52bddae45466e4ef45b8b6f4dec99f9ed4a5f7bb8c5dca`
  (5,045,630 bytes): exactly one of 63 members differs, `bin/percept-fdt-media`.
- Staged with `percept_tries=1` so a repeat failure would reach rescue after one
  bad boot instead of three. It booted: Hantro registered at 14.2 s and 14.3 s,
  and the board stayed up.

**Probe result** (boot `926ca7b0-…`):

| Engine | Node | Compressed input | Decoded output |
|---|---|---|---|
| G1 `38300000.video-codec` | `/dev/video1`, `/dev/media1` | MPEG-2, VP8, H.264 (stateless slice) | NV12, YUYV |
| G2 `38310000.video-codec` | `/dev/video0`, `/dev/media0` | HEVC, VP9 | NV12, VT12 (tiled) |

This matches the v6.12.113 source exactly. GStreamer 1.26.2 registers
`v4l2slh264dec`, `v4l2slh265dec`, `v4l2slmpeg2dec`, `v4l2slvp8dec` and
`v4l2slvp9dec`. `experiments/percept-hardware/verify-boot.sh --vpu` passes all 17
checks: kernel, 4 GiB, eth0, Wi-Fi, Bluetooth, thermal, USB-C, camera, GPU,
no kernel faults, no unexpected failed units, Hantro, video and media nodes.

### Decode proof (`experiments/percept-hardware/vpu-decode-test.sh`)

For each codec the script generates a deterministic sample with a software
encoder, decodes it with ffmpeg (reference) and with GStreamer's stateless V4L2
decoder, and compares the raw planar output. It also requires the engine's own
interrupt line (`38300000.video-codec` or `38310000.video-codec` in
`/proc/interrupts`) to advance, because high CPU use or a non-empty file proves
nothing. 720p ×90 frames and 1080p ×60 frames:

| Codec (engine) | 720p | 1080p | Engine interrupts |
|---|---|---|---|
| H.264 (G1) | bit-identical | bit-identical | 1 per frame |
| VP8 (G1) | bit-identical | bit-identical | 1 per frame |
| HEVC (G2) | bit-identical | bit-identical | 1 per frame |
| VP9 (G2) | bit-identical | bit-identical | 1 per frame (+5 / +3) |
| MPEG-2 (G1) | PSNR 70.9 dB | PSNR 72.7 dB | 1 per frame |

MPEG-2 differs by at most ±1 level, which is within the IDCT tolerance the
standard allows (IEEE 1180); the script accepts it at ≥60 dB for MPEG-2 only.

Two pipeline pitfalls found on the way (not driver faults):

1. **G1 negotiates YUY2 (4:2:2) by default.** `videoconvert` then down-samples
   chroma to NV12, giving a uniform ~44.6 dB PSNR across all G1 codecs and a
   false "mismatch". Forcing `video/x-raw,format=NV12` out of the decoder fixes
   it; the first (YUY2) comparison has been superseded.
2. Raw NV12 buffers carry padding and, for H.264, per-macroblock motion-vector
   data after the picture (1,612,800 bytes per 720p frame instead of 1,382,400),
   so `filesink` output of the native buffer is not tight. The test re-packs to
   I420 first, which is lossless.

### Throughput and CMA sizing (`vpu-bench.sh`, whole-system CPU from `/proc/stat`)

720p, 300 frames, to a `fakesink` with `sync=false`, on an idle board:

| Codec (engine) | Hardware | CPU | Software, 4 threads | CPU |
|---|---|---|---|---|
| H.264 (G1) | 275 fps | 0.26 s | 123 fps | 7.0 s |
| VP8 (G1) | 326 fps | 0.24 s | 138 fps | 4.9 s |
| HEVC (G2) | 366 fps | 0.28 s | 106 fps | 8.3 s |
| VP9 (G2) | 353 fps | 0.37 s | 109 fps | 6.7 s |

An earlier version of this benchmark used `/usr/bin/time`, which is not
installed, and printed absurd ~88,000 fps figures. Those were discarded.

At **1080p** the first numbers looked wrong: H.264 41 fps using 4.5 CPU-s, VP8
34 fps, VP9 30 fps, and **HEVC 3.6 fps using 42.5 CPU-s**. The kernel log showed
`cma: __cma_alloc: reserved: alloc failed, req-size: 887 pages, ret: -12` with
916 of 16,384 pages free: the 64 MiB fallback pool (the vendor's 960 MiB request
cannot be placed) was exhausted. I attributed the slowness to that and added
the switch `cma=256M`. That removed the allocation failures (`CmaTotal`
262,144 kB, none logged) **but did not change the throughput**, so CMA exhaustion
was not the bottleneck; 256 MiB remains reasonable headroom for 1080p decode.

The real cause, found by testing a macroblock-aligned **1920×1088** stream:
1080 is not a multiple of 16, the decoder's buffer is 1088 lines, and my
`fakesink` cannot accept a crop meta, so GStreamer copied every frame with the
CPU, reading an uncached DMA mapping at roughly 100 MB/s. Without the crop:

| Codec (engine) | Hardware 1920×1088 | CPU | Software | CPU |
|---|---|---|---|---|
| H.264 (G1) | 128 fps | 0.22 s | 116 fps | 7.1 s |
| VP8 (G1) | 155 fps | 0.19 s | 86 fps | 4.5 s |
| HEVC (G2) | 169 fps | 0.26 s | 50 fps | 9.1 s |
| VP9 (G2) | 188 fps | 0.29 s | 61 fps | 6.6 s |

So the engines are healthy at 1080p-class resolution; a real sink that takes a
crop meta (KMS, Wayland) avoids the copy. This is synthetic `testsrc2` content;
real streams vary in complexity. Temperature stayed at 35–36 °C throughout.
The boot cmdline now includes `cma=256M` (launcher config only, no kernel change).

### GPU soak

`gles-offscreen-test` in a loop for four minutes: 26 runs, 104,000 frames, 0
failures, an identical pixel checksum (`fb367aed…`) on every run, 104,000 GPU
interrupts (one per frame), and no kernel messages. This is a stability and
correctness soak with a light workload; temperature stayed at 35 °C, so it says
nothing about thermal behaviour under heavy load.

### Boot confirmation made faster

`percept-boot-ok.service` waited for `network-online.target`, which only
completes at 2 min 5.9 s because `systemd-networkd-wait-online` times out on the
unused FEC port, and then slept another minute: counters were reset ~3.5 minutes
after boot, and a reboot before that would (correctly) land in rescue. It now
requires only `sshd` listening (up to 90 s) plus a 15 s settle, so confirmation
comes about a minute after boot. It deliberately does not require an IP address,
so a headless board with the LAN unplugged does not drift into rescue.

### Reboot persistence (3 warm reboots, final configuration)

`experiments/percept-hardware/reboot-soak.sh 3 --vpu` reboots the board three
times and runs `verify-boot.sh --vpu` (17 checks) after each: **3/3 cycles, every
check passed**. SSH came up 112 s after each reboot request and the launcher's
boot confirmation reset `failcount` and `percept_tries` at 121 s (it was ~3.5
minutes before the `percept-boot-ok` change). Configuration: `media=gpu-vpu`,
`cma=256M`, `upper_ram=1`, `thermal_fix=1`, USB-C DTB. These were **warm**
reboots; the three power-disconnected cold boots required by the acceptance
gate still need a person at the power connector.

### CPU clock (checked, left alone)

`arm_a53_core` runs at 1.3 GHz, the nominal rate firmware sets, so the CPUs are
not slow. `cpufreq` is blacklisted and there is no cpufreq sysfs. Enabling it
would only add power saving at 800 MHz and 1 GHz; the vendor OPP table's 1.5 GHz
point needs PMIC voltage control (the BD71837 driver and its DT remain
unqualified and blacklisted). Not worth the risk.

### Also fixed: `systemd-networkd-wait-online`

The FEC port (`eth1`) is not wired on this board, so waiting for every link
failed after 2 minutes on every boot (the only failed unit, a 2 minute
`network-online.target`, and a PHY warning from the FEC). A drop-in
(`experiments/percept-trixie/wait-online-override.conf`, now installed by
`stage-b.sh`) waits only for `eth0`; the unit starts in 0.14 s and is `active`.
Evidence that nothing is wired behind that port: the FEC's MDIO bus reads PHY ID
`0x00000000` at address 0 (a real PHY returns a non-zero OUI) and `eth1` never has
carrier. Disabling the FEC node in the DT would also remove its PHY warning at
boot, but that is cosmetic, so the node was left enabled rather than spend
another launcher rebuild and reboot on it.

Radios re-checked on the final configuration: a Wi-Fi scan returned 9 networks
(interface returned to down, no credentials configured) and a 6 s Bluetooth scan
found 2 devices with `hci0` up.

### Rollback

Remove `media=gpu-vpu` (or set `media=gpu`) in `/boot/efi/percept/launcher.conf`,
remove ` cma=256M` from its `cmdline=`, and reset `failcount` to 0 and
`percept_tries` to 4. Earlier launchers and configs are in
`/root/percept-gpu-vpu/backup-*` on the board; the prior launcher is also at
`sources/firmware-audit/gpu-vpu-20261021/installed-launcher.cpio.gz`. The
`launcher-gpu-vpu.cpio.gz` there carries helper v1, which hangs the board: do
not reinstall it.

## Primary sources and retained inputs

- [Exact i.MX8MQ DTS](https://github.com/gregkh/linux/blob/v6.12.113/arch/arm64/boot/dts/freescale/imx8mq.dtsi)
- [Vivante binding](https://github.com/gregkh/linux/blob/v6.12.113/Documentation/devicetree/bindings/gpu/vivante%2Cgc.yaml)
- [VPU binding](https://github.com/gregkh/linux/blob/v6.12.113/Documentation/devicetree/bindings/media/nxp%2Cimx8mq-vpu.yaml)
- [i.MX8M Hantro implementation](https://github.com/gregkh/linux/blob/v6.12.113/drivers/media/platform/verisilicon/imx8m_vpu_hw.c)
- [i.MX8M block controller](https://github.com/gregkh/linux/blob/v6.12.113/drivers/pmdomain/imx/imx8m-blk-ctrl.c)
- [GStreamer stateless V4L2 codecs](https://gstreamer.freedesktop.org/documentation/v4l2codecs/index.html)

Exact source snapshots downloaded for this plan are in
`sources/firmware-audit/gpu-vpu-plan-20261021/`; the existing upstream DTS is
under `sources/firmware-audit/debian-kernel/dtb/upstream/`.
