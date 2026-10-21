# USB-C port on Debian trixie

## The problem

Under Debian's stock `6.12.113+deb13-arm64` the USB-C port never appears. It is
the only deferred device on the board:

```text
# cat /sys/kernel/debug/devices_deferred
38100000.usb	dwc3: failed to get extcon
```

The other controller, `usb@38200000`, probes normally and carries the internal
Genesys Logic hub, the Realtek Bluetooth radio and the USB-A ports.

Comparing the two device-tree nodes, they are identical apart from one
property. Both have `dr_mode = "host"`; only the USB-C node adds:

```dts
extcon = <0x49>;    /* -> /soc@0/bus@30800000/i2c@30a30000/it5201@67 */
```

Phandle `0x49` is an `ite,it5201` USB-C CC-logic chip at I2C address 0x67.
**Linux has no driver for `ite,it5201`** — the only ITE part supported is
`it5205`, a different chip (a DisplayPort alt-mode mux, `typec/mux/it5205.ko`).
So `extcon_get_edev_by_phandle()` can never resolve, dwc3 defers for ever, and
the port stays dead. `CONFIG_OF_OVERLAY` is off in Debian's kernel, so there is
no runtime overlay escape either.

## The fix: drop the dangling property (no kernel changes)

Removing `extcon` leaves the node byte-for-byte equivalent to the working
`usb@38200000`, which is the direct evidence that this is sufficient — same
kernel, same SoC, same `dr_mode = "host"`, and it probes as an xHCI host.

`tools/strip_dtb_property.py` does the edit, reusing the parser and FDT_NOP
technique of `tools/prepare_percept_dtb.py`:

```sh
python tools/strip_dtb_property.py pe100.dtb pe100-usbc.dtb \
  --remove '/soc@0/usb@38100000:extcon' \
  --expect-sha256 629ff5e7c149451aec0e007e0418152f24a872a95bc673a85a007fd40d08a86e
```

The property record is overwritten with NOP tokens, so the file keeps its exact
size and every other byte, offset, phandle and reservation-map entry. The tool
re-parses the result and fails unless all 214 nodes and every other property
are byte-identical. Manifest: `sources/firmware-audit/usbc-20261021/`.

| File | SHA-256 |
|---|---|
| `pe100.dtb` (original, untouched) | `629ff5e7…0a86e` |
| `pe100-usbc.dtb` | `36d8c2b7…b1fab` |

## Delivery: ESP only, no launcher change

GRUB loads the DTB, UEFI adds its own `/chosen` data, and the launcher passes
the resulting live FDT on to kexec (through `percept-fdt-upper` for the upper
RAM bank). So patching the file GRUB loads carries the fix into trixie with no
change to the launcher or its initramfs.

`grub.cfg` was changed on one line: the **Debian trixie** entry now loads
`pe100-usbc.dtb`, while the **Percept rescue** entry deliberately stays on the
original `pe100.dtb`. If the patched DTB ever broke the stock launcher kernel,
the trixie entry would fail, the `percept_tries` countdown would run out, and
GRUB would reach rescue with the known-good DTB. The previous config is kept on
the ESP as `grub.cfg.pre-usbc`.

## What this does and does not give

Works: the port as a **USB host** — plug in a device or hub and it enumerates,
like the USB-A ports.

Not available, because they all need CC/PD detection from the undriven it5201:

- device/gadget mode, and automatic host↔device role switching;
- DisplayPort alternate mode;
- USB Power Delivery negotiation.

**USB recovery is unaffected.** It runs over the i.MX8MQ boot ROM's SDP and
SPL's SDPV, entered by `flagutil -wBfRequestUsbFlash -v1` plus a reboot (see
`docs/boot-interface-test.md`). That path is all pre-Linux and never reads the
Linux device tree, so `dr_mode` and `extcon` cannot affect it. The port still
comes up as a peripheral for `uuu`.

If gadget mode is wanted later instead of host, set `dr_mode = "peripheral"` in
the same patched DTB; the two cannot be switched automatically without a driver
for the it5201.

## Result: the Vision (Azure Eye) SoM is what was behind this port

After the reboot, `/sys/kernel/debug/devices_deferred` is empty and
`38100000.usb` binds dwc3 → `xhci-hcd.1.auto` (buses 1 and 2). The camera
module enumerates on it:

| Device | ID | Driver |
|---|---|---|
| Microsoft 2-Port USB 2.1 Hub (SoM internal) | `045e:066e` | hub |
| Intel Movidius MyriadX (VPU) | `03e7:2485` | none |
| Microsoft Azure Eye SoM Controller (STM32) | `045e:066f` | `cdc_acm` → `/dev/ttyACM0` |
| Microsoft 4-Port USB 3.1 Hub (SuperSpeed side) | `045e:066d` | hub |

Buses 3 and 4 remain the internal Genesys hub and Bluetooth on `38200000`.

This clears the step-1 blocker in
`percept-camera-usefulness/outputs/percept-camera-assessment.md`, which was
written while this port was still deferred. Two of its open questions are now
answered on this unit:

- **`045e:066f` reports `bcdDevice 3.00`** (iSerial `14016124090452101008`), so
  the SoM is already on the updated firmware. **The unsupported ASUS/Microsoft
  SoM update is not needed** and should not be attempted.
- `03e7:2485` is present with `bcdDevice 0.01` and `iSerial 03e72485` — the
  Myriad X in its USB boot-ROM state, awaiting `/eyesom/mx.mvcmd` from the
  container. No driver binds it, and there is no `/dev/video*`, because the
  IMX219 sensor hangs off the VPU rather than appearing as a UVC webcam.

Remaining gap for the prepared capture test: **Docker is not installed** on
trixie (root has 13 GB free, arch arm64, `/dev/bus/usb/001/` present with
189:* char devices for the container's cgroup rule). Note the README's
cgroup-v1 requirement applied to the vendor 5.4 kernel, which lacked
`CONFIG_BPF_SYSCALL`; on Debian 6.12 the default cgroup v2 and nftables should
be fine, and the trixie command line deliberately has no
`systemd.unified_cgroup_hierarchy=0`.

## Status

- [x] Cause identified (dangling `ite,it5201` extcon phandle)
- [x] Patched DTB built and verified surgical
- [x] Installed on the ESP; rescue kept on the original DTB
- [x] Rebooted: `38100000.usb` probes, camera SoM enumerates
- [ ] Install Docker, load the preserved image, run the proof-of-capture test
