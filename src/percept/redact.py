# SPDX-License-Identifier: MIT
"""Keep secrets out of logs and terminal output."""
import hashlib

MIN_LEN = 4
MASK = "***"


def wifi_psk_hex(ssid, passphrase):
    """The 256-bit WPA-PSK derived from a passphrase (also a secret)."""
    return hashlib.pbkdf2_hmac("sha1", passphrase.encode("utf-8"), ssid.encode("utf-8"), 4096, 32).hex()


def collect_secrets(cfg, extra=()):
    """All secret strings (and derivations) found in a normalised config."""
    found = set(s for s in extra if s)
    w = cfg.get("network", {}).get("wifi", {})
    if w.get("psk"):
        found.add(w["psk"])
        if w.get("ssid") and len(w["psk"]) != 64:
            found.add(wifi_psk_hex(w["ssid"], w["psk"]))
    for u in cfg.get("user", []) if isinstance(cfg.get("user"), list) else []:
        h = u.get("password_hash")
        if h:
            found.add(h)
            found.add(h.rsplit("$", 1)[-1])
    rh = cfg.get("rescue", {}).get("password_hash")
    if rh:
        found.add(rh)
        found.add(rh.rsplit("$", 1)[-1])
    return {s for s in found if len(s) >= MIN_LEN}


class Redactor:
    """Replace every known secret in text; longest first so substrings can't leak."""

    def __init__(self, secrets=()):
        self._secrets = sorted({s for s in secrets if s and len(s) >= MIN_LEN}, key=len, reverse=True)

    def add(self, *values):
        self._secrets = sorted(set(self._secrets) | {v for v in values if v and len(v) >= MIN_LEN},
                               key=len, reverse=True)

    def __call__(self, text):
        for s in self._secrets:
            text = text.replace(s, MASK)
        return text

    def __bool__(self):
        return bool(self._secrets)
