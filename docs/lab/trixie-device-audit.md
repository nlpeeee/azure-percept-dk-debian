# Percept device and driver audit

> **Later update (21 October 2026):** the GPU (etnaviv) and VPU (Hantro G1/G2) now
> work and are tested, see [gpu-vpu-plan.md](gpu-vpu-plan.md); the Vision camera
> captures video, see [camera-vision.md](camera-vision.md); USB-C works, see
> [usb-c.md](usb-c.md). Items below that say otherwise are historical.


Update after boot `1bd35350-fbaa-4ec0-985e-ade1143f240d`: Debian firmware
packages repaired Wi-Fi/Bluetooth initialization; the target-only thermal DT
correction gives a working CPU sensor at 37°C. The separate USB-C DT fix now
binds `38100000.usb` and enumerates the Microsoft camera hubs, Azure Eye SoM
controller (`045e:066f`) and MyriadX (`03e7:2485`). Imaging/inference is not yet
tested. These results supersede the earlier missing-firmware, sensor, USB-C
and camera-enumeration observations below. See
[hardware support and live evidence](percept-hardware-support.md) and
[USB-C integration](usb-c.md).

21 October 2026; Debian `6.12.113+deb13-arm64`, boot
`a2897fef-892d-4743-8a9c-9f9b705aa72f`. This is an inventory/probe audit,
not a functional test of every connector, peripheral or crypto operation.
Device bindings were inspected without loading/rebinding drivers or changing
configuration. Raw evidence is in `sources/firmware-audit/devices-20261021/`.

## Detected and bound

| Device | Evidence and qualification |
|---|---|
| Four Cortex-A53 CPUs and 4 GiB RAM | CPUs `0-3` online, `MemTotal=4,008,364 KiB`. |
| eMMC | `sdhci-esdhc-imx`, 14.6 GiB device, boot areas and three partitions; ext4 root mounted rw. |
| SD card and controller | User inserted an LX32G 29.5 GiB SDHC card. It negotiated SDR104, bound to `mmcblk` through `sdhci-esdhc-imx`, and appeared as `/dev/mmcblk1` with FAT/ext4 partitions. A direct 16 MiB read succeeded without mounting/writing. |
| Intel I211 Ethernet | PCI `8086:1539`, `igb` bound, eth0 has DHCP address and 1 Gbit/s link; SSH operational. |
| USB host and hubs | `dwc3` at `38200000` and `xhci-hcd`; Genesys USB2/USB3 hubs `05e3:0610`/`05e3:0620` enumerated. A subsequently inserted SanDisk stick enumerated at 5 Gbit/s with `uas`, `sd_mod`, `/dev/sda` and a 57.3 GiB partition. Logs show it moved between both external USB-A ports. No storage writes were issued during this audit. |
| TPM 2.0 | `tpm_tis_spi` bound at spi0.0, device ID `0xfc`, `/dev/tpm0` and `/dev/tpmrm0` present. The earlier IMA "No TPM" log precedes this later probe. |
| SNVS RTC | `snvs_rtc`, rtc0 returns date/time. The separately described external RTC is not bound. |
| Hardware watchdog | `imx2_wdt`, active with 60-second timeout. |
| CAAM | Controller and all three job rings bound; crypto algorithms and `rng-caam` registered. Not every algorithm was functionally tested. |
| GPIO, LEDs and power key | Five GPIO controllers bound; status/fault/WLAN LED class devices and SNVS key input registered. |
| I2C/SPI, clocks, resets, GPC, OTP and mailbox | Relevant controller drivers bound. A DT-created client alone does not prove a physical peripheral responded. |
| SPDIF audio | ALSA card `imx-spdif` and capture/playback PCM nodes registered; playback/capture not tested. |

## Failures, missing support and intentional exclusions

| Device/function | Current result |
|---|---|
| RTL8822CE Wi-Fi | PCI device `10ec:c822` detected and modules loaded, but probe fails because `rtw88/rtw8822c_fw.bin` and `rtw8822c_wow_fw.bin` are missing. No wireless interface/PHY registered. |
| Bluetooth | USB `13d3:3548`, `btusb`/`btrtl` bound and hci0 exists; initialization fails without `rtl_bt/rtl8822cu_fw.bin`. A bound USB driver is not proof of usable Bluetooth. |
| Regulatory database | `regulatory.db` absent; `wireless-regdb` is not installed. |
| Thermal sensing | `qoriq_thermal` matches but fails sensor registration. No thermal/hwmon sensor exists. DT declares zero sensor cells but the thermal-zone reference includes an argument; binding correction is needed. |
| USB-C recovery/role controller | `38100000.usb` remains deferred: `dwc3: failed to get extcon`. The DT's IT5201 provider has no bound driver. The functioning USB-A path uses the other controller. |
| GPU | Vendor `gpu3d@38000000` node has no driver match. The mainline-compatible `vivante,gc` node exists but is disabled. `etnaviv` is available; no DRM render/card node is registered. Fixing this requires reviewing the full DT resources, not merely forcing a module. |
| VPU video acceleration | Vendor `nxp,imx8mq-hantro` node does not match the available `hantro_vpu` aliases (`nxp,imx8mq-vpu*`). No V4L2/media node registered. |
| SPI NOR flash | Duplicate DT children both use chip-select 0. The first instantiated child also returns all-zero JEDEC ID and remains unbound; `/proc/mtd` is empty. Presence of a usable flash chip is not established. |
| External ISL1208 RTC / AK audio codecs | DT clients exist, but the corresponding RTC/codec options are disabled in this Debian kernel. Physical population has not been verified. SNVS RTC and SPDIF remain available. |
| PMIC / CPU frequency / deep idle | PMIC and CPU-frequency modules are deliberately blacklisted, and `cpuidle.off=1` is part of the known working boot. These are intentional workarounds, not missing module files. |
| FEC eth1 | Driver bound, but no carrier and PHY auto-negotiation returns `-22`. This additional DT-described interface remains configuring, while the Intel port works. Its physical wiring/population is not established. |
| SDMA | Both drivers bound; missing external `imx/sdma/sdma-imx7d.bin`, with logged ROM-firmware fallback. Not a failed controller probe. |

`systemd-networkd-wait-online` is the only failed unit. Eth1 stays configuring,
consistent with the network-online delay. It does not prevent eth0 networking.
Generic syscon/simple-bus/timer nodes without a platform-driver symlink are not
automatically missing hardware drivers; some are handled through early or
parent initialization.

## Camera attachment

The user initially had only the main board connected, then attached the Vision
camera to the USB-C recovery port. No new USB device or connect event appeared.
That port's controller is deferred as described above, so this observation
cannot establish a camera-driver or camera-firmware failure.

The current test should use a working USB-A host port with a data-capable
USB-A–to–USB-C cable. Camera USB identity and runtime requirements must be
checked after it enumerates; this audit does not support calling the camera
permanently unusable. The Audio accessory was not attached.

After the user moved the camera to USB-A, a second inventory still showed no
new USB device and no connect event. USB2 external hub ports report power on
but no attachment; USB3 ports report power/Rx.Detect with no attachment.
Overcurrent counts are zero. Thus a data connection has not been established;
camera identity, driver support and firmware requirements remain unverified.
Evidence: `camera-usba.txt` and `usb-port-status.txt`.

USB-A is a diagnostic alternative, not the documented factory hookup.
[Microsoft's assembly guide](https://learn.microsoft.com/pt-br/azure/azure-percept/quickstart-percept-dk-unboxing)
uses USB-C to USB-C for Vision. USB-A compatibility/power sufficiency for this
camera has not been established. If a known data cable produces no USB event,
the native USB-C controller/role-provider path is the next integration target.

[ASUS's post-retirement SoM update guide](https://dlcdnets.asus.com/pub/ASUS/mb/Embedded_IPC/DKSC-101/Unsupported_SoM_Update_Azure_Percept_DK_Camera_and_Audio_SoMs.pdf?model=AS-101)
also documents camera identity `045e:066f`, a firmware revision check and a
matching updated Vision container. This is a genuine vendor-published research
lead against older claims of permanent unusability. We have not established
this camera's revision, tool compatibility or current download availability,
and no camera firmware update has been attempted.

## Next work

The initial read-only audit above was followed by installation of Debian's
Realtek firmware/regulatory packages and a target thermal DT correction.
Both radios initialize automatically and CPU temperature reads correctly after
the combined warm reboot. The independent USB-C fix now permits camera USB
enumeration. Package changes, source and tested hashes are in
`percept-hardware-support.md`; this inventory's original gaps are historical.

Camera imaging/inference, broader USB-C role/orientation behavior, GPU/VPU
and duplicate SPI descriptions remain separate integration work. PMIC and CPU
power-management workarounds remain in place.
