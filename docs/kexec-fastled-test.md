# Short LED checkpoint test — final checkpoint reached, stock recovery

Prepared 21 October 2026 for `percept-fastled-20261021-01`.
Source boot: `3dd4a891-c0a7-4e44-b31e-ea7aa9772e33`, kernel `5.4.3-26.cm1`.

## Executed result

The user authorized the test and it ran on 21 October 2026. Reboot was requested
at 06:34:39 UTC (07:34:39 London); the final acknowledged execution-status record
was `value_2` at 06:34:56.885765 UTC. The observer reported **all 1 → 2 → 5 flash
groups**. This establishes CP3 for the first time: verification succeeded and
purgatory returned into the final entry stub. It still does not prove the final
branch executed or Linux began running.

SSH returned by 06:39:38 UTC with stock kernel `5.4.3-26.cm1`, new boot ID
`11e9d07c-3e61-45a6-a2c5-a064a3a5dbe2`, and no `percept_kexec_test` marker.
Reset reason read `0x2`; the recorded watchdog counter was `0x12` (no matching
pre-test counter was captured, so no delta is asserted). The one-shot hook was
archived on the board and removed; no kexec modules remained loaded. No manual
power cycle was requested or reported during this test.

The shorter delays allowed observation of the final checkpoint. They did not
produce a usable marked kernel boot or prove the cause/location of the later
stall. The next discriminator should observe Linux entry/early startup rather
than repeat this same jump. Evidence includes `observer-result.json`,
`post-test-boot.txt` and `receiver.jsonl` in the PC evidence directory below.

The preparation and execution instructions below describe this completed test;
its bundle and receiver are tied to the old source boot and must not be re-armed.

## What changed

The deployed purgatory had a full `0x1000000` busy loop per delay unit and six
dark units before AND after each checkpoint. The sequence consumed 52 units;
using the earlier observed five seconds per unit gives approximately 260 seconds.
This could itself exhaust the i.MX hardware's 128-second countdown. The watchdog
theory is still unproven; userspace timeout reports of 300/600 seconds did not
establish that much unattended hardware time.

The rebuilt version uses `0x100000`, no leading gap and three extra dark units
after each group: 25 units total. Expected pulses are about 0.31 seconds and the
combined signal overhead about 7.8 seconds. These are estimates from the earlier
observation, not a new calibration; SHA256 and relocation time are additional.
Invalid pulse counts return before MMIO; a zero gap is rejected at build time to
prevent counter underflow. No call/return ABI bug was found in the prior code.

The kernel, module pair, checksum verification and watchdog configuration were
not changed. The previous disarmed shutdown hook was archived and removed.

## Verification completed

- Built from the retained clean kexec-tools 2.0.25 archive in a separate directory.
- Ran the actual LED assembly in userspace against anonymous fake-MMIO pages:
  x18–x29 preservation, return path, count rejection, unrelated GPIO/mux/gate
  bits and final LED-off state passed. This did not touch physical GPIO.
- Inspected native disassembly: delay constant `0x100000`, no leading loop,
  three-unit trailing gap; Linux arguments are loaded after the final helper.
- Captured a new bundle using this boot's live FDT and a unique command-line
  marker. ELF-symbol-based checks verified the exact LED function, kernel/DTB
  pointers, zero UART sink, `skip_checks=0` and SHA256 over both padded segments.
- Loaded the exact arch/core pair and bundle with `execute=0`, observed status
  `0` and trigger `N`, then unloaded both modules successfully.
- All 11 hook check-only records were acknowledged by the PC. No hook installed,
  no trigger written, no reboot requested; source boot ID unchanged.

Bundle SHA256: `3742af164bd21b6d284f968441b6c157b628ae2a96b41de2ea157a3b2b060d39`.
Purgatory ELF SHA256: `bfe2303f3cbd06918eef27bddb1a3e331579931059cf74845c1542a179bece4d`.
kexec executable SHA256: `efc62bfd366f5d5da7da35a36418ef4b7059cfca0cf79ca85514c84df1a242b5`.

## Prepared test configuration (historical)

Prepared board directory: `<LOCAL_PATH>/percept-fastled-20261021-01`.
Build directory: `<LOCAL_PATH>/fastled-20261021-01/kexec-tools-2.0.25`.
PC evidence: `sources/firmware-audit/fastled-20261021-01/`.
UDP receiver started on PC `<HOST_IP>:6666`, PID 30076, for this experiment
and source boot ID; stopped after the completed test. Do not reuse the PID.
Its successful check-only and execution records are in `receiver.jsonl`.

When the observer is watching or recording, recheck the source boot and asset
hashes, run the staged hook's `--check` with the matching receiver, then install
the staged hook as `/usr/lib/systemd/system-shutdown/90-percept-led-execution`
and invoke an ordinary reboot. These are the remaining execution steps; they
have not been performed. If the board has rebooted meanwhile, capture a fresh
bundle with `prepare-fastled-test.sh` using a new experiment suffix and boot ID;
do not relabel an old FDT bundle.

Watch for **1 flash → checksum interval → 2 flashes → short gap → 5 flashes**.
Record elapsed time from the first flash if possible. The first group has no
intentional leading dark gap. The old kernel may take time to shut down first.

- Only 1: reached purgatory; checksum work/failure, a fault or reset before CP2.
- 1 then 2: checks passed; final pre-branch checkpoint still not observed. Inspect
  the CP2 return/printf path and elapsed time before another test.
- 1 then 2 then 5: reached the final checkpoint before entry/DTB register loads
  and `br x17`. This does not itself prove that Linux executed. If there is no
  marked boot, the next discriminator is an early-kernel entry marker.
- SSH returns with the unique command-line marker and a new boot ID: same-kernel
  handoff succeeded; proceed to the prepared Debian diagnostic workflow.

Allow the known delayed watchdog recovery. Check the next boot ID/cmdline and
remove the now-disarmed hook after the attempt. USB recovery remains the existing
fallback. No UART or watchdog reconfiguration is required for this test.
