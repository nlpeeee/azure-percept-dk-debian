# M0 spikes: can the build run rootless on WSL2?

Run 2026-10-21 on Debian 13 (WSL2, kernel 6.18, mke2fs 1.47.2, debootstrap 1.0.141, qemu 10.0).
Nothing here touched a board.

| Question | Result |
|---|---|
| Arm64 emulation (binfmt `qemu-aarch64`, flags `POF`) | **Works.** Enabled by installing `qemu-user-static` (systemd on). |
| Read Microsoft's `.raw` without root or loop devices | **Works.** `sfdisk -J` for offsets, `mdir/mcopy -i image@@offset` for the EFI partition, `debugfs -R ... "image?offset=N"` for the ext4 partition. |
| Stock kernel hash | `debugfs dump /boot/vmlinuz` gives a 36,620,232-byte file with sha256 `fec6f292e734ab81c056a28ab0c3940ec7f00fcd39cec417cac9da52bb3f7ef2` - exactly the pinned value. `pe100.dtb` sha `629ff5e7...` also matches. The image's `System.map` and `config` are in the same directory. |
| Does the stock kernel fit the 11 MiB factory ESP? | **No** (36.6 MB). The 64 MiB "layout v2" ESP is required for the image path (stock kernel + launcher ~5 MB + shim/GRUB ~2 MB + DTBs ~0.1 MB fits easily). The factory EFI partition's FAT volume serial is a constant of Microsoft's image (`8AB1-C6BE`), not specific to one board. | <!-- scrub-ok: Microsoft image constant -->
| ext4 features GRUB 2.03 can read | Microsoft's root fs: `has_journal ext_attr resize_inode dir_index filetype extent 64bit flex_bg sparse_super large_file huge_file dir_nlink extra_isize metadata_csum`. Debian 13's `mke2fs` default adds `orphan_file` and `metadata_csum_seed`; with `-O ^orphan_file,^metadata_csum_seed` the feature list is **identical** to Microsoft's. Use `-b 4096` explicitly (small images default to 1 KiB blocks). **Still to confirm on hardware** that GRUB reads it. |
| Populate ext4 rootless with root ownership | **Works:** `unshare -Ur mke2fs -d tree ...` records every file as uid/gid 0. |
| Reproducible ext4 image | **Works:** with a fixed UUID, `-E hash_seed=` and `E2FSPROGS_FAKE_TIME`, two builds are byte-identical. |
| Rootless `debootstrap --foreign` with one user id | **Fails** (`tar: Cannot change ownership to uid 0, gid 42`). Needs `newuidmap`/`newgidmap` from `uidmap`; `percept doctor` checks for it. |
| Full rootless arm64 trixie build (`uidmap` installed) | **Works, no errors or warnings.** Stage 1 (`--foreign`, ~14 s) and stage 2 (under qemu-user in a chroot, ~3 min) with `unshare --map-root-user --map-auto --mount [--pid --fork]`; stage 2 binds the host `/dev` and mounts `/proc` inside that private namespace (nothing leaks to the host). Result: 299 MB, `uname -m` aarch64, all system users created. Host-side the files carry mapped ids (e.g. `/etc/shadow` is 1000:100041). |
| Pack that tree into ext4 | **Works, ~1 s for a 1 GiB image**, when `mke2fs -d` runs in the *same* `--map-root-user --map-auto` namespace: ids map back to 0/42 etc., setuid bits kept (`/usr/bin/passwd` 4755), `e2fsck` clean, features identical to Microsoft's. |

## Consequences

- Prerequisites: the packages `doctor` lists, including `uidmap`. No sudo is needed after that.
- The whole image-composition path (debootstrap, second stage, `mke2fs -d`) runs unprivileged on WSL2; always use the same `unshare --map-root-user --map-auto --mount` namespace for every step that touches the tree.
- Layout v2 (64 MiB ESP with the stock kernel on it) is confirmed necessary, not optional, for the image path.
- Not yet proven: that GRUB 2.03 on the board reads this ext4, that the qemu-built tree boots, and that `systemd` units behave the same as in the board-native build. Those need hardware (M5).
