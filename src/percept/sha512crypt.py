# SPDX-License-Identifier: MIT
"""Pure-Python SHA-512 crypt ($6$), so password hashes can be made on Windows.

Python 3.13 removed the ``crypt`` module and Windows never had it. The
algorithm is Ulrich Drepper's public specification ("Unix crypt using SHA-256
and SHA-512"); test vectors from that document are in tests/unit.
"""
import hashlib
import secrets

_ALPHABET = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
# Output byte order of the final digest, as (b2, b1, b0) triples (spec table).
_ORDER = [
    (0, 21, 42), (22, 43, 1), (44, 2, 23), (3, 24, 45), (25, 46, 4), (47, 5, 26),
    (6, 27, 48), (28, 49, 7), (50, 8, 29), (9, 30, 51), (31, 52, 10), (53, 11, 32),
    (12, 33, 54), (34, 55, 13), (56, 14, 35), (15, 36, 57), (37, 58, 16), (59, 17, 38),
    (18, 39, 60), (40, 61, 19), (62, 20, 41),
]
ROUNDS_DEFAULT = 5000
ROUNDS_MIN, ROUNDS_MAX = 1000, 999_999_999


def _b64(b2, b1, b0, n):
    w = (b2 << 16) | (b1 << 8) | b0
    out = []
    for _ in range(n):
        out.append(_ALPHABET[w & 0x3F])
        w >>= 6
    return "".join(out)


def _sha512(data):
    return hashlib.sha512(data).digest()


def crypt(password, salt=None, rounds=None):
    """Return ``$6$[rounds=N$]salt$hash``. ``salt`` is up to 16 chars of [./0-9A-Za-z]."""
    if salt is None:
        salt = "".join(secrets.choice(_ALPHABET) for _ in range(16))
    salt = salt[:16]
    explicit = rounds is not None
    r = ROUNDS_DEFAULT if rounds is None else max(ROUNDS_MIN, min(ROUNDS_MAX, rounds))
    pw = password.encode("utf-8")
    sl = salt.encode("ascii")

    b = _sha512(pw + sl + pw)
    a_in = pw + sl + (b * (len(pw) // 64) + b[: len(pw) % 64])
    n = len(pw)
    while n > 0:
        a_in += b if n & 1 else pw
        n >>= 1
    a = _sha512(a_in)

    dp = _sha512(pw * len(pw))
    p = dp * (len(pw) // 64) + dp[: len(pw) % 64]
    ds = _sha512(sl * (16 + a[0]))
    s = ds * (len(sl) // 64) + ds[: len(sl) % 64]

    c = a
    for i in range(r):
        d = b""
        d += p if i & 1 else c
        if i % 3:
            d += s
        if i % 7:
            d += p
        d += c if i & 1 else p
        c = _sha512(d)

    out = []
    for x, y, z in _ORDER:
        out.append(_b64(c[x], c[y], c[z], 4))
    out.append(_b64(0, 0, c[63], 2))
    prefix = "$6$" + ("rounds=%d$" % r if explicit else "") + salt + "$"
    return prefix + "".join(out)


def verify(password, hashed):
    if not hashed.startswith("$6$"):
        return False
    rest = hashed[3:]
    rounds = None
    if rest.startswith("rounds="):
        num, _, rest = rest[7:].partition("$")
        if not num.isdigit():
            return False
        rounds = int(num)
    salt = rest.split("$", 1)[0]
    return secrets.compare_digest(crypt(password, salt, rounds), hashed)


def looks_like_hash(value):
    """True for a well-formed ``$6$`` hash (not a plaintext password)."""
    import re
    return bool(re.fullmatch(r"\$6\$(rounds=\d+\$)?[./0-9A-Za-z]{1,16}\$[./0-9A-Za-z]{86}", value))
