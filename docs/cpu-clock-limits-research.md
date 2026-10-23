# CPU clock limits: research and assessment plan

Research date: 2026-10-21. Research only: no board commands, device changes,
voltage changes, or overclock tests were performed for this note. The earlier
GPU/VPU investigation is discontinued; its CPU paragraph is historical evidence,
not a statement of the board's present state.

## Established limits

| Scope | Published limit | Meaning |
| --- | --- | --- |
| ASUS PE100A product | Cortex-A53 up to 1.3 GHz; ambient -20 to +60 C | ASUS's board-level specification; Azure Percept's exact board/BOM still needs matching. |
| NXP industrial i.MX8MQ | HZ speed code: 1.3 GHz; example MIMX8MQ6CVAHZAB; junction -40 to +105 C | Relevant if the actual package/grade matches. |
| NXP consumer i.MX8MQ | JZ speed code: 1.5 GHz; example MIMX8MQ6DVAJZAB; junction 0 to +95 C | A different qualified grade, not proof every i.MX8MQ supports 1.5 GHz. |

Sources: [ASUS product](https://www.asus.com/networking-iot-servers/aiot-industrial-solutions/embedded-computers-edge-ai-systems/pe100a/),
[ASUS original announcement](https://iot.asus.com/resources/news/pe100a-edge-computer/),
[NXP industrial datasheet, Rev. 3, Tables 2 and 8, printed pp. 6–7, 18–20](https://www.nxp.com/docs/en/data-sheet/IMX8MDQLQIEC.pdf),
[NXP consumer datasheet, Rev. 3, Tables 2 and 8, printed pp. 6–7, 18–20](https://www.nxp.com/docs/en/data-sheet/IMX8MDQLQCEC.pdf).

Both datasheets specify VDD_ARM overdrive operation at 0.9–1.05 V (1.0 V
typical), with the allowed CPU rate determined by the part's grade. Nominal mode
is 0.81–1.05 V (0.9 V typical): industrial maximum 800 MHz, consumer 1 GHz.
Industrial VDD_SOC is 0.9–0.99 V (0.95 V typical). These are operating ranges,
not permission to use any clock at any voltage within the range. See the
[industrial electrical tables](https://www.nxp.com/docs/en/data-sheet/IMX8MDQLQIEC.pdf).

VDD_ARM's 1.1 V absolute maximum is a stress limit, not an operating target.
The ARM PLL's published 800 MHz–1.6 GHz range likewise does not qualify the
CPU cores at 1.6 GHz. GPU has a separate rail and 800 MHz nominal / 1 GHz
overdrive limits. LPDDR4-3200 describes a memory data rate, not a CPU clock;
its corresponding 1600 MHz transfer clock and DDR clock-tree readings require
their own interpretation. See [consumer datasheet Tables 5, 8 and 21](https://www.nxp.com/docs/en/data-sheet/IMX8MDQLQCEC.pdf).

## Existing evidence and uncertainty

The historical `docs/gpu-vpu-plan.md` CPU paragraph reports `arm_a53_core`
at 1.3 GHz, cpufreq blacklisted, no cpufreq sysfs, and a vendor OPP table
containing 1.5 GHz. It also reports unqualified/blacklisted BD71837 support.
Reconfirm all of these against the current boot. An OPP in a DTB is a software
candidate; it is not a measured rate or a silicon rating. A clock-framework
readback is normally a rate calculated from registers, not an independent
frequency measurement. `/proc/cpuinfo` BogoMIPS is not a clock measurement.

The subsequent read-only inventory supplied by the main investigation reports
1.3 GHz, roughly 33 C idle, and regulator-summary 900 mV with GPIO1_13 high.
That voltage is a software description/readback, not an electrical measurement.
It must be reconciled with the 1.0 V upstream 1.3 GHz OPP before changing clocks.
No package marking or sustained thermal trace has been established here.
Silicon revision 2.1 alone does not identify a speed grade.

The main investigation's narrowly scoped four-byte read is recorded in
`sources/firmware-audit/cpu-power-20261021/grade-word.txt`: little-endian
word `0x60002a82`. The upstream i.MX8MQ decoder extracts speed with
`(word & 0x300) >> 8` and market segment with `(word & 0xc0) >> 6`, yielding
speed 2, segment 2, and OPP selection masks `0x4, 0x4`. The all-zero sample
fallback does not apply. See the [exact Linux v6.12.113 decoder](https://github.com/gregkh/linux/blob/v6.12.113/drivers/cpufreq/imx-cpufreq-dt.c),
also inspected locally as
`sources/firmware-audit/cpu-power-20261021/imx-cpufreq-dt-v6.12.113.c`
(SHA256 `36261d6b3f7101e48f465f7162d7853e4bcd307f483c97637709876611d56a19`).
The [upstream i.MX8MQ DT](https://github.com/torvalds/linux/blob/master/arch/arm64/boot/dts/freescale/imx8mq.dtsi)
labels segment mask `0x4` industrial, accepts that speed at 1.3 GHz, and excludes
it at 1.5 GHz (which requires speed mask `0x8` and segment mask `0x3`). Thus
the fuse selection permits the 800 MHz and 1.3 GHz upstream CPU OPPs, excluding
1 GHz and 1.5 GHz. It supports the industrial 1.3 GHz conclusion; it does not
establish the complete package ordering code. The live board DT may need
correction if its OPP masks or regulator model differ from that upstream policy.

## Operating temperature clarification

For the industrial grade, -40 to +105 C is the qualified **silicon junction**
range. ASUS's -20 to +60 C specifies **ambient** operating conditions for the
PE100A product. The board's reported current policy is an 80 C passive trip,
90 C critical trip, and 2 C hysteresis. These software thresholds are deliberately
below the chip's grade ceiling; they are not alternative silicon ratings and
should not be raised to 105 C on that basis. Confirm the passive cooling binding
actually provides a functioning cooling device when cpufreq is unavailable.
An idle reading of 33 C leaves no quantified sustained-load thermal headroom.

## Manageable assessment stages

1. **Identify the unit, without changing it.** Save current boot identity,
   kernel, DTB hash/model/compatible and SoC revision. Recover full package/BOM
   identification or an already available bootloader grade report. If grade
   decoding requires fuse data, first locate the exact i.MX8MQ reference-manual
   field and software decoder for this revision; collect only the necessary
   read-only field, not a broad OTP dump. Never program a fuse.
2. **Reconcile software with hardware.** Inspect the live CPU OPP nodes,
   status/`opp-supported-hw`, CPU supply phandle, actual regulator provider and
   constraints, cpufreq driver availability/blacklists, clock parents/dividers,
   and current clock/regulator summaries. Distinguish Hz in OPP/clock data from
   kHz in cpufreq. Record whether 1.5 GHz is merely present, filtered out, or
   actively offered. Do not enable a driver as part of inventory.
3. **Establish the stock thermal baseline.** In a later assessment, first verify
   sensor plausibility/calibration, thermal trips and cooling-device bindings.
   Capture ambient and junction temperatures, clock rate, voltage where
   observable, throttling and errors during idle and a bounded stock workload.
   Use the actual grade's junction limit with measurement margin; the ASUS
   ambient limit and a thermal shutdown trip are different quantities.
4. **Decide whether there is a supported improvement.** A 1.3 GHz HZ part is
   already at its rated maximum when running at 1.3 GHz. A verified JZ part
   might support 1.5 GHz at the SoC level, but board supply, voltage transitions,
   cooling and software still need qualification. A theoretical 1.3-to-1.5 GHz
   increase is 15.4% clock gain; workload speedup can be smaller. Above the
   confirmed grade is experimental overclocking with no supported headroom
   established here. A PLL accepting a setting or a short successful run does
   not establish long-term reliability.

The next useful deliverable is the read-only identity/OPP/voltage/thermal
inventory from stages 1–2. No new OPP values or PMIC settings are proposed by
this note.
