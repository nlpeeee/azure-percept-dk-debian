# Percept CPU and memory benchmarks after the CPU power changes

21 October 2026, after a successful reboot into Debian
`6.12.113+deb13-arm64`. Boot ID: `8a18bd6d-0f49-4e9a-8f50-45ba8397cfd9`.
The persistent policy is 800–1500 MHz, schedutil; each benchmark temporarily
locks the selected rate. Clock-framework telemetry confirmed the actual core
clock throughout each measurement. Peak reported temperature was 38 C.

| Metric | Historical Bookworm + containers | Trixie, 1.3 GHz | Trixie, 1.5 GHz | 1.5 GHz vs historical |
|---|---:|---:|---:|---:|
| CPU, four threads, events/sec | ~2,455 | 2,490.54 | 2,852.86 | +16.2% |
| Memory test, four threads, MiB/sec | ~4,423 | 4,458.96 | 5,391.95 | +21.9% |
| Memory test, one thread, MiB/sec | not recorded | 1,176.89 | 1,360.69 | — |

Within the same Trixie system, 1.5 GHz improved CPU throughput by **14.5%**
over 1.3 GHz. These are individual short runs, not a soak or statistical study.
The original memory command is not retained, so its comparison is approximate.
The 1 KiB repeated-block memory workload is cache-sensitive; it does not measure
raw DRAM bandwidth or establish a memory-clock increase.

## Commands and environment

sysbench 1.0.20, using system LuaJIT. CPU command at each fixed rate:

```sh
sysbench cpu --threads=4 --cpu-max-prime=10000 --time=60 run
```

Memory command at each rate, once with one thread and once with four:

```sh
sysbench memory --threads=4 --time=10 --memory-block-size=1K \
  --memory-total-size=100G --memory-scope=global --memory-oper=write \
  --memory-access-mode=seq run
```

The historical system ran Bookworm with Docker and several containers. The
current system is Trixie without that container workload. The paired Trixie
runs isolate the frequency change more closely than the historical comparison.
CPU and memory benchmark processes exited successfully. CPU frequency was
controlled through the stock OPP/regulator/clock drivers, not direct PLL writes.

The reusable paired runner is `experiments/percept-cpu-tests/benchmark.sh`.
It records commands, outputs, actual clock and temperature, and always restores
a 1.3 GHz cap on exit. Restart `percept-cpu-policy` after a successful run to
restore the configured dynamic maximum. Test artifacts:

* `sources/firmware-audit/cpu-power-20261021/benchmarks-01.tar.gz`
* `sources/firmware-audit/cpu-power-20261021/benchmark-results.json`
* `sources/firmware-audit/cpu-power-20261021/minute-results.json`

The three frequency correctness tests each requested 60 seconds and passed:
800 MHz / 0.9 V / peak 35 C; 1300 MHz / 1.0 V / peak 37 C;
1500 MHz / 1.0 V / peak 38 C. Supply voltages are PMIC register/framework
readbacks, not measurements at an external test point. The 1.5 GHz profile
is experimental operation above this unit's 1.3 GHz industrial rating.
