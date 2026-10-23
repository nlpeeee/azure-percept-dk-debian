# Bounded Percept CPU DVFS qualification

## Current execution order

On 21 October the user requested direct 1.5 GHz testing after the successful
rated smoke test. The long rated suite was interrupted by request, not by a
correctness failure. The subsequent user instruction selects 60 seconds each
at 800, 1300 and 1500 MHz, with soak testing deferred. Longer suites below
are optional qualification and do not block this
experiment. Keep the 1.0 V target, existing thermal limits and cleanup cap.

The local runner is `experiments/percept-cpu-tests/run-cpu-test.sh`. Its default
action and `--help` print usage without changing anything. Installation, enabling
DVFS/overclock OPPs and running tests are separate device operations performed by
the parent task. This work package made no device connection or device changes.

## Prerequisites

Use the approved voltage contract and a working shared CPUfreq `policy0` on
`6.12.113+deb13-arm64`. Available frequencies must include the explicitly requested
rate and the policy must offer `performance`. The runner never creates an OPP,
removes fuse masks, writes voltage, loads a module, changes boot configuration or
reboots. 1500 MHz is an explicit overclock and requires `--allow-overclock` plus
an already installed candidate exposing that OPP. A successful test does not
establish rated operation or electrical headroom.

Run as root with `stress-ng`, `setsid`, GNU `timeout`, util-linux `dmesg` supporting
`--follow-new`, and standard shell tools. Mixed tests also require `ping`. Mount
debugfs beforehand: the runner requires clock, regulator and GPIO summaries and
at least one readable thermal sensor. Supply the current boot ID explicitly.
Keep an independent console and the parent task's approved rollback available.
Do not run another frequency owner or another instance simultaneously.

Each invocation requires a new output directory, explicit kHz and an integer
duration from 1 to 3600 seconds. Use a local output filesystem with enough space
for per-second telemetry. Mixed storage uses a private directory under the
explicit temp parent; choose disposable storage with at least 128 MiB free.
The hdd stressor is limited to one worker and 64 MiB, and the VM stressor to one
64 MiB worker. The stressor directory is removed on an ordinary/trapped exit;
a power loss or SIGKILL can leave it behind. Output logs are retained.

## Stages

The adjacent `test-suite.sh` orchestrates the stages, creates a new directory per
stage, records progress/results in `suite.log`, stops at the first failure and
never reboots. Supply `--suite smoke|rated|oc1500`, `--boot-id`, `--output-root`,
`--network` and `--temp-parent` explicitly. Its default is help. The OC suite
also requires `--allow-overclock`. For example, after installing the reviewed
scripts together on the device:

```sh
sh ./test-suite.sh --suite smoke --boot-id BOOT --output-root NEW_LOG_ROOT \
  --network NETWORK_HOST --temp-parent TEST_STORAGE
```

Smoke runs three five-second stages: 800 MHz CPU, 1300 MHz mixed, then 800 MHz
idle. Review these before starting `--suite rated`. Rated runs 15 minutes at
800 MHz, 15 minutes at 1300 MHz, then fifteen pairs of 30 seconds idle at 800 MHz
and 30 seconds mixed at 1300 MHz. That is 45 minutes of stage time in total.
The final 15 minutes alternate idle/load and include network/storage checks
during each mixed stage. Idle retains telemetry, thermal stops, policy control
and kernel-error monitoring but launches only a bounded sleep, without CPU
stress. Initial network checks run in every mixed stage, including the short
smoke test. Setup, network prechecks, cleanup and logging add wall-clock time.

`--suite oc1500 --allow-overclock` runs the 1/5/30-minute CPU stages followed by
the 60-minute mixed stage sequentially: 96 minutes of stage time. The suite
does not pause for manual review between passing stages; use individual runner
invocations below when separate approval/review between OC stages is required.
All suites stop on a failed stage. INT/TERM/HUP forwards TERM to the active
runner and waits for its workload termination and 1300 MHz cap before the
orchestrator exits. SIGKILL cannot be forwarded. Inspect the final stage's
`events.log` to confirm cleanup actually succeeded.

Replace `BOOT`, `NEW_LOG_DIR`, `TEST_STORAGE` and `NETWORK_HOST` before use. The
network host must be an explicitly chosen reachable peer; ICMP verifies basic
reachability, not bandwidth or application traffic.

```sh
./run-cpu-test.sh --frequency-khz 800000 --duration-seconds 900 \
  --boot-id BOOT --output NEW_LOG_DIR
./run-cpu-test.sh --frequency-khz 1300000 --duration-seconds 900 \
  --boot-id BOOT --output ANOTHER_NEW_LOG_DIR
```

Then alternate 800 MHz idle and 1300 MHz mixed load for 15 minutes total using
thirty sequential 30-second invocations, each with a distinct output directory.
The rated suite automates this as described above. Stop immediately if an
invocation fails. This tests transitions between workload stages; it is not a
high-rate transition torture test. Inspect voltage selector,
clock and temperature evidence before progressing. The runner caps at 1300 on
each exit, so a subsequent 800 MHz stage starts from a cap, not a restored OC.

Only after the rated stages pass, run the explicitly approved 1500 MHz candidate
for 60 seconds, then 300 seconds, then 1800 seconds, reviewing each result before
starting the next. Use `--allow-overclock` on every invocation. Follow with:

```sh
./run-cpu-test.sh --frequency-khz 1500000 --duration-seconds 3600 \
  --allow-overclock --workload mixed --network NETWORK_HOST \
  --temp-parent TEST_STORAGE --boot-id BOOT --output NEW_LOG_DIR
```

All load stages use four CPU workers, `--cpu-method all`, `--verify` and bounded
stress-ng timeouts. Mixed adds the bounded VM/storage stressors and a network
check roughly every ten seconds. Durations describe workload time, excluding
preflight and cleanup. Do not automatically proceed from a failed stage.

## Stop behavior and evidence

At or above 80000 mC on any reported sensor, malformed/missing temperatures,
changed boot ID, a new kernel warning/error, failed workload or network check,
failed kernel monitor, or exceeded deadline, the run fails. INT/TERM/HUP also
fail. Cleanup terminates only the process groups started by this invocation,
then lowers policy minimum if necessary and caps maximum at 1300000 kHz.
It never restores 1500000 in a trap. A normal successful exit also leaves that
cap. The governor remains `performance`; a prior governor is not restored.
Initial clock acquisition must match the request exactly. Subsequent actual
clock and cooling changes are logged for review rather than classified as
workload correctness failures: throttling can invalidate a claimed OC pass.

The loop samples approximately once per second; a bounded network check can
delay a sample by up to four seconds. Termination allows one second grace per
owned process group. This shell monitor cannot protect against a hung kernel,
SIGKILL, power loss, or failed sysfs writes, and cannot replace hardware thermal
protection or an independent watchdog. A cleanup-cap failure is prominently
logged and returns failure. The runner does not change the installed thermal
trips. Missing CPU cooling registration remains a qualification failure even
if this emergency cap works.

`events.log` records requested kHz, actual `arm_a53_core` Hz, policy bounds,
reported current kHz, thermal samples, boot ID and outcome. `power-state.log`
records full regulator/GPIO summaries and cooling states. These are framework
and selector readings, not independent clock/rail measurements. `stress-ng.log`
contains correctness failures and metrics; `new-kernel-errors.log` captures new
warning-or-higher messages without clearing the kernel log. Historical errors
remain in `dmesg-before.log`. Preserve every directory, ambient conditions,
candidate configuration/hash, cooling arrangement, input power measurements
and any reset/console evidence. A reset interrupts logging, so absence of an
error message does not establish a pass. Short tests also do not establish
long-term stability or the absence of silent corruption.

## Local checks

```sh
python experiments/percept-cpu-tests/test_runner.py
python experiments/percept-cpu-tests/test_suite.py
```

The tests run syntax/help/input checks and execute the actual cap and telemetry
helpers against private temporary files. They check lowering an OC cap, retaining
an 800 MHz minimum, the 80 C boundary, invalid sensor data and new kernel errors.
They do not execute stress-ng or touch real sysfs. Suite fixtures verify exact
stage sequences/durations, distinct log directories, stop-on-failure and the
explicit OC flag. On POSIX systems they also check signal forwarding with a fake
runner and execute the actual process-group cleanup helper against an owned
fixture group while preserving an unrelated process. Those two tests skip on
Windows. Actual governor/OPP behavior, cleanup on workload failures and thermal
responses still require the parent's bounded on-device smoke tests before the
long stages. On Windows pass `--shell "C:/Program Files/Git/usr/bin/sh.exe"`.
