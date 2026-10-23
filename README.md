# Debian on Azure Percept DK

Give Microsoft's discontinued Azure Percept DK a second life as a general-purpose
headless ARM64 Linux server running Debian Bookworm.

Microsoft [retired the Azure Percept](https://learn.microsoft.com/en-us/azure/azure-percept/retirement-of-azure-percept-dk)
public preview in March 2023 and shut down all cloud services, turning these boards
into e-waste. The hardware is still perfectly capable — it's an NXP i.MX8MQ with
quad Cortex-A53 cores, 4 GB RAM, 16 GB eMMC, Gigabit Ethernet, dual-band Wi-Fi,
and Bluetooth 5.0. This project puts it back to work.

## The Problem

The Percept DK has **HAB (High Assurance Boot) fuses permanently blown**. The
entire boot chain is cryptographically locked to Microsoft's signing keys:

```
eMMC boot1 (HAB-signed) → SPL → U-Boot → UEFI (RSA-4096) → shim (MS-signed)
→ GRUB (shim_lock) → vmlinuz (MS-signed)
```

**You cannot replace the kernel.** You cannot replace the bootloader. You cannot
enroll MOK keys (UEFI re-provisions `SecureBootFixedKeysMain` every boot). Every
bypass was tested and confirmed dead — booti, unsigned shim, PK deletion, custom
GRUB with `check_signatures=no`, all of it.

**But the kernel doesn't verify the rootfs.** And GRUB's config file isn't signed.

## The Solution

This project:

1. Takes the original Microsoft firmware image (preserving the entire signed boot chain)
2. Replaces the GRUB config to point at a Debian root filesystem
3. Replaces the rootfs partition with Debian Bookworm arm64
4. Keeps the original MS-signed kernel and all 647 original kernel modules
5. Adds the cgroup v1 boot parameter required for Docker to function

The result is a fully working Debian 12 system with SSH, Wi-Fi, Bluetooth, Docker,
and all the hardware working — flashable to any Percept DK in about 5 minutes via USB.

## Hardware Specifications

| Component | Details |
|-----------|---------|
| **SoC** | NXP i.MX8MQ (quad Cortex-A53 @ 1.5 GHz, arm64) |
| **RAM** | 4 GB LPDDR4 — **only 3 GB usable** ([see why](#only-3-of-4-gb-ram-is-usable)) |
| **Storage** | 16 GB eMMC (14.5 GB usable after partitioning) |
| **Ethernet** | Gigabit (Intel igb via PCIe) |
| **Wi-Fi** | Realtek RTL8822CE — 802.11ac dual-band (2.4 + 5 GHz) |
| **Bluetooth** | RTL8822CE — BT 5.0 (HCI via btusb + btrtl) |
| **USB** | 1× USB 3.0 Type-A, 1× USB-C (data/flashing only) |
| **Serial** | 1.8V UART on ttymxc0 @ 115200 — ⚠️ **3.3V adapters will damage the SoC** |
| **Power** | 19V DC barrel jack (external PSU), ~5W typical |

## What Works

| Feature | Status | Notes |
|---------|--------|-------|
| Gigabit Ethernet | ✅ | Intel igb, works out of the box |
| Wi-Fi | ✅ | 88x2ce driver, auto-loads, 2.4+5 GHz |
| Bluetooth | ✅ | btusb + btrtl, BT 5.0, HCI works |
| USB 3.0 | ✅ | Full speed |
| SD card slot | ✅ | SDR104 mode |
| SSH | ✅ | OpenSSH, enabled by default |
| Docker | ✅ | Requires cgroup v1 mode (handled automatically) |
| Serial console | ✅ | 1.8V UART only — see warning above |
| Eye SoM camera | ❌ | MIPI routed to Myriad X only — [dead end](#the-eye-som-camera-is-a-dead-end) |
| GPU acceleration | ❌ | Vivante GC7000L, no usable driver in kernel 5.4 |
| Custom kernel | ❌ | HAB CLOSED — only the MS-signed kernel boots |
| Wi-Fi monitor mode | ❌ | 88x2ce driver doesn't support it |

## Prerequisites

### Source Firmware

You need the original Microsoft recovery image. As of 2025 it's still hosted by
Microsoft:

**[Download Azure-Percept-DK-1.0.20220620.1126 (ZIP, ~3.4 GB)](https://download.microsoft.com/download/4/7/a/47af6fc2-d9a0-4e66-822b-ad36700fefff/Azure-Percept-DK-1.0.20220620.1126-public_preview_1.0.zip)**

Extract it. You'll need `Azure-Percept-DK.raw` (the 8 GB firmware image) and
`flash.bin` (the HAB-signed bootloader, renamed to `fast-hab-fw.raw` in the
scripts).

### Build Host (WSL2 or native Linux)

```bash
sudo apt install debootstrap qemu-user-static zstd
```

### Flash Host (Windows)

- **UUU** (Universal Update Utility) v1.4+ — [download from NXP mfgtools](https://github.com/nxp-imx/mfgtools/releases)
- USB-C cable from PC to the Percept DK's USB-C port (the one near the power jack)

## Quick Start

### 1. Configure

```bash
cd production/
nano config.sh    # Set hostname and Wi-Fi SSID (passwords are asked for during the build)
```

### 2. Extract source files

Place these in `production/sources/`:

| File | Source | Size |
|------|--------|------|
| `Azure-Percept-DK.raw` | From the MS recovery ZIP | 8.0 GB |
| `fast-hab-fw.raw` | `flash.bin` from the MS recovery ZIP (rename it) | 2.6 MB |
| `vmlinuz-mariner` | Extract from partition 3 of the `.raw` at `/boot/vmlinuz` | 35 MB |
| `ms-modules.tar.gz` | Tar up `/lib/modules/5.4.3-26.cm1/` from partition 3 | 8.2 MB |
| `88x2ce.ko` | Decompress `88x2ce.ko.xz` from `ms-modules` | 6.0 MB |
| `rtl8822cu_fw` | `/lib/firmware/rtl_bt/rtl8822cu_fw.bin` on partition 3 | 52 KB |
| `rtl8822cu_config` | `/lib/firmware/rtl_bt/rtl8822cu_config.bin` on partition 3 | 6 B |

Or extract the recovery ZIP into `sources/ms-image/` and let the helper script do it:

```bash
sudo bash copy_sources.sh        # or: sudo bash copy_sources.sh path/to/Azure-Percept-DK.raw
```

To extract files from the raw image by hand:
```bash
# Mount partition 3 (rootfs) of the MS image
LOOPDEV=$(sudo losetup --find --show --partscan Azure-Percept-DK.raw)
sudo mkdir -p /mnt/percept
sudo mount ${LOOPDEV}p3 /mnt/percept

# Copy what you need
cp /mnt/percept/boot/vmlinuz sources/vmlinuz-mariner
tar czf sources/ms-modules.tar.gz -C /mnt/percept/lib/modules 5.4.3-26.cm1
xz -d -k /mnt/percept/lib/modules/5.4.3-26.cm1/kernel/drivers/net/wireless/88x2ce.ko.xz
cp /mnt/percept/lib/modules/5.4.3-26.cm1/kernel/drivers/net/wireless/88x2ce.ko sources/
cp /mnt/percept/lib/firmware/rtl_bt/rtl8822cu_fw.bin sources/rtl8822cu_fw
cp /mnt/percept/lib/firmware/rtl_bt/rtl8822cu_config.bin sources/rtl8822cu_config

sudo umount /mnt/percept
sudo losetup -d $LOOPDEV
```

### 3. Build Debian rootfs

```bash
sudo bash 00_build_rootfs.sh     # asks for the root and percept passwords, then ~5 minutes;
                                 # outputs sources/debian-rootfs.tar.zst
```

### 4. Build flash image

```bash
sudo bash 01_build_image.sh      # ~2 minutes, outputs output/debian-percept-dk.raw
```

### 5. Flash the device

Connect the host to the board's USB recovery/data port with a data-capable cable.
Start UUU on the host and wait for its USB-device message:

```powershell
# Windows PowerShell:
cd E:\percept\production
.\uuu.exe flash.uuu
```
```bash
# Or from WSL:
cd /mnt/e/percept/production
uuu flash.uuu
```

While UUU waits, request **USB recovery mode** through SSH on the running board:

```bash
sudo flagutil -wBfRequestUsbFlash -v1
sync
sudo systemctl reboot
```

Microsoft documents the vendor flag followed by a reboot in this
[Percept recovery answer](https://learn.microsoft.com/en-us/answers/questions/365138/reseting-the-percept-to-initial-state).
Use an orderly reboot so services and filesystems shut down. If `flagutil` is
missing on Debian, the original recovery utility was verified in this workspace
at `/root/percept-kexec-work/flagutil`; use that full path instead. It was
extracted from the original Microsoft image, not installed as a Debian package.
The flag requests recoverable USB boot; it does not program fuses.

If SSH is unavailable, use the official procedure for the board's **internal DIP
switches**, following its exact board revision documentation. No switch positions
are established here. The earlier claim of an external recovery button was
unverified and has been removed. Setting the flag and rebooting still requires
confirmation that the host actually enumerates the recovery USB interface.

Takes about 5 minutes. Wait for "Done".

### 6. First boot

1. Unplug USB cable, power cycle the board
2. Wait 60 seconds
3. SSH in:

```bash
ssh root@<dhcp-address>        # Check your router for the new device
# Password: the one you chose during 00_build_rootfs.sh
```

### 7. Post-flash setup

```bash
bash /root/post_flash.sh
```

This expands the rootfs from 2 GB to fill all 14.5 GB of eMMC, creates a 512 MB
swap file, verifies Wi-Fi and Docker, and shows system status.

### 8. Flash more boards

Repeat steps 5–7. The image in `output/debian-percept-dk.raw` is reusable.

## Directory Structure

```
production/
├── config.sh                    # ← Edit this: hostname, network, Wi-Fi
├── 00_build_rootfs.sh           # Build Debian arm64 rootfs tarball
├── 01_build_image.sh            # Patch MS image with Debian rootfs
├── flash.uuu                    # UUU flash script
├── flash.bat                    # Windows double-click flash helper
├── post_flash.sh                # On-device first-boot setup
├── copy_sources.sh              # Extracts sources/ files from the MS image
├── README.md                    # This file
├── sources/                     # Source artifacts (not in git — see above)
│   ├── Azure-Percept-DK.raw
│   ├── fast-hab-fw.raw
│   ├── vmlinuz-mariner
│   ├── ms-modules.tar.gz
│   ├── 88x2ce.ko
│   ├── rtl8822cu_fw
│   ├── rtl8822cu_config
│   └── debian-rootfs.tar.zst   # Built by 00_build_rootfs.sh
└── output/
    └── debian-percept-dk.raw   # Built by 01_build_image.sh
```

## Known Gotchas

These are hard-won discoveries. Each one cost hours of debugging.

### Only 3 of 4 GB RAM Is Usable

The board has 4 GB LPDDR4, but Linux only sees ~2.7 GB. Two compounding issues:

1. **Microsoft's device tree (`pe100.dtb`) only declares 3 GB.** The i.MX8MQ maps
   4 GB of RAM across two physical regions: 3 GB at `0x40000000`–`0xFFFFFFFF` and
   1 GB at `0x100000000`–`0x13FFFFFFF`. Microsoft's DTB only declares the lower
   region. The NXP reference DTB for the same SoC declares both:

   ```dts
   memory@40000000 {
       reg = <0x00000000 0x40000000 0x00000000 0xc0000000>,  /* 3 GB */
             <0x00000001 0x00000000 0x00000000 0x40000000>;  /* 1 GB */
   };
   ```

2. **Patching the DTB doesn't help.** We tried adding the upper region — the
   kernel silently ignores it. The MS kernel was compiled with only
   `CONFIG_ZONE_DMA32=y` and no `ZONE_NORMAL`, so it physically cannot address
   memory above `0xFFFFFFFF`. This is a compile-time limitation that we cannot
   change because the kernel is signed and locked by HAB.

3. **320 MB is reserved for CMA** (Contiguous Memory Allocator) on top of that,
   leaving ~2.7 GB actually usable.

### Docker Requires cgroup v1

The kernel lacks `CONFIG_BPF_SYSCALL`. Under cgroup v2 (Debian Bookworm's default),
the device controller uses BPF programs to manage container device access. Without
the BPF syscall, every container fails immediately:

```
bpf_prog_query(BPF_CGROUP_DEVICE) failed: function not implemented
```

**Fix:** Force cgroup v1 by adding this to the kernel command line:
```
systemd.unified_cgroup_hierarchy=0
```

This is already baked into the GRUB config written by `01_build_image.sh`. Under
cgroup v1, the device controller uses legacy whitelist files instead of BPF.

Things that **don't work** as alternatives (we tried them all):
- `docker run --privileged` — doesn't help, the BPF call happens before the container starts
- `crun` runtime (including a custom `--disable-bpf` build) — `containerd-shim-runc-v2` makes its own BPF calls independently of the OCI runtime
- Swapping the Docker daemon to use `crun-nobpf` via `daemon.json` — the shim layer sits above the runtime and still calls BPF
- Podman — bypasses containerd but introduces other issues on this kernel

The one-line GRUB parameter is the clean fix.

### iptables-legacy Is Required

The kernel lacks `CONFIG_NF_TABLES`. Docker's default iptables backend won't work.
The build scripts automatically switch to `iptables-legacy` via
`update-alternatives`. If you see Docker failing to create networks, run:

```bash
update-alternatives --set iptables /usr/sbin/iptables-legacy
update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy
systemctl restart docker
```

### Kernel Modules Must Be Original

The kernel uses `RANDSTRUCT_PLUGIN`, which randomizes struct layouts at compile
time using a build seed. Ordinary external module builds require matching layouts
and a seed hash in vermagic. The 647 modules from the original MS image work;
arbitrary replacements can fail loading or corrupt memory.

`MODULE_SIG_FORCE` is **not** set, so unsigned modules do load (with kernel taint).
Matching vermagic alone does not establish struct compatibility. A narrow
experiment on **2026-10-20** successfully loaded a custom hello module and patched
`kexec-mod` modules without the seed, using descriptor positions recovered from
the stock binaries. The patched modules staged the stock kernel and unloaded;
one controlled execution attempt returned through the normal boot path without
the test marker, so a successful kernel jump remains **unconfirmed**. See
[`docs/kexec-mod-experiment.md`](docs/kexec-mod-experiment.md) for evidence and limits.

### The Eye SoM Camera Is a Dead End

The Azure Percept Vision (Eye SoM) has its MIPI CSI-2 lanes wired directly to the
Intel Myriad X VPU, **not** to the i.MX8MQ's ISI (Image Sensing Interface). The
Myriad X runs proprietary Microsoft firmware to process camera frames and run AI
models. There is no way to access the camera sensor from Linux without Microsoft's
closed-source stack, which was part of the cloud service that was shut down. The
camera hardware is permanently unusable.

### Serial Console Is 1.8V

The i.MX8MQ UART operates at **1.8V logic levels**. Connecting a standard 3.3V
FTDI or CH340 serial adapter **will damage the SoC**. You need a 1.8V-capable
USB-UART adapter or a voltage level shifter.

## Partition Layout

| # | Original Name | Original Size | After Flash | Mount |
|---|---------------|---------------|-------------|-------|
| p1 | EFI-A | 11 MB | 11 MB (unchanged) | `/boot/efi` |
| p2 | EFI-B | 11 MB | 11 MB (unchanged) | *(unused backup)* |
| p3 | rootfs-A | 2 GB | **14.5 GB** (expanded) | `/` |
| p4 | rootfs-B | 2 GB | *(deleted)* | — |
| p5 | data | ~4 GB | *(deleted)* | — |

`post_flash.sh` deletes p4 and p5, then grows p3 to fill all available space.

## Secure Boot Deep Dive

For anyone trying to understand or bypass the boot chain — here's everything we
tested so that you don't have to.

### Boot Chain

```
┌─────────────────────────────────────────────────────────────────┐
│ eMMC boot1 partition                                            │
│   SPL (HAB-signed, fuses blown to CLOSED)                       │
│   └─ U-Boot 2019.04 (verified by SPL)                          │
│       └─ uefi.fit (sha256 + RSA-4096)                          │
│           └─ UEFI BdsDxe                                       │
│               └─ bootaa64.efi (Microsoft-signed shim)           │
│                   └─ grubaa64.efi (GRUB 2.03, shim_lock on)    │
│                       ├─ grub.cfg ← NOT SIGNED (this is the    │
│                       │              exploit we use)             │
│                       └─ vmlinuz (MS-signed, verified by shim)  │
│                           └─ rootfs on /dev/mmcblk0p3           │
│                              (NOT verified by anything)          │
└─────────────────────────────────────────────────────────────────┘
```

### What We Tried (and Failed)

| Bypass Attempt | Result |
|----------------|--------|
| Boot NXP unsigned kernel via GRUB | ❌ shim_lock rejects it — not signed by MS |
| Replace `bootaa64.efi` with GRUB (skip shim) | ❌ UEFI Secure Boot rejects — not MS-signed |
| U-Boot `booti` command to bypass UEFI | ❌ HAB rejects — U-Boot is verified too |
| GRUB `check_signatures=no` | ❌ GRUB built with shim_lock, ignores this setting |
| Enroll MOK via `mokutil --import` | ❌ MokManager not present in this shim build |
| Write to MokList EFI variable directly | ❌ Variable is read-only at runtime |
| Delete PK to disable Secure Boot | ❌ `SecureBootFixedKeysMain` re-provisions all keys on every boot |
| Strip MS signature, re-sign kernel with own key | ❌ Custom key not in db, db can't be modified |
| Fastboot download kernel + `booti` | ❌ U-Boot verified boot chain rejects it |

### Why This Approach Works

**GRUB's configuration file is not signed or verified by anything in the chain.**

The shim verifies GRUB's EFI binary. GRUB verifies the kernel's PE signature via
shim_lock. But GRUB reads `grub.cfg` from the EFI partition as a plain text file
with no integrity check. By changing the `root=` parameter and the rootfs content,
we get a fully custom Debian userspace while the entire cryptographic boot chain
remains intact and happy.

### Public Exploit + Signed Update Tracking

This project now keeps a lightweight, date-stamped status of new public boot-chain
exploit research and official signed update checks:

- [`docs/boot-chain-status.md`](docs/boot-chain-status.md) — current verdict + findings matrix
- [`docs/boot-chain-watchlist.md`](docs/boot-chain-watchlist.md) — monthly re-check runbook

As of **2026-04-24**, there is still no confirmed practical public trust-chain break
path for Percept DK and no public official signed update path that enables kernel/
bootloader replacement or full 4 GB RAM use.

## Security Considerations

- There are no default passwords: `00_build_rootfs.sh` asks for them, and every board flashed from
  the image shares them. Change them per board with `passwd` if that matters to you
- SSH host keys and `/etc/machine-id` are generated on each board's first boot, so boards never
  share host keys or DHCP client IDs
- Root SSH is enabled for initial headless setup — disable after adding your SSH key:
  ```bash
  sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
  systemctl restart ssh
  ```
- The kernel (Mariner 5.4.3, dated June 2022) will **never receive security updates** — the HAB lock means no kernel replacement is possible
- Unattended upgrades are enabled for Debian userspace packages (libc, OpenSSH, etc.)
- `CONFIG_BPF_SYSCALL` is disabled — this actually reduces the kernel's BPF attack surface (unintentionally)

## Benchmarks

The table below is the historical Bookworm baseline. After the Debian 13 kernel
and CPU power changes, the board measured **2,852.86 CPU events/sec** and
**5,391.95 MiB/sec in the four-thread memory test** at 1.5 GHz, after reboot.
See [the paired 1.3/1.5 GHz results and exact settings](docs/cpu-benchmarks.md).

Measured on the device running Debian Bookworm with Docker and several containers:

| Metric | Result |
|--------|--------|
| CPU (sysbench, 4 threads) | ~2,455 events/sec |
| Memory bandwidth | ~4,423 MiB/sec |
| Idle RAM (bare Debian + SSH) | ~150 MB |
| Idle RAM (Docker + 8 containers) | ~580 MB |
| Power consumption | ~5W typical |

## Suggested Use Cases

This makes a decent low-power always-on homelab appliance:

- **Network monitoring** — LibreNMS, syslog collector, Uptime Kuma
- **Container host** — Docker with Portainer for lightweight services
- **DNS/ad blocking** — Pi-hole, AdGuard Home
- **Dashboard** — Homepage, Dashy, Heimdall
- **VPN endpoint** — WireGuard, Tailscale
- **Home automation** — Zigbee2MQTT (with USB adapter), MQTT broker
- **Reverse proxy** — Caddy, nginx proxy manager

**Not suitable for:**
- Anything requiring the camera (permanently unusable)
- Heavy compute or transcoding (4× A53 at 1.5 GHz is modest)
- Wi-Fi security testing (no monitor mode)
- Anything requiring kernel modifications

## Troubleshooting

### UUU doesn't detect the device
- Verify recovery USB enumeration after the vendor `BfRequestUsbFlash` request and reboot. If SSH is unavailable, follow the official internal DIP-switch recovery procedure for the board revision; do not guess switch positions.
- Try a different USB-C cable
- On Windows, you may need the NXP USB driver (usually auto-installs)

### SSH connection refused after flash
- Wait a full 60 seconds — first boot is slow
- Check your router's DHCP lease table for the new device
- If all else fails, use a 1.8V serial adapter on ttymxc0 at 115200 baud

### Wi-Fi not working
```bash
lsmod | grep 88x2ce         # Check if module is loaded
modprobe 88x2ce              # Load manually
dmesg | grep -i rtl          # Check for errors
ip link show wlan0           # Verify interface exists
```

### Docker containers fail to start
If you see `bpf_prog_query` errors, the cgroup v1 parameter is missing:
```bash
cat /proc/cmdline            # Should contain systemd.unified_cgroup_hierarchy=0
cat /sys/fs/cgroup/cgroup.controllers 2>/dev/null  # Should fail (means cgroup v1)
ls /sys/fs/cgroup/devices/   # Should exist (cgroup v1 device controller)
```

If missing, add `systemd.unified_cgroup_hierarchy=0` to the `linux` line in
`/boot/efi/boot/grub2/grub.cfg` and reboot.

### Docker network creation fails
```bash
update-alternatives --set iptables /usr/sbin/iptables-legacy
update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy
systemctl restart docker
```

## License

The scripts in this repository are provided as-is under the [MIT License](LICENSE).

The Microsoft firmware files (`Azure-Percept-DK.raw`, `flash.bin`, signed kernel,
kernel modules, device tree, Bluetooth firmware) are Microsoft's property and are
**not included** in this repository. Users must source them from the
[official Microsoft recovery image](https://download.microsoft.com/download/4/7/a/47af6fc2-d9a0-4e66-822b-ad36700fefff/Azure-Percept-DK-1.0.20220620.1126-public_preview_1.0.zip).

## Acknowledgments

- NXP [mfgtools/UUU](https://github.com/nxp-imx/mfgtools) — the USB flashing tool that makes this possible
- The Debian arm64 port
- Microsoft, for at least still hosting the recovery image after discontinuing the product
