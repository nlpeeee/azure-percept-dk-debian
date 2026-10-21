# OS profiles and bringing your own kernel

A *profile* (`profiles/<id>/profile.toml`) says how to build one kind of system
and what a kernel must provide to boot on the Percept DK. You pick one with
`os.profile` in your board settings.

| Profile | Status | What it is |
|---|---|---|
| `debian-trixie` | **tested** | Debian 13 userland on Debian's own `linux-image-arm64` (6.12.113 verified), pinned to the 6.12 series so minor updates keep working |
| `byo-kernel` | experimental | The same userland with a kernel you supply (`os.kernel.source = "files"`) |
| `_template` | - | Starting point for a new profile |

"OS of your choice" means: a Debian-class userland on an arm64 kernel that meets
the contract below. Other distributions are possible by writing a profile, but
only `debian-trixie` has been booted on hardware.

## The kernel contract

For the launcher to `kexec` into a kernel and have it boot on this board:

- **Format:** arm64 `Image` (uncompressed is proven), plus an initramfs.
- **Built in or in the initramfs:** `ARCH_MXC`, `CLK_IMX8MQ`, `PINCTRL_IMX8MQ`,
  `IMX_GPCV2`, `PCI_IMX6_HOST`, `IGB`, `MMC_SDHCI_ESDHC_IMX`, `EXT4_FS`,
  `RESET_IMX7`, `I2C_IMX`, `SERIAL_IMX`, `NVMEM_IMX_OCOTP`.
- **Initramfs must load `imx2_wdt` first.** The stock kernel leaves the hardware
  watchdog running across `kexec`; if nothing feeds it the board resets.
- **Command line** (the profile's baseline; `os.kernel.cmdline_extra` is appended):
  `console=ttymxc0,115200 cpuidle.off=1 clk_ignore_unused pd_ignore_unused
  efi=noruntime net.ifnames=0 module_blacklist=rohm_bd718x7,bd718x7_regulator,imx_cpufreq_dt
  cma=256M`. `cpuidle.off=1` is required: the firmware does not implement the
  wake-up the idle driver expects.
- **Device tree:** the launcher hands your kernel the *vendor* device tree read
  live from the firmware. It needs small fixes for mainline 6.12 (the fixups
  below). They are selected from the kernel release at build time; they are
  wrong for the vendor 5.4 kernel, so profiles for that declare none.

| Fixup | What it changes | Applies to |
|---|---|---|
| `upper-ram` | Declares the fourth GiB of RAM | 6.12 |
| `thermal` | `#thermal-sensor-cells` 0 → 1 so the TMU registers | 6.12 |
| `media-gpu` / `media-gpu-vpu` | Enables the etnaviv GPU, optionally Hantro G1/G2, and gives the VPU power domain its clocks (without them the VPU hangs the bus) | 6.12 |
| `usbc-extcon` | Removes a dangling `extcon` reference so the USB-C port probes (applied to the DTB on the EFI partition) | 6.12 |

## Using your own kernel

```toml
[os]
profile = "byo-kernel"

[os.kernel]
source  = "files"
image   = "~/kernels/Image"
initrd  = "~/kernels/initrd.img"
modules = "~/kernels/modules.tar.gz"   # recommended
config  = "~/kernels/.config"          # lets percept check the contract before you flash
release = "6.12.20-custom"             # what `uname -r` will say
```

`percept build` (milestone M5) will refuse a kernel whose `.config` lacks a required symbol, whose
initramfs lacks the required modules, or that is not an arm64 `Image`. A release
outside the profile's validated list only warns. If a custom kernel fails to
boot, the launcher falls back to key-only SSH **rescue** mode after three failed
boots.

## Writing a profile

1. `cp -r profiles/_template profiles/<id>` and edit `profile.toml`.
2. `python percept profile check profiles/<id>`.
3. Build, flash, boot, then run `board-tests/verify-boot.sh --vpu` against it.
4. Open a PR with the verify output and the kernel release. Mark the profile
   `community` until someone else reproduces it.

Profile fields are validated by `src/percept/profiles.py`; unknown fixup names
and bad command-line characters are rejected.
