# Percept DTB for the Debian 6.12 diagnostic boot

Prepared 20 October 2026 for `6.12.113+deb13-arm64`, using the stock Debian
4 KiB-page kernel. The native boot candidate is
`sources/firmware-audit/debian-kernel/dtb/percept-6.12.113-native-booti.dtb`.
It is 41,158 bytes, SHA-256
`629ff5e7c149451aec0e007e0418152f24a872a95bc673a85a007fd40d08a86e`.
Its JSON manifest sits alongside it. It has not been boot-tested.

The candidate is byte-identical to the original recovery `pe100.dtb`: its
`/chosen` already contains only `stdout-path`, so there are no stale EFI or
initrd pointers to remove. This preserves the board's existing wiring while
providing a checked native-boot artifact. The Debian `imx8mq-evk.dtb` was used
only for supplier-ID comparison; its board nodes were not substituted.
The vendor DTB's generic “NXP i.MX8MQ EVK” model string does not establish that
the boards have interchangeable PMICs, regulators, pin assignments or peripherals.

## Reproduce and review

Run the offline [preparation tool](../tools/prepare_percept_dtb.py):

```powershell
Set-Location <LOCAL_PATH>
python -B .\tools\prepare_percept_dtb.py --mode native-booti
```

The default input is the original recovery DTB. The tool uses the existing FDT
parser, checks the critical nodes and supplier references, reads the downloaded
Linux `v6.12.113` headers and driver tables in `dtb/upstream/`, and records their
URLs and SHA-256 values. The record resolves phandles rather than comparing their
numeric values across unrelated DTBs. Clock comparisons pair specifiers with
`clock-names`, so harmless differences in property ordering do not misidentify
the supplied clocks.

Native `booti` mode assumes a raw Image handoff without a UEFI runtime contract.
For an input carrying dynamic boot data, it removes only `/chosen/linux,uefi-*`
and `/chosen/linux,initrd-start`/`linux,initrd-end`. It replaces their complete
property records with standard FDT NOP tokens. The output retains all other
property bytes, original offsets, phandles and reservation-map entries; a second
parse verifies this. It does not move memory banks, alter CMA, change regulator
voltages, replace pinmux or invent firmware reservations.

The tool checks exactly four Cortex-A53 CPU nodes using PSCI, with `method=smc`;
one lower 3 GiB RAM bank at `0x40000000`; unchanged reserved-memory/CMA nodes;
and the fixed 4 MiB rpmsg `no-map` region at `0xb8000000`. Its native mode
rejects a changed FDT reservation map pending separate qualification. These are
DTB checks; actual recovery firmware RAM ownership and payload placement still
need the boot-interface review.

## Critical compatibility findings

The exact Linux stable `v6.12.113` source snapshots are retained under
`sources/firmware-audit/debian-kernel/dtb/upstream/` and hashed in the manifest.

| Path/function | Supplier check and practical consequence |
| --- | --- |
| CPUs | ARM clock ID 258 and PSCI-SMC remain unchanged; four CPU descriptions retained. CPU-supply still refers to the vendor GPIO regulator, not a substituted EVK PMIC. |
| CCM/SRC/GPC | `fsl,imx8mq-ccm`, `fsl,imx8mq-src`, and `fsl,imx8mq-gpc` occur in the target driver tables. Critical clock/reset/domain references resolve. |
| PCIe 33800000 | Named clocks are CCM IDs 189/126/125 plus the board's fixed 100 MHz bus clock. Reset IDs 26/28/29 are PCIe PHY/apps/turnoff. |
| PCIe 33c00000 | Named clocks are CCM IDs 190/175/174 plus the same fixed bus-clock supplier; reset IDs 34/36/37 select PCIe2. |
| PCIe power | Both controllers reference domain 1, with its domain-10 parent. This dependency is also present in the Debian EVK DTB; changing controller 2 directly to domain 10 would lose that relationship. |
| eMMC 30b40000 | Eight-bit, non-removable vendor wiring/pinmux retained. Named ipg/ahb/per clocks are 236/105/210. `fsl,imx7d-usdhc` is the supported driver fallback in the supplied compatible list. |
| SD 30b50000 | Vendor card-detect and regulator GPIOs retained; clocks 236/105/211 match the reference. |
| I2C 30a20000–30a40000 | `fsl,imx8mq-i2c` matches the target driver; root clocks 184/185/186 match the reference. Existing board bus speeds and pinmux retained. |

The PCIe driver obtains clocks by name and uses these reset names. Its i.MX8MQ
variant handles the PHY internally; the modular generic `phy-fsl-imx8m-pcie`
driver is not automatically a required MQ supplier merely because its config
symbol exists. PCIe reset GPIOs retain the vendor polarity, pin number and
legacy singular property supported by GPIO lookup.
[PCIe driver](https://github.com/gregkh/linux/blob/v6.12.113/drivers/pci/controller/dwc/pci-imx6.c),
[PCIe binding](https://github.com/gregkh/linux/blob/v6.12.113/Documentation/devicetree/bindings/pci/fsl,imx6q-pcie.yaml),
[GPIO lookup](https://github.com/gregkh/linux/blob/v6.12.113/drivers/gpio/gpiolib-of.c).

The ID mappings come from the target version's
[clock header](https://github.com/gregkh/linux/blob/v6.12.113/include/dt-bindings/clock/imx8mq-clock.h),
[reset header](https://github.com/gregkh/linux/blob/v6.12.113/include/dt-bindings/reset/imx8mq-reset.h), and
[power-domain header](https://github.com/gregkh/linux/blob/v6.12.113/include/dt-bindings/power/imx8mq-power.h).
The [eSDHC driver](https://github.com/gregkh/linux/blob/v6.12.113/drivers/mmc/host/sdhci-esdhc-imx.c)
and [I2C driver](https://github.com/gregkh/linux/blob/v6.12.113/drivers/i2c/busses/i2c-imx.c)
confirm their match strings. All resolved critical clocks, resets and power
domain references agree with Debian's EVK DTB by supplier meaning and name.

## First-boot limitations

The vendor PMIC node has `gpio_intr`, but lacks standard `interrupts` and
`interrupt-parent`. The target BD718x7 MFD driver explicitly rejects an absent
IRQ before initializing its register map. The vendor regulator children also
have lowercase `regulator-compatible` values such as `buck1`, whereas the
target driver requests uppercase `BUCK1` names through case-sensitive matching.
This is a real binding gap, not a reason to copy the EVK's different PFUZE100
PMIC. No PMIC conversion was attempted. Keep the PMIC stack out of the minimal
diagnostic initramfs until IRQ wiring, chip identity and regulator constraints
are separately reviewed.
[BD718x7 MFD](https://github.com/gregkh/linux/blob/v6.12.113/drivers/mfd/rohm-bd718x7.c),
[BD718x7 regulators](https://github.com/gregkh/linux/blob/v6.12.113/drivers/regulator/bd718x7-regulator.c),
[regulator matching](https://github.com/gregkh/linux/blob/v6.12.113/drivers/regulator/of_regulator.c).

Upstream PCIe does not consume the vendor `disable-gpio`, `hard-wired`, or
`reserved-region` properties. The second controller/Wi-Fi path and vendor
display, audio, touch and camera nodes are therefore outside the initial wired
diagnostic goal. Assigned PCIe clock parents/rates from another board were not
copied: actual firmware clock state and both link-training results must be
observed. Preserve these limitations in any boot result.

The actual Debian config has `CONFIG_CLK_IMX8MQ=y`,
`CONFIG_PINCTRL_IMX8MQ=y`, `CONFIG_IMX_GPCV2=y`,
`CONFIG_IMX_GPCV2_PM_DOMAINS=y`, PCIe host support and serial console built in.
The initramfs must provide matching reset-imx7, fixed/GPIO regulator, i2c-imx,
igb, eSDHC/SDHCI and their module dependencies for early use. Keep CPU-frequency
modules and general userspace module autoloading out of the first diagnostic
boot; voltage/frequency control has not been qualified. No root filesystem
mount or RAM expansion is part of this candidate.

## A separate kexec variant

A kexec source must be an exported live DTB from the same source boot, with
fresh EFI memory-map/system-table references independently qualified. The tool's
`--mode kexec` rejects use of the recovery file as its input and requires
`--source-boot-id` and independently re-read `--current-boot-id` to match.
Those strings are operator attestations, not proof that pointers are valid.
This mode preserves all EFI and initrd properties. The kexec bundle builder must
replace initrd addresses for its newly staged image while retaining valid EFI
references. Do not strip the live EFI contract using the native `booti` mode.

No kexec variant or boot attempt was produced for this task. Local checks cover
the real candidate's parser/driver-ID validation and exact preservation; they
do not establish that Linux can initialize every described peripheral.
An offline fixture additionally verified removal of an injected stale EFI
property while retaining every original property byte, and rejection of the
recovery DTB as a kexec source.
