# CPU voltage contract investigation

21 October 2026. Research only; no device access or changes by this author.
Parent owns all live reads, writes and reboots. Rated 800/1300 MHz and separately
labelled experimental 1500 MHz are authorized; every selected voltage must stay
at or below 1,000,000 uV. No fuse changes.

## Finding that changes the implementation

The current GPIO regulator is the i.MX8MQ **EVK MP2147 discrete converter**
configuration. It is not evidence that GPIO1_IO13 selects BD71837/BD71840 DVS
slots. NXP's original submission identifies MP2147 and gives GPIO high = 0.9 V,
low = 1.0 V. The retained Percept tree also declares a separate I2C PMIC at
0x4b with BUCK2, a 0.9–1.0 V constraint and legacy RUN/IDLE settings.

Source: [NXP author's EVK regulator patch](https://lists.openwall.net/linux-kernel/2019/02/28/1345).
The later [NXP always-on correction](https://lists.openwall.net/linux-kernel/2019/10/09/120)
confirms that this GPIO only selects the EVK converter voltage.

Consequently GPIO high plus a 900 mV regulator report at 1300 MHz is explained
by Linux looking up selector 1 in `states`; it does not demonstrate the CPU
rail is 900 mV. An inherited EVK supplier node can be unrelated to the board's
real CPU power path. GPIO-regulator keeps a software selector state and reports
its configured table value; it has no ADC. Do not use its report as a PMIC read.

## PMIC slots and targeted reads

The vendor DT's legacy array is RUN=1,000,000 uV, IDLE=900,000 uV, third=0
(unsupported BUCK2 suspend slot). The [legacy NXP driver](https://coral.googlesource.com/linux-imx/+/refs/heads/release-day/drivers/regulator/bd71837-regulator.c)
parses these properties and writes the RUN and IDLE selector registers. This is
reference code, not proof of the exact installed vendor driver or values now in
silicon. The properties in this board's tree sit beneath `regulators`; that
placement also needs matching against the actual vendor MFD child node.

Resolve the actual bus from existing sysfs rather than scanning addresses:

```sh
readlink -f /sys/bus/i2c/devices/*-004b/of_node
readlink /sys/bus/i2c/devices/*-004b/driver
```

With the PMIC unbound as expected, parent may read these configuration/ID
registers using `i2cget -y BUS 0x4b REG b`, once each, without `-f`:

| REG | Meaning |
| --- | --- |
| 0x00 | Revision |
| 0x02 | I2C device configuration |
| 0x03 | PWRCTRL0 |
| 0x04 | PWRCTRL1 |
| 0x06 | BUCK2 control / ramp configuration |
| 0x10 | BUCK2 RUN voltage selector |
| 0x11 | BUCK2 IDLE voltage selector |

These are configuration registers, not interrupt status registers. Do not dump
all registers. [ROHM driver's submitted register map](https://lkml.iu.edu/hypermail/linux/kernel/1809.1/02957.html)
provides these addresses. BUCK2 voltage is `700000 + (reg & 0x3f) * 10000`
within the supported selector range 0..60: 0x1e is 1.0 V and 0x14 is 0.9 V.
Current sources do not establish BD71840 silicon differences; preserve that
qualification when interpreting the fallback BD71837 map.

## Settling and viable implementation

The retained exact 6.12.113 `bd718x7-regulator.c` defines BUCK ramp rates
10000/5000/2500/1250 uV per microsecond. A 100 mV change therefore takes
10/20/40/80 microseconds of nominal programmed ramp. This is not a validated
MP2147 settling specification and does not include board transient margin.
The PMIC driver's regulator timing helper uses the configured ramp; use its
sequence through OPP rather than a clock-only path or a startup-delay guess.

Preferred candidate, once real BUCK2 ownership is corroborated: reparent all
four `cpu-supply` properties to the real PMIC BUCK2 provider, disable/remove the
EVK GPIO regulator, keep BUCK2 constraints 900000..1000000, boot-on/always-on,
and use the audited PMIC provider as the sole voltage owner. Convert node names
to upstream BUCK2 matching; retain all other rail consumers and constraints.
Binding the whole upstream PMIC has broader initialization effects, so this
candidate requires its MFD IRQ/clock/reset and every rail audit first. Merely
changing CPU phandles to an unbound PMIC causes deferred probe, not safe DVFS.

Alternative after verifying an unchanged RUN slot is 1.0 V and firmware keeps
PMIC RUN during the test: a genuinely fixed 1.0 V CPU supply allows frequency
scaling 800/1300 and experimental 1500 without any voltage selection. This is a
valid explicit fixed-voltage test only after the physical source and firmware
state contract are established. It is not justified by inventing a dummy rail.

**Initial investigation blocker (resolved by vendor source below):** no board wiring or exact vendor CPU supply implementation
has yet tied GPIO1_IO13 or real PMIC BUCK2 unambiguously to VDD_ARM; current
slot values and mode are still needed. Do not toggle GPIO1_IO13 to infer wiring.
Parent should inspect factory running DT/CPU supply and vendor clock/regulator
implementation plus targeted PMIC reads. If these agree on BUCK2 at 1.0 V,
that supports the fixed-voltage route without driving the inherited EVK pin.

Experimental 1500 MHz must be a separate explicit OPP opt-in, preserve rated
OPP hardware masks and the 1.0 V ceiling, and retain thermal CPU cooling.
Its voltage match to 1300 MHz does not remove the industrial speed-grade limit.

## Parent's targeted live read results and refined candidate

Parent subsequently read bus 0 address 0x4b while unbound (see adjacent
`pmic-cpu-registers.txt` and `pmic-state-registers.txt`):

```text
00=a3 02=03 03=a2 04=00 06=40 10=1e 11=14
20=c0 2d=80 2f=11
```

RUN=1.0 V and IDLE=0.9 V are now actual register evidence, rather than only
DT declarations. BUCK2 control 0x40 has hardware enable control (`SEL=0`)
and 5 mV/us ramp. Its zero software EN bit does not mean the hardware state
machine disabled the live rail. REGLOCK=0x11 locks power sequence and voltage
registers. TRANS_COND1 low nibble zero selects SNVS after poweroff; preserve
this rather than accepting upstream's default rewrite to READY. POW_STATE=0x80 is stable RUN; the datasheet decode is recorded below.

[ROHM header masks](https://android.googlesource.com/kernel/common/+/b44e46bb047d1/include/linux/mfd/rohm-bd718x7.h)
define SEL=0x02, EN=0x01, ramp mask=0xc0 and the state/config register addresses.
The retained exact upstream source supplies the implementation audit below.

A concrete minimal **mainline PMIC integration candidate**, before boot:

1. Reparent every CPU supply to the existing PMIC BUCK2 phandle. Disable the
   stale GPIO regulator; do not drive GPIO1_IO13 as a test.
2. Rename existing regulator nodes to BUCK1..BUCK8 and LDO1..LDO7 according to
   their lowercase `regulator-compatible`, preserving phandles and constraints.
   Add absent LDO5/LDO7 nodes. Add `rohm,no-regulator-enable-control` to ALL
   fifteen nodes. Omitted nodes do not prevent registration: driver probes all.
3. Set parent `rohm,reset-snvs-powered` so probe preserves TRANS_COND1. Do not
   add reset-trigger or button-duration properties.
4. Remove BUCK1's inherited `regulator-ramp-delay=1250` to avoid changing that
   unrelated rail. Set only BUCK2 `regulator-ramp-delay=5000`, matching its
   current bits and providing 20 us nominal timing for 100 mV. Its min/max stay
   900000/1000000 with boot-on/always-on. Do not add legacy or new DVS-slot
   properties: current slots already match the requirement.
5. Convert PMIC IRQ and clock binding only with pin/wiring evidence. The MFD
   requires an IRQ; `gpio_intr` is not accepted. The legacy flags cell is a
   GPIO polarity flag and is not an IRQ trigger number. Parent must resolve
   GPIO1 line7 wiring/active level, default pinctrl and the clock source.
6. Keep initial frequency at a single 1300 MHz/1.0 V OPP. Introduce the second
   rated OPP only after supplier registration and readback. Experimental
   1500 MHz is a later explicit opt-in with 1.0 V and its own correctness test.

Hardware-enable-control operations still support voltage read/write, so
retaining hardware enable ownership does **not** prevent changing the BUCK2
RUN voltage using OPP/regulator sequencing. It prevents unrelated software
rail enables/disables and SEL takeovers. Current fixed RUN/IDLE power state
must remain part of that contract; system suspend is not in scope.

Mainline probe still has unavoidable writes: it clears REGLOCK bits 0x11;
MFD initializes its IRQ mask/ack handling; regulator driver sets MVRFLTMASK2
0x24 bits 0x10 and 0x20 for LDO5/LDO6 undervoltage-monitor shutdown behavior.
There is no DT switch to omit those last two writes. Read 0x24 first; if those
bits are already set they are no actual monitor-mode change. It skips changing
SEL with the properties above and skips TRANS_COND1 with the reset property.
Constraint registration may adjust a rail whose current selector falls outside
its declared range, so parent should read only configuration 0x05..0x1e and
compare every current rail against retained constraints before accepting the
candidate. The missing LDO nodes need hardware-control markers even if they
have no new voltage constraint. Do not set arbitrary fixed voltages on them.

Outstanding before this candidate can be booted: IRQ/clock binding evidence,
configuration/constraint comparison, current active-state decode or equivalent
vendor firmware proof, and corroboration that real BUCK2 supplies VDD_ARM.
Factory supply phandles and exact vendor regulator code are preferable to a
new physical GPIO experiment. The observed RUN slot strongly supports the
PMIC hypothesis but does not itself identify the board net.


## Final source resolution and implementation gate

The initial physical-supply uncertainty above is now resolved to a reasonable
board-specific engineering standard by ASUS's own published BSP, rather than
by the generic PMIC rail naming convention. Parent fetched these exact files
from `ASUS-IPC/linux-imx`, branch `yocto-sumo-imx_8m` into this evidence folder:
`asus-pe100a.dts`, `asus-imx8mq.dtsi`, `asus-imx8-ca53.dtsi`, and
`asus-imx8mq-cpufreq.c`.

The [official ASUS board source](https://github.com/ASUS-IPC/linux-imx/blob/yocto-sumo-imx_8m/arch/arm64/boot/dts/freescale/fsl-imx8mq-pe100a.dts)
identifies ASUS PE100A, comments PMIC BUCK2 as VDD_ARM, constrains it to
0.9–1.0 V, and explicitly assigns `A53_0 dc-supply = <&buck2_reg>`.
The vendor CPU frequency driver requests the optional `dc` regulator and
changes it to 1.0 V before maximum frequency and 0.9 V after leaving maximum
frequency. Its separate optional `arm` handle is unused for this board:
neither of the complete two-level includes supplies `arm-supply`, nor do they
provide the EVK GPIO converter. There is no evidence of two cascaded supplies.
This supports replacing the present stale EVK supplier with actual PMIC BUCK2.
It is source evidence, not a measured rail waveform or a board schematic.

ASUS's official [PE100A wiki](https://github.com/ASUS-IPC/ASUS-IPC/wiki/PE100A)
links this BSP repository and build target. The exact Microsoft Percept binary
BSP need not be identical; its corresponding PMIC configuration, constraints,
address, pinmux and selector readbacks corroborate the ASUS source. Do not
claim every Percept BOM detail has been established from PE100A branding.

The [ROHM-authored data sheet](https://www.farnell.com/datasheets/2736557.pdf)
Table 3-7 (page 25) defines POW_STATE high nibble 8 as RUN and low bits 00 as
stable. Thus current 0x80 is stable RUN, and BUCK2 currently selects the read
1.0 V RUN setting. Section 4.2/Figure 4-5 (page 68) shows latched interrupt
conditions driving the active-low IRQ_B until write-one-clear acknowledgment.

The board source's actual GPIO declaration uses GPIO1 line 7 active-low;
its pinctrl maps GPIO1_IO7, matching the live tree. The old adjacent comment
saying GPIO1_IO3 is stale. A justified upstream conversion is therefore
`interrupt-parent = <&gpio1>; interrupts = <7 IRQ_TYPE_LEVEL_LOW>;`, where
IRQ_TYPE_LEVEL_LOW is 8. Set `pinctrl-names = "default"` and preserve that
existing pinctrl group. This is derived from the board's GPIO connection plus
PMIC interrupt behavior, not by copying a GPIO flag into an IRQ flag.

Clock detail: upstream `clk-bd718x7.c` requires a named parent to register its
32k output gate. [ROHM's design guide section 5.6](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator_system/bd71837mwv-platform_design_guide.pdf)
explains the PMIC XIN/XOUT crystal source; arbitrary reuse of SoC `ckil` as an
input is not established by this. MFD creates clock and regulator children
independently: a missing clock parent makes the clock child probe fail, but
it does not prevent regulator child registration. For a minimal regulator
experiment, omit an unproven clock connection and explicitly record the clock
child failure and incomplete schema compliance. A production complete binding
should represent the real crystal and maintain any required C32K_OUT consumer.
Do not silently route or gate the SoC's existing 32k clock through a new path.

### Full configuration comparison

Parent's `pmic-rail-config.txt` confirms these decoded RUN/select values:

| Rail | Current voltage | Retained constraint permits it? |
| --- | --- | --- |
| BUCK1 | 0.95 V | Yes |
| BUCK2 | 1.0 V | Yes, ceiling 1.0 V |
| BUCK3 / BUCK4 | 1.0 V each | Yes |
| BUCK5 | 1.0 V | Yes |
| BUCK6 | 3.3 V | Yes |
| BUCK7 | 1.8 V | Yes |
| BUCK8 | 1.1 V | Yes |
| LDO1 | 3.3 V | Yes |
| LDO2 | 0.9 V | Yes |
| LDO3 | 1.8 V | Yes |
| LDO4 | 0.9 V | Yes |
| LDO5 | 1.8 V | Missing vendor node; add no-enable-control without new voltage request |
| LDO6 | 0.9 V | Yes |
| LDO7 | 3.3 V | Missing vendor node; add no-enable-control without new voltage request |

All read software enable-select bits are zero; hardware state owns the rails.
The constraints do not call for an unrelated voltage correction. The GPIO
regulator's reported 0.9 V is reconciled with actual PMIC stable RUN=1.0 V;
it must not be used to accuse the board of undervoltage.

**Material unavoidable mainline side effect:** 0x24 was actually read as 0x00.
The regulator driver's unconditional LDO5/LDO6 additional initialization will
change it to 0x30, disabling those two undervoltage monitors. This is a real
protection-policy change. Upstream comments justify it to avoid false emergency
resets when parent BUCK6/7 turn off during shutdown; the deployed firmware
currently leaves those monitors enabled. Hardware-enable-control properties
do not prevent this write, and there is no DT opt-out. Do not describe the
candidate as preserving every unrelated rail/protection setting.

Final gate: the supply identification, stable RUN selection, IRQ conversion,
rail constraints and ramp timing are resolved well enough to stage a concrete
mainline BUCK2 experiment. Boot acceptance still requires deliberate inclusion
of the above 0x24 protection change and REGLOCK unlock, independent clock-child
handling, and confirmation that no other software changes PMIC state during
DVFS. If scope requires preserving 0x24, the stock mainline regulator probe
cannot meet that requirement; keep the driver blacklisted and stage only, or
implement a narrowly audited provider which changes only BUCK2 RUN and its
lock contract. Do not perform a broad PMIC probe while claiming no side effects.

Implementation review guard: exact 6.12.113 source's `get_special_regulators()`
reads `rohm,no-regulator-enable-control`. Use that spelling on every rail;
`rohm,no-enable-control` is not the property consumed by this driver. A typo
would remove the intended protection against wholesale software enable control.
Keep the original `rohm,bd71840`, `rohm,bd71837` compatible list: the fallback
already selects the existing upstream implementation without erasing vendor
identity. Fail closed if either GPIO controller or PMIC pinctrl phandle resolves
to an unexpected node or GPIO1_IO7 pad configuration.
