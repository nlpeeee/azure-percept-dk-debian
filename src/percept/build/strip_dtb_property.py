#!/usr/bin/env python3
"""Remove whole properties from a DTB using FDT_NOP tokens, changing nothing else.

Written to drop the vendor `extcon` phandle from the Percept's USB-C controller
node: it points at an `ite,it5201` CC chip that has no mainline driver, so dwc3
defers for ever (see docs/usb-c.md). Each removed property's record is
overwritten with NOP tokens, so every other byte, structure offset, phandle and
reservation-map entry keeps its exact value. The manifest records that.

Reuses the parser and NOP technique of tools/prepare_percept_dtb.py.
"""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).absolute().parents[1]
SPEC = importlib.util.spec_from_file_location("percept_prepare_dtb", ROOT / "tools/prepare_percept_dtb.py")
PREP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREP)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--remove", action="append", required=True, metavar="NODE:PROPERTY",
                        help="repeatable, e.g. /soc@0/usb@38100000:extcon")
    parser.add_argument("--expect-sha256", help="refuse to run unless the source matches")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit("refusing to overwrite " + str(args.output))
    data = args.source.read_bytes()
    if args.expect_sha256 and PREP.sha(data) != args.expect_sha256:
        raise SystemExit("source sha256 mismatch: " + PREP.sha(data))

    original, nodes = PREP.walk_properties(data)
    out = bytearray(data)
    edits = []
    for spec in args.remove:
        path, separator, name = spec.rpartition(":")
        if not separator or not path or not name:
            raise SystemExit("bad --remove spec: " + spec)
        if path not in nodes:
            raise SystemExit("no such node: " + path)
        if name not in nodes[path]:
            raise SystemExit("no such property: " + spec)
        value, start, end = nodes[path][name]
        out[start:end] = struct.pack(">I", 4) * ((end - start) // 4)
        edits.append({"node": path, "property": name, "removed_bytes": len(value),
                      "old_hex": value.hex(), "action": "FDT_NOP"})

    # Re-parse and prove the edit was surgical.
    patched, patched_nodes = PREP.walk_properties(bytes(out))
    removed = {(e["node"], e["property"]) for e in edits}
    for path, props in nodes.items():
        if path not in patched_nodes:
            raise SystemExit("node vanished: " + path)
        for name, (value, _, _) in props.items():
            if (path, name) in removed:
                if name in patched_nodes[path]:
                    raise SystemExit("property still present: %s:%s" % (path, name))
                continue
            if PREP.raw(patched_nodes, path, name) != value:
                raise SystemExit("unexpected change at %s:%s" % (path, name))
    for path in patched_nodes:
        if path not in nodes:
            raise SystemExit("node appeared: " + path)
    if len(out) != len(data):
        raise SystemExit("size changed")
    if original["reservations"] != patched["reservations"]:
        raise SystemExit("reservation map changed")

    args.output.write_bytes(bytes(out))
    manifest = {
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "note": args.note,
        "source": {"path": str(args.source.absolute()), "sha256": PREP.sha(data), "bytes": len(data)},
        "output": {"path": str(args.output.absolute()), "sha256": PREP.sha(bytes(out)), "bytes": len(out)},
        "edits": edits,
        "nodes_unchanged": len(nodes),
        "all_other_properties_byte_identical": True,
        "size_unchanged": True,
        "reservation_map_unchanged": True,
        "reservations": patched["reservations"],
    }
    manifest_path = args.output.with_suffix(args.output.suffix + ".json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, struct.error) as error:
        raise SystemExit(str(error))
