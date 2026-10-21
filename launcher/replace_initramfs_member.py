#!/usr/bin/env python3
"""Replace one regular file in a gzip newc initramfs, keeping every other entry.

Used to update the launcher's init after the Bookworm build host was replaced:
all other members (BusyBox, kexec, modules, libraries, device nodes) stay
byte-identical, in their original order and with their original metadata.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

FIELDS = 13


def parse(data):
    entries, offset = [], 0
    while True:
        if data[offset:offset + 6] != b"070701":
            raise ValueError("not a newc archive at offset %d" % offset)
        fields = [int(data[offset + 6 + 8 * i:offset + 14 + 8 * i], 16) for i in range(FIELDS)]
        namesize, filesize = fields[11], fields[6]
        name_start = offset + 110
        name = data[name_start:name_start + namesize - 1].decode("ascii")
        data_start = name_start + namesize
        data_start += (-data_start) % 4
        body = data[data_start:data_start + filesize]
        offset = data_start + filesize
        offset += (-offset) % 4
        entries.append([name, fields, body])
        if name == "TRAILER!!!":
            return entries


def build(entries):
    out = bytearray()
    for name, fields, body in entries:
        fields = list(fields)
        fields[6] = len(body)
        encoded = name.encode("ascii") + b"\0"
        fields[11] = len(encoded)
        out += b"070701" + "".join("%08x" % f for f in fields).encode("ascii") + encoded
        out += bytes((-len(out)) % 4)
        out += body
        out += bytes((-len(out)) % 4)
    return bytes(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("member")
    parser.add_argument("replacement", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("refusing to overwrite " + str(args.output))
    entries = parse(gzip.decompress(args.archive.read_bytes()))
    matches = [e for e in entries if e[0] == args.member]
    if len(matches) != 1 or (matches[0][1][1] & 0o170000) != 0o100000:
        raise SystemExit("member must be exactly one regular file: " + args.member)
    old = matches[0][2]
    matches[0][2] = args.replacement.read_bytes()
    raw = build(entries)
    # Round trip: every other member must be unchanged.
    again = parse(raw)
    for (n1, f1, b1), (n2, f2, b2) in zip(entries, again):
        assert n1 == n2 and b1 == b2 and f1[:6] + f1[7:11] == f2[:6] + f2[7:11]
    args.output.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    print(json.dumps({
        "member": args.member, "entries": len(entries),
        "old_sha256": hashlib.sha256(old).hexdigest(),
        "new_sha256": hashlib.sha256(matches[0][2]).hexdigest(),
        "output": str(args.output), "output_bytes": args.output.stat().st_size,
        "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, indent=2))


if __name__ == "__main__":
    main()
