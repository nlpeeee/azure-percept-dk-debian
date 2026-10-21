#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage CPU runtime files into a Debian root tree; no reboot or hardware access."""
import argparse
import hashlib
import json
from pathlib import Path

FILES = {
    "cpu-policy.sh": ("usr/lib/percept/cpu-policy.sh", 0o755),
    "cpufreq-load-guard": ("usr/lib/percept/cpufreq-load-guard", 0o755),
    "init-top-cpu": ("etc/initramfs-tools/scripts/init-top/00-percept-cpu", 0o755),
    "initramfs-hook": ("etc/initramfs-tools/hooks/percept-cpu", 0o755),
    "percept-cpu.conf": ("etc/modprobe.d/percept-cpu.conf", 0o644),
    "percept-cpu-policy.service": ("etc/systemd/system/percept-cpu-policy.service", 0o644),
}

def stage(root, profile):
    if profile not in ("unchanged", "rated", "oc1500"):
        raise ValueError("invalid CPU profile")
    if profile == "unchanged":
        return []
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("root must be a directory")
    # Reject an existing symlink escaping the target (e.g. /etc -> host /etc).
    def destination(rel):
        p = root / rel
        p.resolve().relative_to(root)
        return p
    targets = list(FILES.values()) + [("etc/percept-cpu/enable-cpufreq", 0o644),
        ("etc/percept-cpu/max-khz", 0o644),
        ("etc/systemd/system/multi-user.target.wants/percept-cpu-policy.service", 0o644),
        ("usr/lib/percept/cpufreq-load-guard", 0o755)]
    for rel, _ in targets:
        destination(rel)
    lib = destination("lib")
    if lib.exists() and not lib.is_symlink():
        destination("lib/percept/cpufreq-load-guard")
    link = destination("etc/systemd/system/multi-user.target.wants/percept-cpu-policy.service")
    if link.is_symlink():
        if link.readlink() != Path("../percept-cpu-policy.service"):
            raise ValueError("unexpected existing CPU policy enablement: " + str(link))
    elif link.exists():
        raise ValueError("unexpected existing CPU policy enablement: " + str(link))
    records = []
    def put(rel, data, mode):
        p = destination(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        p.chmod(mode)
        records.append({"path": rel, "mode": oct(mode), "sha256": hashlib.sha256(data).hexdigest()})
    here = Path(__file__).resolve().parent
    for name, (rel, mode) in FILES.items():
        put(rel, (here/name).read_bytes().replace(b"\r\n", b"\n"), mode)
    # The modprobe rule uses /lib/percept in both initramfs and real root.
    # /lib is usr-merged on stock Debian 13.
    lib = destination("lib")
    if not lib.exists():
        lib.symlink_to("usr/lib", target_is_directory=True)
    elif not lib.is_symlink():
        put("lib/percept/cpufreq-load-guard", (here/"cpufreq-load-guard").read_bytes().replace(b"\r\n", b"\n"), 0o755)
    put("etc/percept-cpu/enable-cpufreq", b"voltage-contract-approved-v1\n", 0o644)
    put("etc/percept-cpu/max-khz", ("1500000\n" if profile == "oc1500" else "1300000\n").encode(), 0o644)
    link = destination("etc/systemd/system/multi-user.target.wants/percept-cpu-policy.service")
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() and link.readlink() == Path("../percept-cpu-policy.service"):
        pass
    elif link.exists() or link.is_symlink():
        raise ValueError("unexpected existing CPU policy enablement: " + str(link))
    else:
        link.symlink_to("../percept-cpu-policy.service")
    return records

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--profile", required=True, choices=("unchanged", "rated", "oc1500"))
    parser.add_argument("--allow-live-root", action="store_true", help="only inside the target arm64 chroot")
    args = parser.parse_args()
    if args.root.resolve() == Path("/").resolve() and not args.allow_live_root:
        parser.error("use an offline target root or --allow-live-root inside its chroot")
    print(json.dumps({"profile": args.profile, "files": stage(args.root, args.profile)}, indent=2))

if __name__ == "__main__":
    main()
