# Percept radios and thermal sensing on Debian 13

> **Later update (21 October 2026):** the GPU (etnaviv) and VPU (Hantro G1/G2) now
> work and are tested, see [gpu-vpu-plan.md](gpu-vpu-plan.md); the Vision camera
> captures video, see [camera-vision.md](camera-vision.md); USB-C works, see
> [usb-c.md](usb-c.md). Items below that say otherwise are historical.


Status, 21 October 2026: Wi-Fi and Bluetooth firmware is installed and tested.
The thermal correction and launcher were prepared, validated and installed
after the USB-C agent confirmed its separate change did not alter the launcher.
The combined warm reboot succeeded; the CPU thermal sensor reports 37°C.
This work does not change the USB-C DTB, GRUB configuration or controller.

## Wi-Fi and Bluetooth: standard Debian packages

The RTL8822CE PCI device (`10ec:c822`) uses Debian's existing
`rtw88_8822ce` / `rtw_8822ce` driver. The USB Bluetooth function (`13d3:3548`)
uses `btusb` and `btrtl`. Both earlier probe failures were missing firmware.
No old-kernel module, vendor driver build or kernel patch was needed.

On a new trixie installation, enable `non-free-firmware` in Debian's apt
sources, run `apt-get update`, then:

```sh
sh experiments/percept-hardware/install-radio-firmware.sh --reprobe
```

Omit `--reprobe` if preparing a filesystem before its next boot. The re-probe
reloads the Bluetooth driver and probes unbound RTL8822CE devices; it does
not touch the Intel Ethernet interface. It identifies PCI hardware by IDs,
not this board's PCI domain numbering or MAC address.

Installed versions on the first board:

| Package | Version | Purpose |
|---|---|---|
| firmware-realtek | 20250410-2 | Wi-Fi and Bluetooth firmware |
| wireless-regdb | 2026.05.30-1~deb13u1 | Regulatory database |
| iw | 6.9-1+b1 | Wi-Fi inspection/testing |
| bluez | 5.82-1.1 | Bluetooth management and daemon |

BlueZ's package installation enabled `bluetooth.service`. No Wi-Fi network,
credentials, pairing or country override was configured. The earlier “uk”
message meant “OK”; it was not a request to configure the UK regulatory domain.

Evidence from boot `a2897fef-892d-4743-8a9c-9f9b705aa72f`:

- `rtw_8822ce` bound and created `wlan0`. Normal firmware reports 9.9.15;
  WOW firmware reports 9.9.4. Bringing the interface up succeeded at 20 dBm.
- A Wi-Fi scan returned status 0 and nine BSS entries. SSIDs were not retained
  in the PC record. The interface was then returned to down state.
- Bluetooth loaded its firmware and configuration, reported firmware
  `0xaed66dcb`, and registered a powered controller supporting BR/EDR and LE.
- Association/data throughput, pairing and a Bluetooth peripheral session
  have not been tested. Automatic firmware loading on the subsequent boot
  `1bd35350-fbaa-4ec0-985e-ade1143f240d` passed for both radios.

Firmware SHA256 (symlinks followed):

```text
3deecb31210986d98cdbfb000391e08d602a6eee4ffc883969faa2b907ab03ba  rtw88/rtw8822c_fw.bin
6717fc6ff426a74571ac4f04cd9698fb2f356012c05c58aa64cf21ceb6b958a2  rtw88/rtw8822c_wow_fw.bin
660a105e2f6ace3831260003d321b50d9cb259768b0016eb7fa5750c1f90817b  rtl_bt/rtl8822cu_fw.bin
6c28a3f07c6a30ed208c4b64862a23f02b7d93543ea980edd24df16bab45095f  rtl_bt/rtl8822cu_config.bin
2fb33ca0074db573e05ef7dd50bb45b63c0ff98b7e852e1105ebad536fae8e6b  regulatory.db
```

The two firmware/database `.deb` files are archived under
`sources/firmware-audit/hardware-support-20261021/packages/`. For offline
reproduction, install those with `apt-get install /path/to/package.deb`;
BlueZ/iw and their dependencies still need an apt repository or local cache.
Keep each board's own hardware addresses and EEPROM data.

## Thermal: target-only DT correction

Debian already ships `qoriq_thermal`, matching `fsl,imx8mq-tmu`. The vendor
DT declares `#thermal-sensor-cells = <0>`, while `cpu-thermal` references the
TMU with a sensor ID (`<&tmu 0>`). Linux 6.12's binding requires one cell.
The provider mismatch causes sensor registration to fail with `-ENOENT`.

The live TMU's little-endian property, four range values and all 40 calibration
pairs match the selected upstream i.MX8MQ DTS. The correction only changes
`#thermal-sensor-cells` to 1. It retains this board's calibration, clock,
phandle, CPU sensor reference, memory map and firmware handover information.
It does not enable CPU frequency scaling or change its existing workaround.

Sources retained in `sources/firmware-audit/hardware-support-20261021/`:

- [Linux v6.12.113 thermal binding](https://github.com/gregkh/linux/blob/v6.12.113/Documentation/devicetree/bindings/thermal/qoriq-thermal.yaml)
- [Linux v6.12.113 i.MX8MQ DTS](https://github.com/gregkh/linux/blob/v6.12.113/arch/arm64/boot/dts/freescale/imx8mq.dtsi)
- [Linux v6.12.113 qoriq driver](https://github.com/gregkh/linux/blob/v6.12.113/drivers/thermal/qoriq_thermal.c)
- [Debian firmware package](https://packages.debian.org/trixie/firmware-realtek)

Implementation: `experiments/percept-hardware/fix-thermal-fdt.c`, a static
musl helper compatible with the stock bootstrap. Debian has no runtime OF
overlay support in this kernel, so the fix belongs in the target DT before
kexec, rather than a runtime overlay. `/boot/efi/pe100.dtb` is not modified.

Build and prepare on trixie (paths relative to uploaded helper directory):

```sh
apt-get install --no-install-recommends musl-tools binutils device-tree-compiler
sh prepare-thermal.sh
```

`device-tree-compiler` was installed as `1.7.2-2+b1`. `libfdt-dev` of that
version was also installed during investigation but is **not a build/runtime
dependency** of this helper. GCC/musl and memory-test tools are development
tools, not requirements of the installed boot route.

Passed checks: static AArch64 executable, expected DT preconditions, exactly
one changed byte in the current DT (`0x235f`, 0 to 1), idempotent output, and
rejection of a changed two-cell format. The combined upper-RAM then thermal
pipeline also passed inside the extracted launcher, as did BusyBox syntax
checking of the modified init. Sixty existing archive members are unchanged.
The subsequent live test established a CPU temperature reading.

## Prepared launcher and coordinated reboot

The candidate is retained on the PC under
`sources/firmware-audit/hardware-support-20261021/` and on the board under
`/root/percept-hardware-support/`. It is now installed on the ESP.

| Artifact | SHA256 |
|---|---|
| Input working launcher | `46e4bd0dd84336f9d7c290e3a73a1da1a74f8647f6c04c073e2f0512b2dfba27` |
| `launcher-thermal.cpio.gz` | `8b77383ae74cebce6b1967e3d1344a98eff819916b7b457a421ed32340134918` |
| `percept-fdt-thermal` | `cc4db46e44d526bb94ee1c6a8d6d26d0994935e642c0e3b11444f4a3312d4b6f` |
| Candidate `.conf` | `b07a31a98e69c15484fa3c7d0a18ab425d8397df9ae72a025cae4551141a722c` |

The archive is 4,994,513 bytes. Its config retains `upper_ram=1` and adds
`thermal_fix=1`. `prepare-launcher.py` constructs it from the specified,
hash-checked working archive, patching its own init rather than copying a
possibly divergent source file. It adds only the helper and thermal hook.
`launcher-thermal.fragment` gives the merge points for another launcher.

Before the coordinated reboot, merge with any newer USB-C launcher work.
If the installed archive/config have changed, regenerate from that version;
do not overwrite the other agent's changes with this older candidate.
DT transformations must consume the previous `target_dtb`, then pass the
final result to kexec. Every actual boot must start from that boot's live FDT.
Retain the preceding archive/config on p3 or the PC (the ESP is too small
for two full launchers), then install the merged archive and configuration.

Next-boot acceptance:

```sh
uname -r
cat /proc/sys/kernel/random/boot_id
iw dev
btmgmt info
for z in /sys/class/thermal/thermal_zone*; do
    printf '%s: ' "$z"; cat "$z/type" "$z/temp"
done
dmesg | grep -E 'qoriq|thermal|rtw_8822ce|hci0: RTL'
```

Require a new boot ID, the stock Debian release, automatically registered
radios, and a CPU thermal zone with a plausible temperature in millidegrees C
and no sensor-registration error.
To disable just this correction, remove `thermal_fix=1` from the new config.
The preceding launcher cannot parse that new key, so restore the matching
old config if rolling the archive back.

After coordination, `install-prepared-thermal.sh` installed the candidate and
retained the preceding launcher/config under
`/root/percept-hardware-support/before-thermal/`. Hash checks confirmed that
the USB-C GRUB configuration (`9929e415…`), USB-C DTB (`36d8c2b7…`) and original
DTB were unchanged. The combined RAM/thermal pipeline also passed against
the USB-C agent's actual DTB. A subsequent reboot was explicitly requested
by the user. Its timestamp and UART offset are in `reboot-start.json`.

### Live reboot result

Boot `1bd35350-fbaa-4ec0-985e-ade1143f240d` runs the same unmodified Debian
Image and matching initrd, with 4,008,368 KiB MemTotal, rw eMMC root and SSH.
`qoriq_thermal` binds to `30260000.tmu`, and `thermal_zone0` is `cpu-thermal`,
reading 37000 millidegrees C. Its trip temperatures remain 80000 and 90000;
no trip or thermal-load experiment was performed. The DT sensor-cells value
is 1 and the previous sensor-registration error is absent.

The independent USB-C change also took effect: `38100000.usb` bound to
`dwc3`, the deferred-device list is empty, and its xHCI buses enumerate the
Microsoft hubs, `03e7:2485` MyriadX and `045e:066f` Azure Eye SoM controller.
This demonstrates USB enumeration, not a functioning video/inference pipeline.
No USB-C files were modified by the thermal installation.

The repository launcher init, production launcher config and build script
are synced to the installed thermal integration. Build helpers before using
the full launcher builder. The prepared-archive tool remains an alternative
for the preceding archive; it intentionally rejects an already-integrated
thermal helper. `post-boot.txt` and `reboot-uart.log` retain the live evidence.

At 225 seconds of uptime the automatic boot marker had completed with
`Result=success`, `failcount=0` and `percept_tries=4`. CPU temperature was
still 37°C. The pre-existing FEC-related `systemd-networkd-wait-online`
failure remains; Intel Ethernet/SSH work. This was an ordinary warm reboot,
not one of the three required power-disconnected cold boots.

The evidence archive and before/after package inventories are retained in
`sources/firmware-audit/hardware-support-20261021/`. The archive SHA256 is
`52f9b5419da4df06ad38d4f4a811c65ce4367b41b8d9b4cd81cebf0151ab716d`.
