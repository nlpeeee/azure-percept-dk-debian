#!/usr/bin/env python3
"""Recover this ARM64 Image's PREL32 exports/absolute CRCs using its System.map.

Validates symbol locations and all shared CRCs against an independent stock
module-import CSV. Does not recover module-exported symbols or type layouts.
"""
import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("system_map", type=Path)
    parser.add_argument("imports", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    image = args.image.read_bytes()
    if image[56:60] != b"ARMd":
        parser.error("Expected an uncompressed ARM64 Image")
    symbols = {}
    addresses_by_name = {}
    for line in args.system_map.read_text().splitlines():
        address, _, name = line.split()
        symbols[name] = int(address, 16)
        addresses_by_name.setdefault(name, set()).add(int(address, 16))
    base = symbols["_text"]

    def string_at(address):
        offset = address - base
        if not 0 <= offset < len(image):
            raise ValueError("String address outside Image")
        end = image.index(0, offset)
        return image[offset:end].decode("ascii")

    exports = {}
    kinds = [("", "EXPORT_SYMBOL"), ("_gpl", "EXPORT_SYMBOL_GPL"),
             ("_gpl_future", "EXPORT_SYMBOL_GPL_FUTURE"),
             ("_unused", "EXPORT_UNUSED_SYMBOL"), ("_unused_gpl", "EXPORT_UNUSED_SYMBOL_GPL")]
    for suffix, kind in kinds:
        start = symbols["__start___ksymtab" + suffix]
        stop = symbols["__stop___ksymtab" + suffix]
        crc_start = symbols["__start___kcrctab" + suffix]
        crc_stop = symbols["__stop___kcrctab" + suffix]
        if (stop - start) % 12 or (stop - start) // 12 != (crc_stop - crc_start) // 4:
            raise ValueError("Export/CRC table lengths do not match expected PREL32 format")
        for index, address in enumerate(range(start, stop, 12)):
            value, name_offset, namespace_offset = struct.unpack_from("<iii", image, address - base)
            name = string_at(address + 4 + name_offset)
            namespace = string_at(address + 8 + namespace_offset)
            if symbols.get("__ksymtab_" + name) != address:
                raise ValueError(f"System.map disagrees with export {name}")
            if name in addresses_by_name and address + value not in addresses_by_name[name]:
                raise ValueError(f"System.map disagrees with symbol address {name}")
            crc = struct.unpack_from("<I", image, crc_start - base + 4 * index)[0]
            exports[name] = (crc, kind, namespace)
    with args.imports.open() as stream:
        imports = {r["symbol"]: int(r["crc"], 16) for r in csv.DictReader(stream)}
    common = imports.keys() & exports.keys()
    mismatches = [n for n in common if imports[n] != exports[n][0]]
    if mismatches:
        raise ValueError(f"Independent module CRC evidence disagrees: {mismatches[:10]}")
    if not common:
        raise ValueError("No independent CRC cross-checks available")
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "Module.symvers.kernel").open("w", newline="\n") as stream:
        for name, (crc, kind, namespace) in sorted(exports.items()):
            # Linux 5.4 places namespace before module, unlike newer kernels.
            stream.write(f"0x{crc:08x}\t{name}\t{namespace}\tvmlinux\t{kind}\n")
    summary = dict(kernel_export_count=len(exports), independently_matched_crcs=len(common),
                   crc_mismatches=0, image_sha256=hashlib.sha256(image).hexdigest(),
                   system_map_sha256=hashlib.sha256(args.system_map.read_bytes()).hexdigest(),
                   symvers_format="Linux 5.4: CRC, symbol, namespace, module, export kind",
                   scope="Built-in kernel exports only. Does not establish source/type/layout ABI compatibility.")
    (args.output / "kernel-exports.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
