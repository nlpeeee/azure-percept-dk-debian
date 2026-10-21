#!/usr/bin/env python3
"""Prepare the minimal percept_hello ABI experiment; never load it.

Uses initializer locations observed in a stock module, retaining no stock code.
This is an unvalidated experiment, not a general RANDSTRUCT compatibility tool.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from inspect_stock_modules import read_module


def sections(data):
    if data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<HH", data, 16) != (1, 183):
        raise ValueError("Expected an ELF64 little-endian AArch64 relocatable object")
    shoff = struct.unpack_from("<Q", data, 40)[0]
    size, count, names_index = struct.unpack_from("<HHH", data, 58)
    headers = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * size) for i in range(count)]
    name_header = headers[names_index]
    names = data[name_header[4]:name_header[4] + name_header[5]]
    return {names[h[0]:].split(b"\0", 1)[0].decode(): (i, shoff + i * size, h)
            for i, h in enumerate(headers)}, headers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("stock", type=Path)
    parser.add_argument("kernel_symvers", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--kexec-experiment", action="store_true",
                        help="Also permit the specifically audited experimental kexec modules")
    parser.add_argument("--extra-symvers", type=Path)
    parser.add_argument("--led-probe", action="store_true",
                        help="Permit the fixed-address Percept LED diagnostic module")
    args = parser.parse_args()
    original, candidate = read_module(args.candidate)
    stock_bytes, stock = read_module(args.stock)
    module_name = candidate["modinfo"].get("name", [None])[0]
    permitted = {"percept_hello"}
    if args.kexec_experiment:
        permitted |= {"kexec_mod", "kexec_mod_arm64"}
    if args.led_probe:
        permitted.add("percept_led_probe")
    if module_name not in permitted:
        raise ValueError("Unsupported module name")
    if module_name == "percept_hello":
        if set(candidate["versions"]) != {"printk", "module_layout"}:
            raise ValueError("Hello probe must import exactly printk and module_layout")
    elif module_name == "kexec_mod":
        if set(candidate["modinfo"].get("parmtype", [])) not in (
            {"bundle:charp", "execute:bool"},
            {"bundle:charp", "execute:bool", "trigger:bool", "execution_status:int"},
            {"bundle:charp", "execute:bool", "trigger:bool", "execution_status:int",
             "percept_caam_reset:bool"},
            {"bundle:charp", "execute:bool", "trigger:bool", "execution_status:int",
             "percept_caam_reset:bool", "percept_ocotp_clock:bool"},
        ):
            raise ValueError("Only the parameter frontend is supported")
        if "__register_chrdev" in candidate["versions"]:
            raise ValueError("Unexpected character device frontend")
    elif module_name == "percept_led_probe":
        if set(candidate["modinfo"].get("parmtype", [])) != {"pulse:bool"}:
            raise ValueError("Unexpected LED probe parameters")
        if not set(candidate["versions"]).issubset({
            "module_layout", "printk", "__ioremap", "iounmap", "msleep",
            "param_ops_bool", "arm64_const_caps_ready", "cpu_hwcap_keys",
            "cpu_hwcaps", "kimage_vaddr",
        }):
            raise ValueError("Unexpected LED probe imports")
    elif set(candidate["modinfo"].get("parmtype", [])) != {"detect_el2:int", "shim_hyp:int"}:
        raise ValueError("Unexpected architecture module parameters")
    exports = {}
    for path in [args.kernel_symvers] + ([args.extra_symvers] if args.extra_symvers else []):
        for line in path.read_text().splitlines():
            crc, name, namespace, module, kind = line.split("\t")
            if name in exports and exports[name] != crc:
                raise ValueError(f"Conflicting export CRC for {name}")
            exports[name] = crc
    for name, crc in candidate["versions"].items():
        if exports.get(name) != crc:
            raise ValueError(f"CRC mismatch for {name}; rebuild instead of overriding it")
    data = bytearray(original)
    table, headers = sections(data)
    if module_name == "percept_hello" and any(name in table for name in ("__param", "__ksymtab", "__ksymtab_gpl")):
        raise ValueError("Probe must not have parameters or exports")
    module_index, module_shoff, module_header = table[".gnu.linkonce.this_module"]
    module_data = bytearray(data[module_header[4]:module_header[4] + module_header[5]])
    name = module_name.encode() + b"\0"
    old_name_offset = candidate["this_module_name_offset"]
    if old_name_offset < 0:
        raise ValueError("Cannot locate candidate name initializer")
    module_data[old_name_offset:old_name_offset + len(name)] = bytes(len(name))
    if any(module_data):
        raise ValueError("Unexpected nonzero initializers in the probe descriptor")
    if set(candidate["this_module_relocations"]) != {"init_module", "cleanup_module"}:
        raise ValueError("Unexpected probe descriptor relocations")
    if set(stock["this_module_relocations"]) != {"init_module", "cleanup_module"}:
        raise ValueError("Stock sample lacks the expected observed initializers")
    target_size = stock["this_module_size"]
    name_offset = stock["this_module_name_offset"]
    if target_size != 768 or name_offset != 640:
        raise ValueError("This experiment is pinned to the observed Percept descriptor")
    new_module = bytearray(target_size)
    new_module[name_offset:name_offset + len(name)] = name

    def replace_section(shoff, payload, alignment):
        data.extend(bytes((-len(data)) % alignment))
        offset = len(data)
        data.extend(payload)
        struct.pack_into("<QQ", data, shoff + 24, offset, len(payload))

    replace_section(module_shoff, new_module, 64)
    reloc_index, _, reloc_header = table[".rela.gnu.linkonce.this_module"]
    if reloc_header[7] != module_index:
        raise ValueError("Unexpected relocation target")
    sym_header = headers[reloc_header[6]]
    string_header = headers[sym_header[6]]
    strings = data[string_header[4]:string_header[4] + string_header[5]]
    for off in range(reloc_header[4], reloc_header[4] + reloc_header[5], reloc_header[9]):
        _, info, addend = struct.unpack_from("<QQq", data, off)
        name_index = struct.unpack_from("<I", data, sym_header[4] + (info >> 32) * sym_header[9])[0]
        symbol = strings[name_index:].split(b"\0", 1)[0].decode()
        if info & 0xffffffff != 257 or addend != 0:
            raise ValueError("Expected direct R_AARCH64_ABS64 initializer")
        target = stock["this_module_relocations"][symbol]
        if target["addend"]:
            raise ValueError("Unexpected stock relocation addend")
        struct.pack_into("<Q", data, off, target["offset"])
    # Update __this_module's ELF symbol size, preserving all symbol indices.
    for off in range(sym_header[4], sym_header[4] + sym_header[5], sym_header[9]):
        name_index = struct.unpack_from("<I", data, off)[0]
        if strings[name_index:].split(b"\0", 1)[0] == b"__this_module":
            struct.pack_into("<Q", data, off + 16, target_size)
    _, modinfo_shoff, modinfo_header = table[".modinfo"]
    info_data = bytearray(data[modinfo_header[4]:modinfo_header[4] + modinfo_header[5]])
    offset, replaced = 0, 0
    while offset < len(info_data):
        end = info_data.index(0, offset)
        if info_data[offset:end].startswith(b"vermagic="):
            info_data[offset:end] = bytes(end - offset)
            replaced += 1
        offset = end + 1
    if replaced != 1:
        raise ValueError("Expected exactly one vermagic initializer")
    info_data.extend(b"vermagic=" + stock["modinfo"]["vermagic"][0].encode() + b"\0")
    replace_section(modinfo_shoff, info_data, 1)
    if args.output.exists():
        raise ValueError("Refusing to overwrite an output")
    args.output.write_bytes(data)
    _, prepared = read_module(args.output)
    for field in ("this_module_size", "this_module_name_offset", "this_module_relocations"):
        if prepared[field] != stock[field]:
            args.output.unlink()
            raise ValueError(f"Output cross-check failed: {field}")
    manifest = dict(candidate_sha256=hashlib.sha256(original).hexdigest(),
                    stock_sha256=hashlib.sha256(stock_bytes).hexdigest(),
                    output_sha256=hashlib.sha256(data).hexdigest(),
                    output=str(args.output), imports=candidate["versions"],
                    changes="Rebuilt zero-initialized descriptor using observed name/init/exit positions; copied stock vermagic. No imported CRCs or code changed.",
                    status="Unvalidated ABI experiment. A load test can crash the running kernel.")
    args.output.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
