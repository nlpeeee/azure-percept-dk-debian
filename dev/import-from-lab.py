#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One-time seed of this tree from the maintainer's lab checkout.

Copies an explicit allowlist (never a directory sweep), normalises line endings
to LF, and refuses to overwrite files that already exist unless --force is
given. After the seed this repository is the source of truth: fix files here,
not in the lab tree. Run ``dev/scrub-scan.py`` afterwards.

    python dev/import-from-lab.py --lab /path/to/lab-checkout [--force] [--dry-run]
"""
import argparse
import os
import shutil
import sys

# (lab path relative to --lab, destination relative to this repo)
ALLOWLIST = [
    # launcher
    ("experiments/percept-launcher/init", "launcher/init"),
    ("experiments/percept-launcher/build-launcher.sh", "launcher/legacy-build-launcher.sh"),
    ("experiments/percept-launcher/grub.cfg.production", "launcher/grub.cfg.production"),
    ("experiments/percept-launcher/launcher.conf.trixie", "launcher/launcher.conf.trixie"),
    ("experiments/percept-launcher/launcher.conf.rescue", "launcher/tests/fixtures/launcher.conf.rescue"),
    ("experiments/percept-launcher/launcher.conf.example", "launcher/launcher.conf.example"),
    # device-tree helpers
    ("experiments/percept-upper-ram/extend-fdt.c", "launcher/fdt/extend-fdt.c"),
    ("experiments/percept-hardware/fix-thermal-fdt.c", "launcher/fdt/fix-thermal-fdt.c"),
    ("experiments/percept-media/adapt-fdt.c", "launcher/fdt/adapt-fdt.c"),
    ("experiments/percept-media/validate-dtb.py", "launcher/fdt/validate-dtb.py"),
    # on-board scripts
    ("experiments/percept-trixie/percept-boot-ok", "target/percept-boot-ok"),
    ("experiments/percept-trixie/percept-boot-ok.service", "target/percept-boot-ok.service"),
    ("experiments/percept-trixie/wait-online-override.conf", "target/wait-online-override.conf"),
    ("experiments/percept-trixie/rescue-install.sh", "target/install.sh"),
    # profile / rootfs build inputs (to be split into hooks)
    ("experiments/percept-trixie/stage-b.sh", "profiles/debian-trixie/hooks/legacy-stage-b.sh"),
    ("experiments/percept-trixie/build-trixie-rootfs.sh", "profiles/debian-trixie/legacy-build-trixie-rootfs.sh"),
    ("experiments/percept-trixie/builder-init", "profiles/debian-trixie/native-board/builder-init"),
    ("experiments/percept-trixie/pack-trixie-rootfs.sh", "profiles/debian-trixie/native-board/pack-trixie-rootfs.sh"),
    # board acceptance tests
    ("experiments/percept-hardware/verify-boot.sh", "board-tests/verify-boot.sh"),
    ("experiments/percept-hardware/reboot-soak.sh", "board-tests/reboot-soak.sh"),
    ("experiments/percept-hardware/record-status.sh", "board-tests/record-status.sh"),
    ("experiments/percept-hardware/vpu-decode-test.sh", "board-tests/vpu-decode-test.sh"),
    ("experiments/percept-hardware/vpu-bench.sh", "board-tests/vpu-bench.sh"),
    ("experiments/percept-gpu/gles-offscreen-test.c", "board-tests/gles-offscreen-test.c"),
    # camera
    ("experiments/percept-camera/assemble-eye-runtime.sh", "camera/assemble-eye-runtime.sh"),
    ("experiments/percept-camera/percept-eye-run.sh", "camera/percept-eye-run.sh"),
    # kexec module tooling
    ("tools/extract_kernel_exports.py", "kexecmod/extract_kernel_exports.py"),
    ("tools/inspect_stock_modules.py", "kexecmod/inspect_stock_modules.py"),
    ("tools/prepare_hello_probe.py", "kexecmod/prepare_hello_probe.py"),
    ("experiments/percept-caam/test_reset.c", "kexecmod/tests/test_reset.c"),
    ("patches/kexec-tools-arm64-purgatory-led-telemetry.patch", "kexecmod/patches/optional/kexec-tools-arm64-purgatory-led-telemetry.patch"),
    ("patches/kexec-tools-arm64-purgatory-led.S", "kexecmod/patches/optional/kexec-tools-arm64-purgatory-led.S"),
    ("patches/README-kexec-tools-purgatory-led.md", "kexecmod/patches/optional/README.md"),
    # image helpers
    ("tools/strip_dtb_property.py", "src/percept/build/strip_dtb_property.py"),
    ("tools/replace_initramfs_member.py", "launcher/replace_initramfs_member.py"),
    ("tools/build_percept_initramfs.py", "launcher/legacy-build_percept_initramfs.py"),
    # legacy Bookworm flow
    ("00_build_rootfs.sh", "legacy/00_build_rootfs.sh"),
    ("01_build_image.sh", "legacy/01_build_image.sh"),
    ("post_flash.sh", "legacy/post_flash.sh"),
    ("flash.uuu", "legacy/flash.uuu"),
    ("flash.bat", "legacy/flash.bat"),
    ("copy_sources.sh", "legacy/copy_sources.sh"),
    # user-facing docs, rewritten later
    ("docs/trixie-install.md", "docs/legacy/trixie-install-lab.md"),
    ("docs/debian13-reproduction.md", "docs/legacy/debian13-reproduction-lab.md"),
    ("docs/percept-hardware-support.md", "docs/hardware-status-lab.md"),
    ("docs/percept-upper-ram.md", "docs/architecture/upper-ram.md"),
    ("docs/usb-c.md", "docs/architecture/usb-c.md"),
    ("docs/percept-device-tree.md", "docs/architecture/device-tree.md"),
    ("docs/boot-chain-status.md", "docs/architecture/boot-chain.md"),
    ("docs/camera-vision.md", "docs/camera.md"),
    ("docs/gpu-vpu-plan.md", "docs/gpu-vpu.md"),
    ("docs/percept-restore.md", "docs/recovery.md"),
    ("docs/percept-uart.md", "docs/troubleshooting-uart.md"),
    # lab notebooks
    ("docs/kexec-mod-experiment.md", "docs/lab/kexec-mod-experiment.md"),
    ("docs/kexec-caam-fix.md", "docs/lab/kexec-caam-fix.md"),
    ("docs/kexec-jump-test.md", "docs/lab/kexec-jump-test.md"),
    ("docs/kexec-fastled-test.md", "docs/lab/kexec-fastled-test.md"),
    ("docs/kexec-uart-test.md", "docs/lab/kexec-uart-test.md"),
    ("docs/kexec-staging-diagnostics.md", "docs/lab/kexec-staging-diagnostics.md"),
    ("docs/kernel-path-forward.md", "docs/lab/kernel-path-forward.md"),
    ("docs/debian-kernel-test.md", "docs/lab/debian-kernel-test.md"),
    ("docs/custom-kernel-test.md", "docs/lab/custom-kernel-test.md"),
    ("docs/boot-interface-test.md", "docs/lab/boot-interface-test.md"),
    ("docs/trixie-device-audit.md", "docs/lab/trixie-device-audit.md"),
    ("docs/boot-chain-watchlist.md", "docs/lab/boot-chain-watchlist.md"),
]

TEXT_SUFFIXES = {".sh", ".py", ".c", ".h", ".md", ".patch", ".S", ".conf", ".service",
                 ".uuu", ".bat", ".example", ".production", ".trixie", ".rescue", ""}


def is_text(path):
    with open(path, "rb") as f:
        return b"\0" not in f.read(4096)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lab", required=True, help="lab checkout (maintainer working tree)")
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    missing = skipped = copied = 0
    for src_rel, dst_rel in ALLOWLIST:
        src = os.path.join(args.lab, src_rel)
        dst = os.path.join(here, dst_rel)
        if not os.path.isfile(src):
            print("missing  ", src_rel)
            missing += 1
            continue
        if os.path.exists(dst) and not args.force:
            print("exists   ", dst_rel)
            skipped += 1
            continue
        print("copy     ", src_rel, "->", dst_rel)
        copied += 1
        if args.dry_run:
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if is_text(src):
            with open(src, "rb") as f:
                data = f.read().replace(b"\r\n", b"\n")
            with open(dst, "wb") as f:
                f.write(data)
        else:
            shutil.copyfile(src, dst)
        shutil.copymode(src, dst)
    print("copied %d, skipped %d, missing %d" % (copied, skipped, missing))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
