# CPU power management restoration plan

## Active implementation: 800 MHz to experimental 1.5 GHz

**Current recovery checkpoint:** `cpu-power-handoff.md`. Deeper CPU-idle testing
failed with early RCU/timer stalls and CPU1 hard lockup after removing
`cpuidle.off=1`. That flag is restored and normal boot verified with the
demonstrated 800–1500 MHz schedutil profile. No recovery action is pending.
Do not continue the unused-clock/domain tests now; those are separate optional
power savings and are not required for the achieved frequency scaling.

The user approved implementation on 21 October 2026, including reversible boot
changes and tests. This supersedes the research-only restrictions and the
prohibition on experimental OPP changes below. Use `cpu_profile=unchanged`,
`rated` or `oc1500`; the last explicitly admits this unit's grade at 1.5 GHz
with a 1.0 V target. No voltage tuning above 1.0 V is authorized by this plan.
The original research is retained below for context, not as current status.

ASUS board source and live PMIC reads establish BUCK2 as the CPU supplier:
see `cpu-voltage-contract.md`. The GPIO provider inherited by the running DT
does not represent the ASUS board's documented CPU supply. Therefore a separate
PMIC integration boot, with CPUfreq still disabled, precedes rated scaling.
The mainline PMIC probe has an explicit unrelated side effect: register 0x24
changes from 0x00 to 0x30, disabling LDO5/LDO6 voltage monitoring. Other voltage
constraints and hardware enable control must be preserved and checked.

User revision, 21 October: use recovery-backed direct testing with fewer
prerequisites. The PMIC boot and rated-frequency smoke tests have passed.
The user explicitly stopped making the 45-minute rated suite a prerequisite
and requested an immediate 1.5 GHz test. That long suite was stopped by request
after roughly 2.5 minutes of its first stage; it did not fail a workload check.

Latest user revision: one minute at each frequency is sufficient now; defer
soak testing. Active sequence: boot the `oc1500` profile initially in powersave;
verify the 800/1300/1500 policy; run 60 seconds each at 800, 1300 and 1500 MHz,
using bounded correctness and mixed I/O workloads. Then use 800–1500 MHz schedutil as a
provisional working profile and continue separate idle/clock/domain tests.
The former 30/60-minute OC and 45-minute rated suites remain available as
optional longer qualification, not prerequisites for testing or using 1.5 GHz.
Record cold boots as performed; do not describe warm reboots as cold boots.
This short qualification is not a claim of long-term stability.

Any correctness error, new
fault/reset, unexplained peripheral failure or temperature at 80 C rejects
the trial and restores a 1300 MHz cap. Retain 80/90 C thermal thresholds.

UART evidence is `<LOCAL_PATH>/UART/putty2.log`; do not take over PuTTY's COM port.
Native profile tests and staging artifacts are recorded under
`sources/firmware-audit/cpu-power-20261021/`. Tests on DT copies do not establish
working frequency or voltage transitions. Existing boot recovery remains the
fallback; no new recovery framework or restoration rehearsal is required.

Prepared 21 October 2026. This is a staged investigation, not an installed
configuration or permission to reboot. It retains the signed vendor bootstrap,
stock Debian kernel and fresh per-boot DT capture. No device changes were made
for this document. GPU/VPU implementation is outside this work.

## Establish the actual baseline

The reproduction ledger is older than some retained evidence. At 17:50 UTC,
`sources/firmware-audit/gpu-vpu-20261021/final-state.txt` records a launcher with
`upper_ram=1`, `thermal_fix=1`, `media=gpu-vpu`, `cma=256M`, Debian
`6.12.113+deb13-arm64`, and the three disabled mechanisms:

```text
cpuidle.off=1 clk_ignore_unused pd_ignore_unused
module_blacklist=rohm_bd718x7,bd718x7_regulator,imx_cpufreq_dt
```

Its verification record reports functional networking, thermal sensing and no
deferred devices. These are historical observations, not a live attestation.
Fresh live evidence supplied during this review records boot ID
`7850ed05-abd5-4ebb-8127-2cde06b4576f`, kernel
`6.12.113+deb13-arm64`, the same disabling arguments plus `cma=256M`, no
cpufreq policies or cpuidle directories, and `arm_a53_core` at 1.3 GHz through
`arm_pll_out`. The 400 MHz `arm_a53_div` is an unused alternate, not proof
of an active low-frequency policy. The SoC reports i.MX8MQ revision 2.1.
A 33 C reading at very low load does not qualify voltage/frequency headroom.
Capture ESP configuration and hashes,
selected GRUB DTB, launcher transformations and exported running DT before
selecting a candidate. Preserve any subsequent fixes. Do not rebuild from an
older launcher example and silently discard newer transformations.

## What the DT and drivers actually require

The retained sample DT resolves all four CPUs to shared OPP table phandle 4,
CCM ARM clock 258, PSCI and GPIO regulator phandle 0x5e, `vdd_arm`.
That regulator has two selectors: GPIO supplier 0x2e, line 13, active-high,
selector 0 = 1,000,000 microvolts; selector 1 = 900,000 microvolts.
Resolve that supplier in the fresh DT; phandle numbers are not stable identities.
The table describes 800/1000 MHz at 0.9 V and 1300/1500 MHz at 1.0 V, with
two-dimensional `opp-supported-hw` masks. These values agree with the retained
exact `v6.12.113` upstream `imx8mq.dtsi`, including its `opp-suspend` markers.
They do not establish which OPPs this chip is entitled to use.

The upstream i.MX frequency wrapper reads CPU `speed_grade` NVMEM, constructs
speed-grade/market-segment masks, then creates the generic `cpufreq-dt` device.
The generic platform initializer deliberately excludes `fsl,imx8mq`; loading
`cpufreq-dt` alone is not a replacement for the wrapper. Generic cpufreq obtains
the CPU clock, shared OPPs and `cpu-supply`, then delegates transitions to OPP.
Do not remove supply properties or hardware masks to make registration succeed.
Dependencies are the matching `imx-cpufreq-dt`, `cpufreq-dt`, OCOTP/NVMEM,
GPIO-regulator, GPIO/pinctrl and CCM drivers, OPP/regulator frameworks, and a
governor supported by this Debian build. Record exact kernel config and
`modinfo` dependencies instead of assuming all are modules.

Sources: [6.12 generic cpufreq](https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/cpufreq/cpufreq-dt.c),
[6.12 platform exclusions](https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/cpufreq/cpufreq-dt-platdev.c),
[i.MX wrapper reference](https://raw.githubusercontent.com/torvalds/linux/master/drivers/cpufreq/imx-cpufreq-dt.c).
The wrapper link is a moving reference: the exact 6.12.113 source must be fetched
and hashed before implementing its fuse decode; attempts to retrieve that exact
file during this review failed. The exact DT and PMIC source snapshots already
exist in `sources/firmware-audit/debian-kernel/dtb/upstream/`.

**CPU DVFS does not inherently require binding the PMIC MFD.** The current
CPU regulator is a GPIO selector, not the I2C BUCK2 child. However, it relies on
firmware/OTP having programmed the physical PMIC DVS slots correctly. A GPIO
selector table describes voltages; it does not measure or program those slots.
Before changing frequency, establish GPIO ownership, initial level, actual
RUN/IDLE slot values, selector polarity, settling time, and any firmware actor
that can change them. Read regulator driver initialization too: acquiring GPIOs
may itself drive a level. Never assume loading a supplier is observational.
If this contract is unproven, retain frequency blacklist and investigate the
PMIC; do not force a clock-only DVFS workaround.

The PMIC is a separate conversion. Vendor `gpio_intr` is not the IRQ binding
consumed by 6.12's MFD; its probe returns `-EINVAL` without `i2c->irq`.
Vendor lowercase `regulator-compatible` names fail the regulator driver's
uppercase `BUCK1`/`BUCK2` etc. matches. Preserve constraints and consumer
phandles when converting. Check the complete binding: required clocks,
`#clock-cells`, regulators and standard interrupt data, plus pinctrl default
state and the interrupt controller's cell format. Do not mechanically translate
the GPIO flags cell into an IRQ trigger or assume line 7 is level-low without
wiring evidence. Identify the actual chip: vendor lists `rohm,bd71840` with
`rohm,bd71837` fallback; the fallback match is not proof of electrical identity.

The regulator driver can change hardware/software control, reset targets and
DVS programming. Legacy `bd71837,pmic-buck2-*` properties are not a contract
with the upstream driver. Audit every boot-critical rail, reset behavior and
upstream `rohm,dvs-*`/hardware-control support before loading it. Never let GPIO
and I2C paths independently own the same CPU voltage transition. If retaining
GPIO DVS, preserve that hardware mode and slot contract; if moving to I2C,
prove the wiring/mode, use one provider and retest all transitions.

Sources: [exact MFD](https://github.com/gregkh/linux/blob/v6.12.113/drivers/mfd/rohm-bd718x7.c),
[exact regulator driver](https://github.com/gregkh/linux/blob/v6.12.113/drivers/regulator/bd718x7-regulator.c),
[PMIC binding](https://github.com/gregkh/linux/blob/v6.12.113/Documentation/devicetree/bindings/mfd/rohm,bd71837-pmic.yaml),
[regulator binding](https://github.com/gregkh/linux/blob/v6.12.113/Documentation/devicetree/bindings/regulator/rohm,bd71837-regulator.yaml).

## Small execution chunks and acceptance gates

Each chunk is a separate candidate with its own captured configuration, boot ID,
serial log and rollback pair. Use the existing launcher failure/rescue mechanism;
keep its original bootstrap/rescue DT intact. Apply only reviewed target-DT
transformations to that boot's fresh captured tree, after existing transforms.
No static archived EFI handover tree becomes a production input.

| Chunk | Proposed work after live review | Pass / stop condition |
|---|---|---|
| 0: evidence only | Capture the facts below; compare with retained baseline; measure quiet and CPU-load input power at fixed peripherals/ambient. | All files refer to the same boot; supply/clock/firmware unknowns explicitly resolved or block dependent work. |
| 1: WFI idle | Review Debian PSCI idle config/driver and firmware; remove only `cpuidle.off=1`, with every deeper state disabled from earliest initialization by a reviewed candidate DT that omits CPU idle-state references. Keep all frequency/PMIC blacklists and clock/domain ignores. | Timer/network wakeups work, no RCU stalls or watchdog resets. No deeper state is accidentally enabled. PSCI cpuidle may refuse to register without any DT deeper states; absence of sysfs counters in this WFI-only diagnostic is not failure or proof of WFI savings. |
| 2: firmware idle | Restore the original `cpu-idle-states` references as a separate boot. Existing state has PSCI parameter `0x10033`, local timer stop, 1000 us entry, 700 us exit, 2700 us residency. Verify those values against actual trusted firmware, PSCI feature support and kernel parsing first. | Deeper-state counters increase and wakeups work through repeated idle/load cycles on all CPUs; no hang, timer drift, interrupt loss or firmware rejection. A registered state with zero residency is not success. |
| 3: DVFS supplier gate | Audit exact driver/config, fuse masks, GPIO DVS state and slot voltages. If GPIO route is proven, retain PMIC blacklist. Otherwise complete the separate PMIC conversion review before proceeding. | One authoritative CPU voltage provider; real voltages/settling and legal OPP subset established. No dummy regulator, deferred supplier or unexplained GPIO ownership. |
| 4: minimal DVFS | First candidate exposes only one proven legal OPP so registration cannot choose an unreviewed default frequency. Remove only `imx_cpufreq_dt` from blacklist. Set an explicit conservative policy, then use a second candidate adding one additional legal OPP. | Correct speed-grade filtering, shared four-CPU policy, expected provider and measured clock; bounded repeated low/high transitions succeed with correct voltage-before-frequency increase and frequency-before-voltage decrease. No reset, error or throttling anomaly. |
| 5: governor | Add remaining factory legal OPPs only after transition checks. Test supported `schedutil` or another deliberately selected governor under quiet, single-core, all-core and mixed I/O load. | Real frequency/residency changes, stable power reduction and correct thermal cooling linkage; stress correctness checks pass. Do not force thermal trips by unsafe heating. |
| 6: unused clocks | Remove only `clk_ignore_unused`; preserve `pd_ignore_unused`. Compare clock summaries and each previously working peripheral across boot, idle and activity. | No boot/network/storage/USB/radio/thermal regression; needed clocks remain supplied, idle power change repeatable. Fix missing consumers in DT rather than adding broad permanent keeps. |
| 7: domains/runtime | Remove only `pd_ignore_unused`. Inspect genpd topology and runtime-PM counters. Enable `power/control=auto` only for individual reviewed, supported peripheral drivers. | Expected domains suspend/resume, repeated I/O survives, dependencies remain correct, no timeout/deferred probes. This flag controls unused-domain handling, not every runtime-PM policy. |
| 8: qualification | Repeat combined idle/DVFS/I/O exercise; warm reboot and three real power-disconnected cold boots; retain matching previous launcher/config and kernel/initrd. | No silent rollback, changed hash surprise, lost device, kernel fault, data error or watchdog event. Only then update the reproduction ledger. |

If deeper PSCI idle is uncertain, keep it disabled and progress on independently
qualified DVFS. Failure of a deep state does not justify disabling proven WFI.
Do not include suspend-to-RAM, CPU hotplug, fuse writes, DDR DVFS or new clock
rates in these chunks. System suspend introduces a separate firmware/PMIC
contract and requires its own test plan.

## Targeted live evidence still needed

Collect read-only evidence through the parent's existing device connection:

* Boot ID, `uname -a`, `/proc/cmdline`, kernel config, launcher/config/GRUB/DTB
  hashes and current contents; exported FDT plus decompiled CPU, OPP, GPIO,
  PMIC, thermal/cooling, PSCI, OCOTP and GPC subtrees.
* Complete boot dmesg including PSCI/SMCCC, firmware, cpuidle, cpufreq, OCOTP,
  regulator and deferred-probe messages; trusted-firmware build/version if
  already exposed. No speculative SMC calls.
* Existing cpufreq policy directories (including absence), available governors,
  current/available frequencies and transition statistics; cpuidle driver,
  governor and per-CPU state name, description, disable, usage, time, rejected.
* Existing debugfs clock, regulator, GPIO and genpd summaries, and runtime-PM
  status/counters for required devices. Do not mount/change debugfs or modprobe
  a driver merely to collect evidence without marking that as a new chunk.
* CPU NVMEM `speed_grade` cell and its resolved offset/length, read once via the
  exposed provider; derive legal masks using the exact-version wrapper. Avoid
  dumping unrelated fuse contents. Resolve board part/revision and physical
  PMIC identity from existing records/markings.
* Existing vendor PMIC driver/boot firmware handling of BUCK2 DVS, GPIO line
  mapping and initial level; slot register values through a proven read-only
  path if available. No blind `i2cdetect`, raw register writes or driver binding.
  If firmware cannot establish actual rail behavior, a safe measurement point
  and voltage/settling measurement are needed before DVFS transitions.
* Thermal trip/hysteresis/cooling maps and actual cooling-device links. Baseline
  temperature plus wall/input power at a stated ambient and fixed peripheral
  state; collect load performance/correctness and logs together.

## Overclocking remains a separate decision

Restore stock management first. The DT's highest listed OPP, a readable clock
rate or a cool sensor reading does not establish headroom. Speed/market fuses,
actual ordering code, voltage limits and tolerances, rail transients, board
power delivery and junction limits all constrain operation. NXP's
[i.MX8MQ consumer data sheet](https://www.nxp.com/docs/en/data-sheet/IMX8MDQLQCEC.pdf)
provides part-specific electrical conditions; identify this board's part and
use its applicable consumer/industrial document before interpreting limits.
Do not overwrite masks, add OPPs, raise a voltage constraint or alter PLL rates
as part of this restoration. Even stock DVFS needs transition and correctness
testing; short benchmarks and absence of thermal throttling do not prove long
term reliability or data integrity above the rated envelope.

