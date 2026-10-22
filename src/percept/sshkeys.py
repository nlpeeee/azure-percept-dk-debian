# SPDX-License-Identifier: MIT
"""Validation of OpenSSH public-key lines (authorized_keys entries)."""
import base64
import binascii
import struct

KEY_TYPES = {
    "ssh-ed25519", "sk-ssh-ed25519@openssh.com",
    "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
    "sk-ecdsa-sha2-nistp256@openssh.com", "ssh-rsa",
}


class PublicKeyError(ValueError):
    pass


def _read_string(blob, off):
    if off + 4 > len(blob):
        raise PublicKeyError("truncated key data")
    (n,) = struct.unpack(">I", blob[off:off + 4])
    off += 4
    if off + n > len(blob):
        raise PublicKeyError("truncated key data")
    return blob[off:off + n], off + n


def parse_public_key(line):
    """Return (type, comment, rsa_bits_or_None). Raises PublicKeyError if unusable."""
    line = line.strip()
    if not line:
        raise PublicKeyError("empty key")
    if "\n" in line or "\r" in line:
        raise PublicKeyError("more than one line")
    if line.startswith("-----BEGIN") or "PRIVATE KEY" in line:
        raise PublicKeyError("this looks like a PRIVATE key; supply the public key (.pub) only")
    parts = line.split(None, 2)
    if len(parts) < 2:
        raise PublicKeyError("expected '<type> <base64> [comment]'")
    ktype, b64 = parts[0], parts[1]
    comment = parts[2] if len(parts) > 2 else ""
    if ktype not in KEY_TYPES:
        raise PublicKeyError("unsupported or optioned key (type %r); options such as command= are not allowed" % ktype[:40])
    try:
        blob = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise PublicKeyError("key data is not valid base64") from None
    inner, off = _read_string(blob, 0)
    if inner.decode("ascii", "replace") != ktype:
        raise PublicKeyError("key data does not match declared type %s" % ktype)
    bits = None
    if ktype == "ssh-ed25519":
        pub, off = _read_string(blob, off)
        if len(pub) != 32 or off != len(blob):
            raise PublicKeyError("ed25519 key data has the wrong length")
    if ktype == "ssh-rsa":
        _e, off = _read_string(blob, off)
        n, off = _read_string(blob, off)
        bits = len(n.lstrip(b"\0")) * 8
        if n.lstrip(b"\0"):
            bits -= 8 - n.lstrip(b"\0")[0].bit_length()
    return ktype, comment, bits


def check_key(line):
    """Return (normalized_line, warning_or_None); raise PublicKeyError on a bad key."""
    ktype, comment, bits = parse_public_key(line)
    warn = None
    if bits is not None:
        if bits < 2048:
            raise PublicKeyError("RSA key is only %d bits; use at least 3072 (or ed25519)" % bits)
        if bits < 3072:
            warn = "RSA key is %d bits; ed25519 or RSA >= 3072 is recommended" % bits
    parts = line.strip().split(None, 2)
    return " ".join(parts[:2] + ([comment] if comment else [])), warn
def generate_key(path, password):
    """Generate a PC key without a console dependency; never overwrite a key."""
    import os
    from pathlib import Path
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    from .config import restrict_permissions
    path=Path(path)
    if path.exists() or Path(str(path)+'.pub').exists():
        raise FileExistsError('key already exists; select its public key instead')
    key=Ed25519PrivateKey.generate()
    encryption=serialization.BestAvailableEncryption(password.encode()) if password else serialization.NoEncryption()
    private=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.OpenSSH,encryption)
    public=key.public_key().public_bytes(serialization.Encoding.OpenSSH,serialization.PublicFormat.OpenSSH)+b'\n'
    path.parent.mkdir(parents=True,exist_ok=True)
    for target,value in ((path,private),(Path(str(path)+'.pub'),public)):
        with os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:stream.write(value)
        restrict_permissions(str(target))
    return public.decode().strip()

