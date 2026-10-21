# SPDX-License-Identifier: MIT
"""Shared test helpers. Importing this module puts src/ on sys.path."""
import base64
import os
import struct
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))


def _s(b):
    return struct.pack(">I", len(b)) + b


def ed25519_key(seed=1, comment="test@example"):
    """A syntactically valid (not usable) ed25519 public key line built at runtime."""
    blob = _s(b"ssh-ed25519") + _s(bytes([seed]) * 32)
    return "ssh-ed25519 %s %s" % (base64.b64encode(blob).decode(), comment)


def rsa_key(bits=3072, comment="rsa@example"):
    n = (1 << (bits - 1)) | 1
    nb = n.to_bytes((bits + 7) // 8, "big")
    if nb[0] & 0x80:
        nb = b"\0" + nb
    blob = _s(b"ssh-rsa") + _s(b"\x01\x00\x01") + _s(nb)
    return "ssh-rsa %s %s" % (base64.b64encode(blob).decode(), comment)


def minimal_cfg(**over):
    cfg = {"schema": 1, "board": {"name": "t1"}, "user": [{"name": "percept", "authorized_keys": [ed25519_key()]}]}
    for k, v in over.items():
        cfg[k] = v
    return cfg
