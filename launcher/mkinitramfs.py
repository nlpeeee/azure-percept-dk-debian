#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Assemble the launcher initramfs (newc cpio, gzip) reproducibly.

Run inside the arm64 builder chroot, where ``ldd`` can resolve the libraries of
the dynamic programs (kexec, dropbear, mke2fs, ...). Output depends only on its
inputs: members are sorted, timestamps and ownership are fixed, gzip carries no
mtime, so identical inputs give a byte-identical archive.

    mkinitramfs.py --output launcher.cpio.gz --init launcher/init --busybox /bin/busybox \
        --binary /usr/sbin/dropbear:usr/sbin/dropbear --file SRC:DEST[:MODE] --symlink LINK:TARGET
"""
import argparse
import gzip
import hashlib
import json
import re
import stat
import struct
import subprocess
import sys
from pathlib import Path

MAX_SIZE = 8_000_000          # keep well inside the 11 MiB factory EFI partition
REQUIRED_APPLETS = {
    "sh", "init", "mount", "umount", "mkdir", "cat", "sleep", "ip", "timeout", "uname", "reboot",
    "readlink", "tr", "head", "grep", "sync", "blockdev", "findfs", "udhcpc", "insmod", "rmmod",
    "cp", "chmod", "env", "sha256sum", "cpio",
}


def elf_machine(data):
    if data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("not a 64-bit little-endian ELF")
    return struct.unpack_from("<H", data, 18)[0]


def check_arm64(path):
    data = path.read_bytes()
    if elf_machine(data) != 183:
        raise ValueError("not an ARM64 ELF: %s" % path)
    return data


def is_static(data):
    offset = struct.unpack_from("<Q", data, 32)[0]
    size, count = struct.unpack_from("<HH", data, 54)
    return not any(struct.unpack_from("<I", data, offset + n * size)[0] == 3 for n in range(count))  # PT_INTERP


def libraries(path):
    out = subprocess.check_output(["ldd", str(path.resolve())], text=True)
    return sorted(set(re.findall(r"(?:=>\s+)?(/[^\s()]+)", out)))


def member_name(text):
    name = text.lstrip("/")
    parts = name.split("/")
    if not name or any(p in ("", ".", "..") for p in parts) or not re.fullmatch(r"[A-Za-z0-9_./+-]+", name):
        raise ValueError("unsafe archive path: %r" % text)
    return name


def split_src_dest(text, default_dest):
    src, sep, dest = text.partition(":")
    if not sep:
        if not default_dest:
            raise ValueError("expected SRC:DEST in %r" % text)
        dest = str(Path(src).resolve())
    return Path(src), member_name(dest)


def newc(entries):
    """entries: sorted list of (name, mode, data, rdev_major, rdev_minor)."""
    out = bytearray()
    for ino, (name, mode, data, major, minor) in enumerate(entries + [("TRAILER!!!", 0, b"", 0, 0)], 1):
        nm = name.encode("ascii") + b"\0"
        fields = [ino, mode, 0, 0, 1, 0, len(data), 0, 0, major, minor, len(nm), 0]
        out += ("070701" + "".join("%08x" % f for f in fields)).encode("ascii")
        out += nm
        out += bytes((-len(out)) % 4)
        out += data
        out += bytes((-len(out)) % 4)
    return bytes(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--init", required=True, type=Path)
    ap.add_argument("--busybox", required=True, type=Path)
    ap.add_argument("--binary", action="append", default=[], metavar="SRC[:DEST]",
                    help="dynamic ARM64 program; its ldd libraries are added")
    ap.add_argument("--static-binary", action="append", default=[], metavar="SRC:DEST")
    ap.add_argument("--file", action="append", default=[], metavar="SRC:DEST[:MODE]")
    ap.add_argument("--symlink", action="append", default=[], metavar="LINK:TARGET")
    ap.add_argument("--authorized-keys", type=Path, help="optional keys baked in for rescue mode")
    ap.add_argument("--require-applet", action="append", default=[])
    ap.add_argument("--manifest", type=Path)
    args = ap.parse_args(argv)

    busybox = check_arm64(args.busybox)
    if not is_static(busybox):
        raise ValueError("busybox must be a static binary")
    applets = set(subprocess.check_output([str(args.busybox.resolve()), "--list"], text=True).split())
    missing = (REQUIRED_APPLETS | set(args.require_applet)) - applets
    if missing:
        raise ValueError("busybox lacks applets: %s" % ", ".join(sorted(missing)))
    subprocess.run([str(args.busybox.resolve()), "sh", "-n", str(args.init)], check=True)

    members = {}
    sources = {}

    def add(name, mode, data=b"", major=0, minor=0, source=None, replace=False):
        if name in members and not replace:
            return
        parent = str(Path(name).parent)
        if parent != ".":
            add(parent, stat.S_IFDIR | 0o755)
        members[name] = (name, mode, data, major, minor)
        if source is not None:
            sources[name] = source

    for d in ("bin", "sbin", "dev", "etc", "proc", "sys", "run", "tmp", "root", "esp", "target", "lib/percept"):
        add(d, stat.S_IFDIR | (0o1777 if d == "tmp" else 0o755))
    add("bin/busybox", stat.S_IFREG | 0o755, busybox, source=str(args.busybox))
    add("bin/sh", stat.S_IFLNK | 0o777, b"busybox")
    add("init", stat.S_IFREG | 0o755, args.init.read_bytes().replace(b"\r\n", b"\n"), source=str(args.init))
    add("dev/console", stat.S_IFCHR | 0o600, major=5, minor=1)
    add("dev/null", stat.S_IFCHR | 0o666, major=1, minor=3)
    if args.authorized_keys:
        add("etc/percept-launcher/authorized_keys", stat.S_IFREG | 0o600, args.authorized_keys.read_bytes(),
            source=str(args.authorized_keys))

    for text in args.binary:
        src, dest = split_src_dest(text, True)
        add(dest, stat.S_IFREG | 0o755, check_arm64(src), source=str(src))
        libs = libraries(src)
        if not libs:
            raise ValueError("%s has no dynamic dependencies (use --static-binary)" % src)
        for lib in libs:
            add(lib.lstrip("/"), stat.S_IFREG | 0o755, check_arm64(Path(lib)), source=lib)
    for text in args.static_binary:
        src, dest = split_src_dest(text, False)
        data = check_arm64(src)
        if not is_static(data):
            raise ValueError("%s is not static" % src)
        add(dest, stat.S_IFREG | 0o755, data, source=str(src))
    for text in args.file:
        body, sep, mode = text.rpartition(":")
        if not sep or not re.fullmatch(r"[0-7]{3,4}", mode):
            body, mode = text, "0644"
        src, dest = split_src_dest(body, False)
        add(dest, stat.S_IFREG | int(mode, 8), src.read_bytes(), source=str(src), replace=True)
    for text in args.symlink:
        link, sep, target = text.partition(":")
        if not sep or not re.fullmatch(r"[A-Za-z0-9_./+-]+", target):
            raise ValueError("expected LINK:TARGET in %r" % text)
        add(member_name(link), stat.S_IFLNK | 0o777, target.encode("ascii"), replace=True)

    entries = [members[k] for k in sorted(members)]
    blob = gzip.compress(newc(entries), compresslevel=9, mtime=0)
    if len(blob) > MAX_SIZE:
        raise ValueError("archive too large: %d > %d" % (len(blob), MAX_SIZE))
    args.output.write_bytes(blob)
    manifest = {
        "sha256": hashlib.sha256(blob).hexdigest(),
        "size": len(blob),
        "members": {n: hashlib.sha256(members[n][2]).hexdigest() for n in sorted(members) if stat.S_ISREG(members[n][1])},
    }
    if args.manifest:
        args.manifest.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print("%s  %d bytes, %d members" % (manifest["sha256"], len(blob), len(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
