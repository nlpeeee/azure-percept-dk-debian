# SPDX-License-Identifier: MIT
"""Offline FDT structure and property-span validation; no device access."""
import hashlib
import struct

def digest(data):
    return hashlib.sha256(data).hexdigest()


def span(data, offset, size):
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise ValueError("range outside input: offset=%#x size=%#x" % (offset, size))
    return data[offset:offset + size]


def be32(data, offset):
    return struct.unpack(">I", span(data, offset, 4))[0]


def align4(value):
    return (value + 3) & ~3


def cstring(data, start, end):
    stop = data.find(b"\0", start, end)
    if stop < 0:
        raise ValueError("unterminated string")
    return data[start:stop].decode("ascii"), stop + 1


def property_value(value, name=""):
    if not value:
        return True
    numeric = (name in ("load", "entry", "data-size", "data-position", "data-offset", "timestamp",
                        "hashed-strings", "reg", "phandle", "interrupt-parent")
               or name.startswith("#") or name.endswith("-cells"))
    if not numeric and value[0] and value.endswith(b"\0") and all(c == 0 or 32 <= c < 127 for c in value):
        return value[:-1].decode("ascii").split("\0")
    if len(value) <= 16 and len(value) % 4 == 0:
        return ["0x%x" % c for c in struct.unpack(">%dI" % (len(value) // 4), value)]
    return {"bytes": len(value), "sha256": digest(value),
            "hex": value.hex() if len(value) <= 64 else None}


def parse_fdt(data, base):
    h = struct.unpack(">10I", span(data, base, 40))
    magic, total, off_struct, off_strings, off_rsv, version, compat, cpu, nstrings, nstruct = h
    if magic != 0xd00dfeed or version != 17 or compat > 17:
        raise ValueError("expected FDT v17 with compatible version <=17")
    blob = span(data, base, total)
    if total < 40 or any(p < 40 for p in (off_struct, off_strings, off_rsv)):
        raise ValueError("invalid FDT header offsets")
    struct_end = off_struct + nstruct
    strings_end = off_strings + nstrings
    span(blob, off_struct, nstruct)
    span(blob, off_strings, nstrings)
    if off_struct % 4 or off_rsv % 8:
        raise ValueError("misaligned FDT block")
    if max(off_struct, off_strings) < min(struct_end, strings_end):
        raise ValueError("overlapping FDT structure and strings")
    reservations = []
    p = off_rsv
    while True:
        addr, size = struct.unpack(">QQ", span(blob, p, 16))
        p += 16
        if addr == size == 0:
            break
        reservations.append({"address": addr, "size": size})
        if len(reservations) > 65536:
            raise ValueError("too many memory reservations")
    if max(off_rsv, off_struct) < min(p, struct_end) or max(off_rsv, off_strings) < min(p, strings_end):
        raise ValueError("overlapping FDT reservation map")
    nodes, stack, raws, offsets = {}, [], {}, {}
    p = off_struct
    ended = False
    while p < struct_end:
        token = be32(blob, p)
        p += 4
        if token == 1:
            name, p = cstring(blob, p, struct_end)
            p = align4(p)
            if not stack:
                if name or nodes:
                    raise ValueError("invalid FDT root")
                path = "/"
            else:
                if not name or "/" in name:
                    raise ValueError("invalid FDT node name")
                path = stack[-1].rstrip("/") + "/" + name
            if path in nodes or len(stack) > 256:
                raise ValueError("duplicate node or excessive FDT depth")
            stack.append(path)
            nodes[path], raws[path] = {}, {}
        elif token == 2:
            if not stack:
                raise ValueError("unbalanced END_NODE")
            stack.pop()
        elif token == 3:
            if not stack:
                raise ValueError("FDT property outside node")
            length, nameoff = struct.unpack(">II", span(blob, p, 8))
            p += 8
            if nameoff >= nstrings or length > struct_end - p:
                raise ValueError("invalid property length or name offset")
            name, _ = cstring(blob, off_strings + nameoff, strings_end)
            value = span(blob, p, length)
            if name in nodes[stack[-1]]:
                raise ValueError("duplicate FDT property")
            nodes[stack[-1]][name] = property_value(value, name)
            raws[stack[-1]][name] = value
            offsets[(stack[-1], name)] = base + p
            p = align4(p + length)
        elif token == 4:
            pass
        elif token == 9:
            if stack or not nodes:
                raise ValueError("unbalanced FDT END")
            ended = True
            break
        else:
            raise ValueError("unknown FDT token %#x" % token)
    if not ended or p > struct_end:
        raise ValueError("missing FDT END or block overrun")
    record = {"offset": base, "totalsize": total, "sha256": digest(blob),
              "version": version, "last_compatible_version": compat,
              "boot_cpuid_phys": cpu, "reservations": reservations,
              "nodes": nodes, "kind": "FIT" if "/images" in nodes and "/configurations" in nodes else "FDT"}
    return record

def walk_properties(blob):
    """Use the shared parser for full validation, then retain raw property spans."""
    parsed = parse_fdt(blob, 0)
    if parsed["kind"] != "FDT":
        raise ValueError("expected an ordinary DTB")
    _, total, start, strings, _, _, _, _, _, nstruct = struct.unpack_from(">10I", blob)
    pos, stack, result = start, [], {}
    while pos < start + nstruct:
        token_start = pos
        token = struct.unpack_from(">I", blob, pos)[0]
        pos += 4
        if token == 1:
            end = blob.index(b"\0", pos)
            name = blob[pos:end].decode("ascii")
            path = "/" if not stack else stack[-1].rstrip("/") + "/" + name
            stack.append(path)
            result[path] = {}
            pos = align4(end + 1)
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack_from(">II", blob, pos)
            pos += 8
            name_start = strings + nameoff
            name = blob[name_start:blob.index(b"\0", name_start)].decode("ascii")
            value = blob[pos:pos + length]
            pos = align4(pos + length)
            result[stack[-1]][name] = (value, token_start, pos)
        elif token == 4:
            continue
        elif token == 9:
            break
    return parsed, result
