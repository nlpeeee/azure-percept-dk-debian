# launcher.conf reference

`percept/launcher.conf` on the EFI partition tells the launcher what to boot.
One `key=value` per line, `#` comments, no quoting. The launcher is strict: an
unknown key, a malformed line or a value it does not like sends the board to
**rescue mode** (it never guesses).

`percept` generates this file; `python percept launcher-conf --board <name>`
prints what a board would get (`--compat v2` for the planned key set).

## Keys understood by the shipped launcher ("current")

| Key | Values | Meaning |
|---|---|---|
| `mode` | `kexec` (default), `rescue` | `rescue` forces stock-kernel SSH rescue |
| `kernel` | absolute path on the root partition | e.g. `/vmlinuz` |
| `initrd` | absolute path | e.g. `/initrd.img` (mandatory today) |
| `cmdline` | `A-Za-z0-9_.,=:/+ -` only | full kernel command line, `root=UUID=...` included |
| `kernel_sha256`, `initrd_sha256` | 64 hex | optional pins (not used with distro kernels, so updates keep working) |
| `upper_ram` | `0`/`1` | expose the fourth GiB |
| `thermal_fix` | `0`/`1` | TMU sensor-cells fix |
| `media` | `none`, `gpu`, `gpu-vpu` | GPU / VPU device-tree enablement |
| `cpu_profile` | `unchanged` (default), `rated`, `oc1500` | CPU OPP profile; non-default needs PMIC and target runtime setup |
| `cpu_pmic` | `0` (default), `1` | Convert PMIC binding and connect CPUs to BUCK2; required for scaling |

## Keys planned for launcher v2 (milestone M4)

These remove the last board-specific constants from `launcher/init` (a MAC
address, two IPs, device names). The generator already emits and tests them;
the launcher will accept them in M4.

| Key | Values | Replaces / does |
|---|---|---|
| `profile` | `percept-dk` | defaults for devices, console, limits |
| `esp`, `root` | `UUID=...`, `LABEL=...`, `/dev/...` | hard-coded `mmcblk` names |
| `root_fstype`, `root_opts` | `ext4`, `ro,noload` | |
| `kernel_format` | `auto`, `Image`, `Image.gz` | |
| `net_mode` | `dhcp`, `static`, `none` | rescue network |
| `net_if` | `auto` (by driver `igb`) or a name | hard-coded MAC match |
| `net_ip`, `net_prefix`, `net_gw` | IPv4 | hard-coded rescue address |
| `log_receiver_ip`, `log_receiver_port` | IPv4, port | hard-coded telemetry receiver (off unless set) |
| `fail_limit` | 1-10 | failure counter limit |
| `rescue_console` | `ttymxc0` | |
| `dtb_fixups` | comma list, e.g. `upper-ram,thermal,media-gpu-vpu` | replaces `upper_ram`/`thermal_fix`/`media` |
| `dtb_fixups_policy` | `skip-inapplicable`, `strict` | what a fixup that does not apply means |

## Other ESP files

| File | Meaning |
|---|---|
| `percept/failcount` | `N\n`; the launcher increments it each boot, the OS's `percept-boot-ok` resets it to 0 |
| `percept/authorized_keys` | rescue-mode SSH keys |
| `percept/rescue_password_hash` | optional one-line `$6$` hash; if present, rescue mode also accepts the `root` password (dropbear password login is otherwise off) |
| `boot/grub2/grubenv` | exactly 1024 bytes; `percept_tries` counts down from 4 in GRUB, reset by `percept-boot-ok` |

CPU profiles are integrated in the launcher build. Generate these keys from
`os.cpu_profile`; see [CPU power management](cpu-power-management.md) for the
matching rootfs hook, governor ordering, qualification and rollback.
