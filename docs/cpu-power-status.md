# CPU clock, temperature and power-management status

## Implementation progress (21 October 2026)

**Later CPU-idle test rolled back through rescue:** removing `cpuidle.off=1`
caused early CPU/timer/RCU stalls before initramfs/modules. The flag has now
been restored and normal boot verified, ID
`4cc6e675-5705-49e9-8c46-09a0b9a2fa1f`: 800–1500 MHz schedutil, service success,
34 C, no lockup/RCU-stall messages. The passing DVFS setup is separate.
Clock/domain settings were not changed.
See `cpu-power-handoff.md` for the last observed boot, working config and
recovery paths. No further idle/clock/domain experiments are planned now.

The completed short tests passed at 800/1300/1500 MHz, with peaks of 35/37/38 C.
The user replaced long qualification prerequisites with one minute per rate;
soak testing is deferred. Automatic powersave initialization and persistent
800–1500 MHz schedutil were verified after reboot
(`8a18bd6d-0f49-4e9a-8f50-45ba8397cfd9`). The normal Debian `/initrd.img` path
is in use, with reproducible hooks. The rated 1300 MHz policy cap was also
applied and verified before returning to 1500. No physical cold boots are claimed.
See [benchmark results](cpu-benchmarks.md) and
[installation/rollback](cpu-power-install.md). The following paragraphs record
earlier implementation milestones; the remaining work is independent idle,
unused-clock and unused-domain testing.

The user subsequently approved implementation of 800/1300 MHz scaling and an
explicit 1500 MHz profile at 1.0 V. The initial research below is historical.
ASUS source confirms PMIC BUCK2 is the CPU supply; the inherited GPIO regulator
is not the board-specific supplier. See `cpu-voltage-contract.md`.

The isolated PMIC boot passed on Debian 6.12.113+deb13-arm64, boot ID
`a9a2f9aa-b5b2-4239-a5f2-574aeda92a94`. All fifteen regulators registered;
BUCK2 reads 1.0 V. Other rail selectors and voltage constraints are unchanged.
Confirmed probe effects are REGLOCK 0x11 to 0x00, monitor register 0x24 from
0x00 to 0x30, and IRQ initialization. The monitor change disables LDO5/LDO6
monitoring and is intentional, not an unchanged-setting claim.

Installed launcher SHA256:
`b18c4c8dd969d9c46de00b39933448f2f6a91a6224d479e6dd782a82393afe07`.
Original launcher/configuration remain under `/root/percept-cpu-build/` and in
the PC evidence directory. A separate CPU test initramfs preserves the working
original initramfs. Its early script runs before udev, loads powersave, and
uses kmod install guards. Same-module softdep directives were removed after
real kmod testing showed they bypassed the install guard.

CPU helper native tests passed both output contracts and six rejected inputs;
PMIC helper passed the full property/reservation contract and nine rejected
inputs. Six runner fixture tests and six module-guard fixture tests passed.
The rated-profile reboot has been requested; frequency-transition qualification
and 1.5 GHz tests are not yet claimed. UART: `<LOCAL_PATH>/UART/putty2.log`.

Research and live inspection: 21 October 2026. No device configuration changes,
frequency/voltage writes or reboot were performed. Previous GPU/VPU work is
discontinued in this task; preserve the newer installed implementation.

## Findings

The current Debian 6.12.113+deb13-arm64 boot is
`7850ed05-abd5-4ebb-8127-2cde06b4576f`. The active `arm_a53_core` clock reads
1,300,000,000 Hz through `arm_pll_out`. The alternate `arm_a53_div` at 400 MHz
is not the selected CPU clock. These are clock-framework readings, not an
independent frequency-counter measurement. Temperature is 33 C at nearly idle
load (0.01/0.08/0.04).

The four-byte speed-grade cell at NVMEM offset 0x10 reads `0x60002a82`.
The exact upstream 6.12.113 driver decodes speed bits 9:8 as 2 and market bits
7:6 as 2, producing supported-hardware masks `<4 4>`. Against the live DT,
only 800 MHz and 1300 MHz qualify. The listed 1000 MHz and 1500 MHz OPPs do
not qualify. Do not remove the hardware masks to enable them. This supports
the industrial 1.3 GHz conclusion; it does not identify every package/BOM detail.

| Temperature limit | Range / setting | Interpretation |
|---|---|---|
| ASUS PE100A ambient | -20 to +60 C | Board product rating; confirm Percept BOM equivalence for environmental qualification. |
| Industrial i.MX8MQ junction | -40 to +105 C | Relevant silicon grade; junction is not room temperature. |
| Consumer i.MX8MQ junction | 0 to +95 C | Comparison only, not the identified grade. |
| Installed passive trip | 80 C, 2 C hysteresis | Requested thermal cooling threshold. |
| Installed critical trip | 90 C, 2 C hysteresis | Linux critical action threshold, not the silicon maximum. |

Primary datasheet/product links and electrical qualifications are in
[clock limits research](cpu-clock-limits-research.md). Do not raise the existing
thermal trips merely because the industrial silicon limit is higher.

CPUfreq has no active policy and is blacklisted. The only registered thermal
cooling device is `38000000.gpu` (states 0 through 6). Thus the CPU's DT cooling
map does not establish working CPU frequency throttling. Deep idle is disabled
by `cpuidle.off=1`; unused clocks/domains are retained by `clk_ignore_unused`
and `pd_ignore_unused`. This is not proof every form of hardware idle or
peripheral runtime management is disabled. Firmware reports PSCI 1.1.

CPU supply is `vdd_arm`, a GPIO regulator using GPIO1_IO13, currently high.
The DT maps high to 0.9 V and low to 1.0 V. Linux reports 0.9 V, while its
1.3 GHz OPP requests 1.0 V. This is a selector-derived report, not an actual
rail measurement. Resolve the physical DVS slot values and polarity before
enabling transitions; do not label the board undervolted solely from this data.

## Manageable follow-on work

1. **Voltage contract:** inspect vendor GPIO/PMIC initialization and DVS slots,
   reconcile the reported voltage, and identify required transition settling.
   Keep the PMIC driver blacklisted if the GPIO path is sufficient. Deliver a
   concrete DT/driver candidate with one CPU voltage owner.
2. **Rated CPU scaling:** enable the exact Debian CPUfreq wrapper using only
   the fuse-approved 800/1300 MHz operating points after the voltage contract
   is established. Test transitions, governor behavior, CPU cooling registration
   and bounded load correctness. Record idle/load temperature and input power
   with ambient temperature. This is the first useful functional milestone.
3. **Idle and peripheral power:** test CPU idle separately, then unused clock
   gating, then unused power domains. Preserve current GPU/VPU/USB/radio fixes;
   verify wakeups and peripheral activity after each change. A deep-idle failure
   need not block independently working CPU scaling.
4. **Qualification and repeatability:** verify repeated cold boots and mixed
   workloads; document exact launcher/DT changes over stock Debian, hashes and
   rollback. Read the second device's own grade rather than copying assumptions.

Sol subagents completed separate clock/temperature research and the detailed
[power-management implementation plan](cpu-power-management-plan.md). That
plan contains smaller test candidates within the four work packages above.

Restoring power management should reduce idle power and provide proper voltage
sequencing and thermal control. It does not increase the silicon rating.
1.5 GHz would be overclocking this unit, a 15.4% clock increase with potentially
smaller application gains. No reliable overclock headroom has been established
by the idle temperature. Assess it only after rated operation is characterized.

## Evidence

Saved under `sources/firmware-audit/cpu-power-20261021/`:
`live-inventory.txt`, `grade-word.txt`, `grade-thermal.txt`,
`cooling-devices.txt`, and `imx-cpufreq-dt-v6.12.113.c`.
The initial byte-sized NVMEM read was rejected by the driver; the successful
read used one aligned four-byte access, with no writes.

Exact source: https://raw.githubusercontent.com/gregkh/linux/v6.12.113/drivers/cpufreq/imx-cpufreq-dt.c

Source SHA256: `36261d6b3f7101e48f465f7162d7853e4bcd307f483c97637709876611d56a19`.
