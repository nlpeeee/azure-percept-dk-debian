#!/usr/bin/env python3
"""Read ARM64 ELF module metadata; never load or modify the input modules."""
import argparse
import csv
import hashlib
import json
import lzma
import struct
from pathlib import Path


def read_module(path):
    packed = path.read_bytes()
    data = lzma.decompress(packed) if path.suffix == ".xz" else packed
    if data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", data, 18)[0] != 183:
        raise ValueError(f"Expected little-endian ELF64 AArch64: {path}")
    shoff = struct.unpack_from("<Q", data, 40)[0]
    entsize, count, names_index = struct.unpack_from("<HHH", data, 58)
    headers = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * entsize)
               for i in range(count)]
    names_hdr = headers[names_index]
    names = data[names_hdr[4]:names_hdr[4] + names_hdr[5]]
    sections = {}
    for hdr in headers:
        name = names[hdr[0]:].split(b"\0", 1)[0].decode("ascii")
        sections[name] = (hdr, data[hdr[4]:hdr[4] + hdr[5]])
    info = {}
    for item in sections.get(".modinfo", (None, b""))[1].split(b"\0"):
        if b"=" in item:
            key, value = item.split(b"=", 1)
            info.setdefault(key.decode(), []).append(value.decode(errors="replace"))
    versions = {}
    version_data = sections.get("__versions", (None, b""))[1]
    if len(version_data) % 64:
        raise ValueError(f"Unexpected modversion_info size: {path}")
    for off in range(0, len(version_data), 64):
        crc = struct.unpack_from("<Q", version_data, off)[0]
        name = version_data[off + 8:off + 64].split(b"\0", 1)[0].decode()
        versions[name] = f"0x{crc:08x}"
    module_section = sections.get(".gnu.linkonce.this_module")
    initializers = {}
    relocation_section = sections.get(".rela.gnu.linkonce.this_module")
    if relocation_section:
        rel_hdr, rel_data = relocation_section
        sym_hdr = headers[rel_hdr[6]]
        str_hdr = headers[sym_hdr[6]]
        strings = data[str_hdr[4]:str_hdr[4] + str_hdr[5]]
        for off in range(0, len(rel_data), rel_hdr[9]):
            offset, info_index, addend = struct.unpack_from("<QQq", rel_data, off)
            symbol_offset = sym_hdr[4] + (info_index >> 32) * sym_hdr[9]
            name_index = struct.unpack_from("<I", data, symbol_offset)[0]
            name = strings[name_index:].split(b"\0", 1)[0].decode()
            initializers[name] = {"offset": offset, "addend": addend}
    module_name = info.get("name", [path.name.split(".ko")[0].replace("-", "_")])[0]
    name_offset = module_section[1].find(module_name.encode() + b"\0") if module_section else -1
    return data, {
        "path": str(path),
        "sha256_elf": hashlib.sha256(data).hexdigest(),
        "modinfo": info,
        "compilers": sorted(set(s.decode(errors="replace") for s in
                                sections.get(".comment", (None, b""))[1].split(b"\0") if s)),
        "this_module_size": module_section[0][5] if module_section else None,
        "this_module_name_offset": name_offset,
        "this_module_relocations": initializers,
        "debug_sections": sorted(s for s in sections if s.startswith(".debug")),
        "versions": versions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    paths = sorted(set(args.module_root.rglob("*.ko")) | set(args.module_root.rglob("*.ko.xz")))
    if not paths:
        parser.error("No .ko or .ko.xz files found")
    records, crcs, vermagics = [], {}, set()
    sample_data = None
    for path in paths:
        data, record = read_module(path)
        record["path"] = str(path.relative_to(args.module_root))
        records.append(record)
        vermagics.update(record["modinfo"].get("vermagic", []))
        for name, crc in record["versions"].items():
            if name in crcs and crcs[name] != crc:
                raise ValueError(f"Conflicting CRCs for {name}")
            crcs[name] = crc
        if sample_data is None:
            sample_data = data
    args.output.mkdir(parents=True, exist_ok=True)
    summary = {
        "module_count": len(records),
        "vermagic": sorted(vermagics),
        "imported_symbol_count": len(crcs),
        "module_layout_crc": crcs.get("module_layout"),
        "this_module_sizes": sorted(set(r["this_module_size"] for r in records if r["this_module_size"] is not None)),
        "modules_with_debug_info": sum(bool(r["debug_sections"]) for r in records),
        "init_offsets": sorted(set(v["offset"] for r in records for k, v in r["this_module_relocations"].items() if k == "init_module")),
        "exit_offsets": sorted(set(v["offset"] for r in records for k, v in r["this_module_relocations"].items() if k == "cleanup_module")),
        "name_offsets": sorted(set(r["this_module_name_offset"] for r in records)),
        "compilers": sorted(set(c for r in records for c in r["compilers"])),
        "sample_module": records[0]["path"],
        "scope": "Imported symbol CRCs only; this is not a complete Module.symvers and does not recover RANDSTRUCT layouts or seed.",
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.output / "modules.json").write_text(json.dumps(records, indent=2) + "\n")
    with (args.output / "imported-symbol-crcs.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["symbol", "crc"])
        writer.writerows(sorted(crcs.items()))
    (args.output / "stock-sample.ko").write_bytes(sample_data)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
