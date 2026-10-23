# Turnkey, publishable Percept DK installer

## Context

Board 1 was converted to Debian 13 trixie by hand: flash Bookworm, add a stock-kernel launcher + kexec module,
rescue-install the rootfs. It works (GPU, VPU, USB-C host, Wi-Fi, BT, thermal, 4 GiB, camera) but isn't reusable:
the launcher hard-codes board 1's MAC/IP/devices, the trixie tarball carries board 1's SSH host keys, two
authorised keys and default passwords, `stage-b.sh` mixes generic and per-board setup (and `apt-mark hold`s the
kernel), and nothing is packaged for anyone else. Goal: a documented installer on GitHub that takes a Percept DK
to a working Debian-class system, with the user's choice of OS/kernel where the kernel meets a documented contract.

Constraints from the user: Windows + **WSL2** build host (Linux-native must also work; WSL is being installed, work
resumes after the reboot). **All per-board settings** (SSH keys/passwords, Wi-Fi SSID/PSK/country, Ethernet
DHCP/static, hostname, rescue IP, tz/locale, OS/kernel/features) are collected by a script/wizard, validated and
**injected at build time**; nothing per-board or secret is ever published. Keep the Debian kernel stock (cmdline
switches + DT fixups, no kernel patches).

## Decisions (confirmed with user)

- **Primary path:** personalised disk image built in WSL, flashed with `uuu.exe` from Windows. **Secondary:** SSH
  in-place install through launcher rescue (proven on board 1, ships first). Experimental: RAM-boot over USB.
- **Config:** TOML, `board.toml` (non-secret) + `secrets.toml`; wizard and `--from file`. (My default.)
- **Releases ship prebuilt launcher cpio + kexec `.ko`** (user choice). Preconditions before the first binary
  release: LICENSES/ texts, NOTICE.md, `kexecmod/SOURCE-OFFER.md` pointing at pinned sources, a licence review of the
  `.ko` (built against kernel.org 5.4.3 + symbols from Microsoft's stock Image; no Microsoft file may be in any
  release asset), and hash recorded in `known-hashes.toml`. Until then, build-from-source is the supported route.
- **History:** keep the one public commit, tag `legacy-bookworm`, add the scrubbed tree on top, no force-push. Scan
  the old commit for scrub-list hits first; if it leaks, ask the user before rewriting.
- **Layout v2 for the image path:** 64 MiB ESP holding the stock Image + both DTBs + launcher, so rescue survives a
  corrupt p3. The SSH path keeps the factory 11 MiB ESP. (M0 spike: measure stock Image size.)

## Architecture

One build core on the PC produces three layers:
1. **Vendor inputs** (`cache/vendor/`): fetched from Microsoft/kernel.org/NXP, hash-gated, never published.
2. **Generic artifacts** (`cache/artifacts/`): launcher cpio (all per-board behaviour comes from ESP files at runtime),
   generic rootfs tarball. No per-board data.
3. **Personal outputs** (`out/<board>/`, gitignored, named `*-PERSONAL.*`): overlay tarball, ESP file set, uuu image
   or SSH bundle.

User journey (Windows): `percept.cmd doctor` -> `fetch` -> `configure` -> `build` -> `flash` (typed
`ERASE <name>`) -> `verify`. Running board: `percept install-over-ssh`.

## CLI (Python 3.9+ stdlib + POSIX sh)

`src/percept/` package, shims `percept` / `percept.cmd`. Python runs natively on Windows (wizard, doctor, flash) and
re-execs Linux stages via `wsl.exe -d <distro> -- python3 -m percept ...` working in WSL ext4 (never drvfs; only the
final `out/` copy touches Windows). `uuu.exe` always runs Windows-side (no USB passthrough into WSL). Commands:
`doctor, fetch, configure, build [--target image|ssh-bundle|esp-only], flash, install-over-ssh, verify, recover
(enter-usb|factory-restore|reset-counter|rescue-shell), find, profile list|check`. Global: `--board --dry-run --yes
--verbose`; stages keyed by input hash (idempotent, atomic outputs); logs 0600 through a redactor; destructive steps
need typed confirmation even with `--yes`. Vendored `tomli` for <3.11; pure-Python sha512-crypt (Python 3.13 dropped
`crypt`), tested against `openssl passwd -6`.

`fetch`: downloads the MS recovery ZIP (url/size/sha256 in `vendor/vendor-manifest.toml`), streams only the needed
bytes of the 8.5 GB `.raw`, extracts p3 files rootlessly with `debugfs rdump`: stock Image (sha `fec6f292…`),
`/lib/modules/5.4.3-26.cm1`, `.config`, `System.map`, `pe100.dtb` (sha `629ff5e7…`), `fast-hab-fw.raw`
(`1f872586…`), `emmc_full.txt`; plus Linux 5.4.3, kexec-tools 2.0.25, BusyBox, dropbear, e2fsprogs, uuu 1.5.243.

## Config schema (fields, injection)

Sections: `[board]` name/hostname/timezone/locale; `[ssh]` password_auth=false, root_login=disabled|key-only,
host_keys=firstboot; `[[user]]` name/sudo/groups/authorized_keys(_file)/password_hash|password_mode;
`[network.ethernet]` dhcp|static (address, prefix, gateway, dns); `[network.wifi]` ssid/psk/country/security/hidden;
`[rescue]` net_mode/address/prefix/gateway/authorized_keys/fail_limit/grub_tries/log_receiver; `[os]` profile/mirror,
`[os.kernel]` source=distro|files|custom + image/initrd/modules/cmdline_extra, `[os.features]` gpu/vpu/usb_c_host/
camera/upper_ram/thermal, `[os.packages]`; `[storage]` layout/root_size; `[install]` method + ssh/uuu options.
Secrets accept `*_file` / `*_env`.

Validation: key types and base64, reject private-key blocks and `command=`; at least one SSH auth path (no
lockout); no default passwords (key, generated-once to `credentials.txt` 0600, or typed); static gateway in subnet;
Wi-Fi SSID bytes/PSK length/country required; RFC 1123 hostname; printable-ASCII `cmdline_extra` (<=2048 incl.
baseline); features must be supported by the profile's kernel range.

Injection map: hostname/tz/locale/users/shadow/sudoers/authorized_keys/sshd policy/Ethernet `.network`/Wi-Fi
`wpa_supplicant-wlan0.conf`+`.network`/fstab (per-build root UUID + ESP serial) -> **rootfs overlay**; rescue
net/fail_limit/kernel/initrd/cmdline/dtb_fixups -> **ESP `percept/launcher.conf`**; rescue keys -> **ESP
`percept/authorized_keys`**; GRUB tries -> `grubenv`; SSH host keys, machine-id, rescue dropbear key -> **generated
on device at first boot**. Redactor is seeded with every secret and derivative; a CI canary test asserts no secret
reaches generic artifacts or releases.

## OS / kernel profiles

`profiles/<id>/profile.toml`: rootfs source (debootstrap suite/mirror | tarball | prebuilt+hash; builder
qemu-user default), ordered chroot hooks, kernel source (distro package + pin | user files | custom), `[contract]`
(required config symbols, initramfs modules `imx2_wdt sdhci-esdhc-imx ext4`, cmdline baseline: `console=ttymxc0,115200
earlycon=ec_imx6q,0x30860000 cpuidle.off=1 clk_ignore_unused pd_ignore_unused efi=noruntime net.ifnames=0
module_blacklist=rohm_bd718x7,bd718x7_regulator,imx_cpufreq_dt cma=256M`), `[[fixup]]` entries
(upper-ram, thermal, media-gpu-vpu, usbc-extcon) with kernel-range globs and preconditions, feature matrix,
boot-confirm unit. Fixups are selected **at build time** from the kernel release and written as
`dtb_fixups=`; helpers exit 0 applied / 3 not-applicable / other fail. Stock-5.4 profiles use `fixups=[]` (6.12
bindings are wrong for the vendor driver).

Kernel updates keep working: `apt-mark hold` is replaced by an apt pin to the validated series (`6.12.*`), symlinked
`/vmlinuz` `/initrd.img`, no hash pins, plus a warn-only postinst guard for out-of-range releases.

BYO kernel (`byo-kernel`, experimental): build-time checks (arm64 Image magic, config symbols, initrd modules,
release range with `--i-understand`), runtime safety from failcount + GRUB countdown -> rescue. Matrix at release:
`debian-trixie` tested; `debian-bookworm-stock` tested legacy; BYO experimental; other distros template only.
Adding a profile is documented (copy `_template`, `profile check`, boot, `verify-boot.sh`, submit report).

## Launcher generalisation (`experiments/percept-launcher/init` -> `launcher/init`)

New optional `launcher.conf` keys (old keys remain aliases; unknown key still -> rescue): `profile`, `esp=`/`root=`
as UUID/LABEL/path (replaces `ESP_DEVICE`/`ROOT_DEVICE`), `root_fstype/opts`, optional `initrd`,
`kernel_format`, relaxed `cmdline` charset, `net_mode static|dhcp|none`, `net_if=auto` (pick by driver `igb`, not
MAC), `net_ip/prefix/gw`, `log_receiver_*` (telemetry off unless set), `fail_limit`, `rescue_console`,
`dtb_fixups` + `dtb_fixups_policy`, DT model guard. Remove constants at init lines 12-23 and the MAC loop (~117);
add `udhcpc`; rescue SSH key-only from ESP `percept/authorized_keys`; dropbear host key generated on first rescue
boot and saved to ESP. `grub.cfg.in` rendered from layout (gpt indices, kernel location, optional original Mariner
entry for in-place installs); `grubenv` exactly 1024 bytes (unit-tested).

Reproducible build: one arm64 Bookworm chroot under qemu-user (rootless via `unshare -Ur chroot`) builds BusyBox,
kexec-tools+patches, dropbear, e2fsprogs, the musl FDT helpers (incl. `percept-fdt-media`) and the kexec modules,
replacing board-native `build-launcher.sh` / `build_percept_initramfs.py` (no host-ldd glibc bake, no
`/root/...` paths, no baked keys). Fallbacks: `--builder ssh://board`, `--builder docker`.

kexec modules: inputs from `fetch`; `extract_kernel_exports.py` + `prepare_hello_probe.py` (hard asserts stay: wrong
stock build fails loudly). `.ko` pair reusable on any board with the same stock Image sha. Hash mismatch = warning;
the real gate is a load test on the board. **First task: salvage the CAAM/OCOTP sources** (only in ignored
`sources/kexec-mod` and `experiments/percept-caam/deploy-02.tar.gz`) into `kexecmod/patches/`.

## Image / install pipelines

**Image (WSL, rootless):** generic rootfs in qemu-user chroot -> apply overlay -> `mke2fs -t ext4 -d tree -U <uuid>
-O ^orphan_file,^metadata_csum_seed` (GRUB 2.03-safe; check `dumpe2fs`, untested on hardware) -> ESP via
`mkfs.vfat -F 16 -i <serial>` + `mcopy` (EFI/BOOT shim+grub from user's MS image, `boot/grub2/{grub.cfg,grubenv}`,
`pe100.dtb`, `pe100-usbc.dtb` via `strip_dtb_property.py`, stock Image in v2, `percept/{launcher.cpio.gz,
launcher.conf,failcount=0,authorized_keys}`) -> pure-Python GPT composer (`gpt.py`, sizes from `emmc_full.txt`) ->
sparse raw + generated uuu script. Per-image random ext4 UUID and ESP serial go into overlay fstab and
`launcher.conf` (replaces hard-coded `<ESP_SERIAL>`). First boot: `percept-firstboot-grow` (`sgdisk -e`, growpart,
resize2fs), `ssh-hostkeys.service`, `percept-boot-ok` (keep the fixed no-network-online version + wait-online
override).

**Flash (Windows):** `uuu.exe -lsusb` must show one device; generated script from `flash.uuu` (SDP boot
`fast-hab-fw.raw`, FB flash bootloader, FB flash `-raw2sparse all`, partconf). Recovery entry: `percept recover
enter-usb` (SSH `flagutil -wBfRequestUsbFlash -v1` + reboot, tested -> fastboot `0525:a4a5`); DIP switch positions are
**not established**: document honestly, invite contributions, never invent them. Dry-run shown first; typed confirm.

**Install-over-ssh:** `accept-new` + per-board known_hosts; `target/probe.sh` identity (stock kernel sha, pe100.dtb
sha, DT model, `uname -r`); back up ESP + GPT, hash p3 (optional full p3); push rescue set (keep Mariner GRUB entry),
reboot to rescue at configured IP (check reachability **before** wiping); `target/install.sh` (generalised
`rescue-install.sh`, same refusals) streams rootfs, restores stock Image, `arm` writes production conf; reboot, verify.

Rollback: counters/GRUB rescue, `recover reset-counter`, `factory-restore` (flash MS image via same uuu path).

## Security defaults

No default passwords; password auth off, root login disabled by default; host keys at first boot; no personal/test
keys anywhere (board-1 tarball superseded); no `StrictHostKeyChecking=no`; every mount/chroot script runs under <!-- scrub-ok: preserved security-policy prose names a forbidden option, not an executable SSH instruction. -->
`unshare --mount --propagation private` (CI greps); redaction + 0600 + canary test; docs state plainly that secure
boot protects only the first hop because the launcher kexecs an unsigned kernel.

## Repo layout and publishing

```
README.md LICENSE LICENSES/ REUSE.toml NOTICE.md SECURITY.md CONTRIBUTING.md CHANGELOG.md percept percept.cmd
src/percept/ (cli doctor fetch config schema validate profiles wsl redact tomlw sha512crypt build/{rootfs,overlay,
  esp,image,gpt,launcher,kexecmod,fixups} flash ssh_install verify recover find)  schema/  data/  vendor/
profiles/{debian-trixie,debian-bookworm-stock,byo-kernel,_template}  launcher/{init,build.sh,grub.cfg.in,
  launcher.conf.in,patches,fdt/*.c,tests}  kexecmod/  target/  board-tests/  camera/  examples/  tests/
docs/ (+ docs/lab, docs/legacy)  legacy/ (00_build_rootfs.sh 01_build_image.sh post_flash.sh flash.* config.sh)
.github/workflows/{ci,release}.yml
```

Moves: `experiments/percept-launcher/*` -> `launcher/`; `percept-{hardware,media,upper-ram}/*.c` -> `launcher/fdt/`;
`percept-trixie/{percept-boot-ok*,wait-online-override.conf}` -> `target/`; `stage-b.sh`/`build-trixie-rootfs.sh` split
into profile hooks + builder (`builder-init` kept as `native-board` fallback); `rescue-install.sh` -> `target/install.sh`;
`tools/{extract_kernel_exports,inspect_stock_modules,prepare_hello_probe}.py` -> `kexecmod/`; `strip_dtb_property.py`
-> `build/fixups.py`; `percept-hardware/{verify-boot,reboot-soak,vpu-*}.sh` -> `board-tests/`; `percept-camera/*`
-> `camera/` (keep private-namespace wrapper). Dropped: `UART/putty.log`, `pics/`, `sources/*`, other experiment
dirs, `deploy*.tar.gz`, `__pycache__`.

Licences: MIT for installer code/docs; GPL-2.0-only for launcher init (SPDX-tagged), kexec-mod/kexec-tools patches,
libfdt-linked helpers; SPDX per file + `REUSE.toml`, `reuse lint` in CI; NOTICE lists BusyBox, kexec-tools, kexec-mod,
amonakov/kexec-module, dropbear, e2fsprogs, libfdt, uuu, tomli. Name a copyright holder in LICENSE (ask user).

Clean-tree process: dev-only `tools/export-public.py` copies from an allowlist into `../publish/` (never `git add -A`,
the working tree has many uncommitted multi-agent changes) and runs a scrub scanner that fails on: MAC
`<BOARD_MAC>`, `<BOARD_IP>/<HOST_IP>`, UUID `<BOARD_UUID>`, ESP serial `<ESP_SERIAL>`, SoM serial, `<COM_PORT>`,
`<LOCAL_PATH>`, `<LOCAL_PATH>`, `<PASSWORD>`, ssh public/private key material,
`StrictHostKeyChecking=no`, files >1 MB. Rewrite `docs/debian13-reproduction.md`/`rescue-install.sh` hits. <!-- scrub-ok: preserved security-policy prose names a forbidden option, not an executable SSH instruction. -->
`.gitignore` adds `cache/ out/ boards/* *.raw *.zst *.log *.pcap secrets.toml *.key sources/ pics/ UART/`.

## Docs

Rewrite README trixie-first (current one is stale: 3 GB RAM, "kernel can't be replaced", dead-end claims);
new: quickstart-windows, install (replaces trixie-install + debian13-reproduction), configuration (generated from
schema), profiles + byo-kernel, architecture (folds boot-chain, device-tree, upper-ram, launcher/counters),
hardware-status (works: GPU etnaviv, VPU Hantro G1/G2, USB-C host-only, Wi-Fi, BT, thermal, TPM, 4 GiB, camera via
extracted MS runtime; not working: CPU DVFS, PMIC, deep idle, external RTC, AK audio; FEC unused; each row tagged
with tested kernel and "untested on board 2"), recovery + recovery-usb-mode, troubleshooting (UART/rescue/counters),
security, legal, camera, gpu-vpu. Lab notebooks -> `docs/lab/`; Bookworm flow -> `docs/legacy/`; review
`spl-authentication-review` before publishing.

## CI and tests

shellcheck, `busybox sh -n launcher/init`, ruff/py_compile, `reuse lint`, scrub scanner; pytest: config validation
(incl. no-private-key, no-lockout), profile fixup selection, sha512-crypt vs openssl, exact 1024-byte grubenv,
launcher.conf round-trip/unknown-key/charset, GPT via `sfdisk -d`, FDT helpers on synthetic DTS via `dtc`
(applied/skipped/failing), launcher simulated run (config parse + failcount) under busybox; image-composition test
(`mke2fs -d`, `mkfs.vfat`, `mcopy`, `e2fsck`, `fsck.vfat`, `dumpe2fs` must not list `orphan_file`); canary-secret
test; weekly qemu rootfs build. Release workflow: tagged source + sums; binaries only after the precondition list
above; never any Microsoft content.

## Milestones (dependency order)

- **M1 (now, no WSL):** salvage CAAM/OCOTP kexec-mod sources into patches; snapshot working launcher.
- **M2 (now):** repo skeleton, licences, REUSE, export script + scrub scanner, README rewrite, scan old public commit.
- **M3 (now):** config/profile core: schema, validator, wizard, redactor, sha512-crypt, unit tests, `doctor`.
- **M0 (after WSL):** spikes: binfmt/qemu-user, `unshare -Ur chroot`, `mke2fs -d` features, `debugfs` extraction, stock Image vs ESP size.
- **M4:** launcher generalisation + reproducible chroot build + kexec module build with hash gate.
- **M5:** qemu rootfs + overlay, image composition, first `uuu` rehearsal on a board (the key risk gate).
- **M6:** `install-over-ssh` + `install.sh`; rescue-set install for factory boards (board 1).
- **M7:** verify/soak/recovery tooling, docs complete.
- **M8:** second-board from-scratch run; three cold boots (needs a human at the power connector).
- **M9 (stretch):** multi-entry boot with one-shot next, BYO-kernel polish.

## Risks

qemu-user rootfs fidelity vs board-native tarball (diff `dpkg -l`/tree, keep `native-board` builder; trixie glibc
thread crash only affected running trixie under 5.4); emulated `.ko` bytes differ (gate on load test); `mke2fs`
features vs GRUB 2.03 (pinned flags, early rehearsal); WSL2 without binfmt/sudo (doctor prints fixes, Docker
fallback); unproven `uuu` flow and unknown DIP positions (document `flagutil` route, ask community); factory root
access undocumented (only affects SSH path); `.ko`/cpio redistribution licensing; only Debian 6.12.113 proven ("OS of
choice" = Debian-class on a kernel meeting the contract, stated in README); old public commit may leak; stock Image
may not fit ESP v2.

## Verification

Hardware, board 1 then board 2: full from-scratch `build` + `flash`, `board-tests/verify-boot.sh --vpu`,
`reboot-soak.sh`, three cold boots, rescue drill (3 failed boots -> rescue at configured IP with configured keys),
kernel-update drill (minor apt upgrade, boot-confirm hook), recovery drill (`reset-counter`, `factory-restore`).
Software: CI above, plus a clean-clone dry run on a fresh WSL2 distro following `docs/quickstart-windows.md` only,
and a final scrub-scanner pass over the export before anything is pushed.
