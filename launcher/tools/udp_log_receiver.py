#!/usr/bin/env python3
"""Receive staging breadcrumbs; acknowledge only after flushing each record."""
import argparse
import datetime
import ipaddress
import json
import os
import re
import socket

TOKEN = re.compile(r"[A-Za-z0-9_.:-]+\Z")
FIELDS = {"protocol", "experiment", "source_boot", "actual_boot", "sequence", "event", "detail"}


def ipv4(value):
    try:
        return str(ipaddress.IPv4Address(value))
    except ipaddress.AddressValueError as error:
        raise argparse.ArgumentTypeError(str(error))


def decode(data, experiment, source_boot):
    """Reject unrelated or malformed datagrams; no received text is executed."""
    if len(data) > 1024:
        raise ValueError("oversized packet")
    record = json.loads(data.decode("ascii"))
    if not isinstance(record, dict) or set(record) != FIELDS:
        raise ValueError("unexpected fields")
    limits = {"experiment": 80, "source_boot": 36, "actual_boot": 36, "event": 64, "detail": 128}
    for field, maximum in limits.items():
        value = record[field]
        if not isinstance(value, str) or not 1 <= len(value) <= maximum or not TOKEN.fullmatch(value):
            raise ValueError("invalid token")
    if record["protocol"] != "percept-stage-v1" or record["experiment"] != experiment or record["source_boot"] != source_boot:
        raise ValueError("wrong experiment")
    if type(record["sequence"]) is not int or not 1 <= record["sequence"] <= 1000000:
        raise ValueError("invalid sequence")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", required=True, type=ipv4, help="This PC's fixed LAN IPv4 address")
    parser.add_argument("--port", type=int, default=6666)
    parser.add_argument("--source", required=True, type=ipv4, help="Expected board IPv4 address")
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--source-boot", required=True)
    parser.add_argument("--output", required=True, help="New JSONL file; existing files are never overwritten")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be in 1..65535")
    for value, maximum in ((args.experiment, 80), (args.source_boot, 36)):
        if not 1 <= len(value) <= maximum or not TOKEN.fullmatch(value):
            parser.error("invalid experiment or source-boot token")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind((args.bind, args.port))
        with open(args.output, "x", encoding="utf-8", newline="\n") as output:
            print("Listening on {}:{}; Ctrl+C stops the receiver.".format(args.bind, args.port), flush=True)
            try:
                while True:
                    data, address = receiver.recvfrom(2048)
                    if address[0] != args.source:
                        continue
                    try:
                        record = decode(data, args.experiment, args.source_boot)
                    except (ValueError, UnicodeError):
                        continue
                    record["received_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    record["sender"] = "{}:{}".format(*address)
                    line = json.dumps(record, sort_keys=True)
                    output.write(line + "\n")
                    output.flush()
                    os.fsync(output.fileno())
                    print(line, flush=True)
                    acknowledgement = "ACK {} {} {}".format(record["sequence"], record["experiment"], record["actual_boot"])
                    receiver.sendto(acknowledgement.encode("ascii"), address)
            except KeyboardInterrupt:
                return


if __name__ == "__main__":
    main()
