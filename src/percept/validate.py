# SPDX-License-Identifier: MIT
"""Validate and normalise a per-board configuration.

``validate(cfg, base_dir)`` returns a ``Result``: ``errors`` block a build,
``warnings`` do not, ``config`` is the fully defaulted configuration (secret
references resolved, SSH key files read). Nothing here touches the network or
the board.
"""
import ipaddress
import os
import re

from . import config as cfgmod
from . import sha512crypt, sshkeys
from .schema import FIELDS, SCHEMA_VERSION

_HERE = os.path.dirname(os.path.abspath(__file__))

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
TZ_RE = re.compile(r"^[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+)*$")
LOCALE_RE = re.compile(r"^(C|POSIX|[a-z]{2,3}_[A-Z]{2})\.UTF-8$")
CMDLINE_RE = re.compile(r"^[A-Za-z0-9_.,=:/+ -]*$")
PKG_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
GROUP_RE = USER_RE
RESERVED_USERS = {"root", "daemon", "bin", "sys", "sync", "games", "man", "lp", "mail", "news", "uucp",
                  "proxy", "www-data", "backup", "list", "irc", "nobody", "sshd", "systemd-network",
                  "systemd-resolve", "systemd-timesync", "messagebus"}

CHOICES = {
    "ssh.root_login": ("disabled", "key-only"),
    "user.sudo": ("auto", "nopasswd", "password", "none"),
    "user.password_mode": ("none", "hash", "generate"),
    "network.ethernet.mode": ("dhcp", "static"),
    "network.ethernet.ipv6": ("auto", "off"),
    "network.wifi.security": ("wpa2", "wpa3", "open"),
    "rescue.net_mode": ("dhcp", "static"),
    "os.kernel.source": ("distro", "files", "custom"),
    "storage.layout": ("auto", "v2", "factory"),
    "install.method": ("uuu", "ssh"),
}


class Result:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.config = {}

    @property
    def ok(self):
        return not self.errors

    def err(self, path, msg):
        self.errors.append("%s: %s" % (path, msg))

    def warn(self, path, msg):
        self.warnings.append("%s: %s" % (path, msg))


def countries():
    with open(os.path.join(_HERE, "data", "countries.txt"), encoding="ascii") as f:
        return set(f.read().split())


def _defaults():
    out = {}
    for f in FIELDS:
        if f.path.startswith("user[]"):
            continue
        node = out
        parts = f.path.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        if f.default is None or (isinstance(f.default, str) and f.default.startswith("=")):
            continue
        node[parts[-1]] = list(f.default) if isinstance(f.default, list) else f.default
    return out


USER_DEFAULTS = {f.path.split(".", 1)[1]: (list(f.default) if isinstance(f.default, list) else f.default)
                 for f in FIELDS if f.path.startswith("user[]") and f.default is not None}


def _fill(cfg, defaults):
    for k, v in defaults.items():
        if isinstance(v, dict):
            cfg[k] = _fill(cfg.get(k, {}) if isinstance(cfg.get(k), dict) else {}, v)
        else:
            cfg.setdefault(k, v)
    return cfg


def _typecheck(cfg, res):
    """Check scalar types against the schema before any rule logic runs."""
    kinds = {"str": str, "int": int, "bool": bool}
    for f in FIELDS:
        parts = f.path.replace("[]", "").split(".")
        arr = "[]" in f.path

        def check(table, where):
            node = table
            for p in parts[1 if arr else 0:-1]:
                node = node.get(p) if isinstance(node, dict) else None
                if node is None:
                    return
            if not isinstance(node, dict) or parts[-1] not in node:
                return
            v = node[parts[-1]]
            if f.type.startswith("list"):
                if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
                    res.err(where, "must be a list of strings")
            elif f.type == "int":
                if isinstance(v, bool) or not isinstance(v, int):
                    res.err(where, "must be a whole number")
            elif not isinstance(v, kinds[f.type]):
                res.err(where, "must be %s" % {"str": "text", "bool": "true or false"}[f.type])

        if arr:
            for i, u in enumerate(cfg.get("user", []) if isinstance(cfg.get("user"), list) else []):
                if isinstance(u, dict):
                    check(u, "user[%d].%s" % (i, parts[-1]))
        else:
            check(cfg, f.path)


def _ipv4(res, path, value):
    try:
        return ipaddress.IPv4Address(value)
    except (ipaddress.AddressValueError, ValueError):
        res.err(path, "%r is not an IPv4 address" % value)
        return None


def _static_block(res, cfg, section, need_gateway):
    t = cfg[section.split(".")[0]] if "." not in section else cfg[section.split(".")[0]][section.split(".")[1]]
    addr = t.get("address")
    prefix = t.get("prefix")
    gw = t.get("gateway")
    if not addr:
        res.err(section + ".address", "required for static addressing")
    if prefix is None:
        res.err(section + ".prefix", "required for static addressing")
    elif not 1 <= prefix <= 30:
        res.err(section + ".prefix", "must be between 1 and 30")
    if need_gateway and not gw:
        res.err(section + ".gateway", "required for static addressing")
    a = _ipv4(res, section + ".address", addr) if addr else None
    g = _ipv4(res, section + ".gateway", gw) if gw else None
    if a is not None and isinstance(prefix, int) and 1 <= prefix <= 30:
        net = ipaddress.IPv4Network("%s/%d" % (a, prefix), strict=False)
        if a in (net.network_address, net.broadcast_address):
            res.err(section + ".address", "is the network or broadcast address of %s" % net)
        if g is not None:
            if g not in net:
                res.err(section + ".gateway", "%s is outside %s" % (g, net))
            if g == a:
                res.err(section + ".gateway", "must differ from the board's own address")
    for d in t.get("dns", []):
        _ipv4(res, section + ".dns", d)


def _read_keys(res, where, entry, base_dir):
    lines = list(entry.get("authorized_keys", []))
    kf = entry.get("authorized_keys_file")
    if kf:
        path = os.path.expanduser(kf)
        if not os.path.isabs(path):
            path = os.path.join(base_dir, path)
        try:
            with open(path, encoding="utf-8") as f:
                lines += [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]
        except OSError as exc:
            res.err(where + ".authorized_keys_file", "cannot read %s (%s)" % (path, exc.strerror))
    keys, seen = [], set()
    for i, line in enumerate(lines):
        try:
            norm, warn = sshkeys.check_key(line)
        except sshkeys.PublicKeyError as exc:
            res.err("%s.authorized_keys[%d]" % (where, i), str(exc))
            continue
        if warn:
            res.warn("%s.authorized_keys[%d]" % (where, i), warn)
        blob = norm.split()[1]
        if blob not in seen:
            seen.add(blob)
            keys.append(norm)
    return keys


def validate(cfg, base_dir=".", env=None):
    res = Result()
    try:
        cfg = cfgmod.resolve_references(cfg, base_dir, env)
    except cfgmod.ConfigError as exc:
        res.err("config", str(exc))
        return res
    for path in cfgmod.unknown_keys(cfg):
        res.err(path, "unknown setting (typo?)")
    _typecheck(cfg, res)
    if res.errors:
        return res

    c = _fill(cfg, _defaults())
    res.config = c
    if c["schema"] != SCHEMA_VERSION:
        res.err("schema", "this version of percept needs schema = %d" % SCHEMA_VERSION)

    # --- board ---------------------------------------------------------
    b = c.setdefault("board", {})
    name = b.get("name")
    if not name:
        res.err("board.name", "required")
    elif not NAME_RE.match(name):
        res.err("board.name", "use lowercase letters, digits, '-' and '_' (1-32 chars, not starting with - or _)")
    b.setdefault("hostname", name or "")
    if not HOST_RE.match(b["hostname"] or ""):
        res.err("board.hostname", "not a valid RFC 1123 hostname")
    if not TZ_RE.match(b["timezone"]) or ".." in b["timezone"]:
        res.err("board.timezone", "not an IANA zone name such as Europe/London")
    if not LOCALE_RE.match(b["locale"]):
        res.err("board.locale", "expected a UTF-8 locale such as en_US.UTF-8 or C.UTF-8")

    # --- ssh / users -----------------------------------------------------
    s = c["ssh"]
    if s["root_login"] not in CHOICES["ssh.root_login"]:
        res.err("ssh.root_login", "must be one of %s" % ", ".join(CHOICES["ssh.root_login"]))
    if not 1 <= s["port"] <= 65535:
        res.err("ssh.port", "must be 1-65535")
    users = c.get("user")
    if not isinstance(users, list) or not users:
        res.err("user", "at least one [[user]] is required")
        users = []
    names = set()
    ssh_path = False
    for i, u in enumerate(users):
        w = "user[%d]" % i
        _fill(u, USER_DEFAULTS)
        un = u.get("name", "")
        if not USER_RE.match(un):
            res.err(w + ".name", "invalid login name")
        elif un in RESERVED_USERS:
            res.err(w + ".name", "%r is reserved" % un)
        if un in names:
            res.err(w + ".name", "duplicate user")
        names.add(un)
        for key in ("sudo", "password_mode"):
            if u[key] not in CHOICES["user." + key]:
                res.err("%s.%s" % (w, key), "must be one of %s" % ", ".join(CHOICES["user." + key]))
        for g in u["groups"]:
            if not GROUP_RE.match(g):
                res.err(w + ".groups", "invalid group name %r" % g)
        u["authorized_keys"] = _read_keys(res, w, u, base_dir)
        u.pop("authorized_keys_file", None)
        h = u.get("password_hash")
        if h is not None:
            if not sha512crypt.looks_like_hash(h):
                res.err(w + ".password_hash", "not a '$6$' SHA-512 crypt hash. Plaintext passwords are never stored; make a hash with 'percept hash-password'")
            elif u["password_mode"] == "none":
                u["password_mode"] = "hash"
        if u["password_mode"] == "hash" and not h:
            res.err(w + ".password_hash", "required when password_mode = \"hash\"")
        if u["password_mode"] == "generate" and h:
            res.err(w + ".password_mode", "'generate' conflicts with a supplied password_hash")
        if u["sudo"] == "auto":
            u["sudo"] = "password" if u["password_mode"] != "none" else "nopasswd"
        elif u["sudo"] == "password" and u["password_mode"] == "none":
            res.err(w + ".sudo", "'password' needs a password (set password_hash or password_mode = \"generate\")")
        if u["authorized_keys"]:
            ssh_path = True
        if s["password_auth"] and u["password_mode"] != "none":
            ssh_path = True
    if s["password_auth"] and not any(u.get("password_mode") != "none" for u in users):
        res.err("ssh.password_auth", "enabled but no user has a password")
    if users and not ssh_path:
        res.err("user", "no way to log in: give a user an SSH public key (recommended) or enable ssh.password_auth with a password")
    if s["password_auth"]:
        res.warn("ssh.password_auth", "password logins over SSH are weaker than keys")

    # --- ethernet ----------------------------------------------------------
    e = c["network"]["ethernet"]
    if e["mode"] not in CHOICES["network.ethernet.mode"]:
        res.err("network.ethernet.mode", "must be dhcp or static")
    elif e["mode"] == "static":
        _static_block(res, c, "network.ethernet", need_gateway=True)
        if not e.get("dns"):
            res.warn("network.ethernet.dns", "no DNS servers set; name resolution will fail")
    if e["ipv6"] not in CHOICES["network.ethernet.ipv6"]:
        res.err("network.ethernet.ipv6", "must be auto or off")

    # --- wifi ----------------------------------------------------------------
    w = c["network"]["wifi"]
    if w["security"] not in CHOICES["network.wifi.security"]:
        res.err("network.wifi.security", "must be wpa2, wpa3 or open")
    if w["enabled"]:
        ssid = w.get("ssid")
        if not ssid:
            res.err("network.wifi.ssid", "required when Wi-Fi is enabled")
        elif not 1 <= len(ssid.encode("utf-8")) <= 32:
            res.err("network.wifi.ssid", "must be 1-32 bytes")
        elif "\n" in ssid or "\r" in ssid or "\0" in ssid:
            res.err("network.wifi.ssid", "contains control characters")
        cc = w.get("country")
        if not cc:
            res.err("network.wifi.country", "required when Wi-Fi is enabled (regulatory domain, e.g. GB, US)")
        elif cc not in countries():
            res.err("network.wifi.country", "%r is not an ISO 3166 alpha-2 code" % cc)
        psk = w.get("psk")
        if w["security"] == "open":
            if psk:
                res.warn("network.wifi.psk", "ignored for an open network")
        elif not psk:
            res.err("network.wifi.psk", "required unless security = \"open\"")
        elif re.fullmatch(r"[0-9A-Fa-f]{64}", psk):
            pass
        elif not (8 <= len(psk) <= 63 and all(0x20 <= ord(ch) <= 0x7E for ch in psk)):
            res.err("network.wifi.psk", "must be 8-63 printable ASCII characters, or 64 hex digits")
    elif w.get("ssid") or w.get("psk"):
        res.warn("network.wifi", "Wi-Fi details given but enabled = false; they will be ignored")

    # --- rescue ----------------------------------------------------------------
    r = c["rescue"]
    if not r["enabled"]:
        res.warn("rescue.enabled", "rescue disabled: a bad boot will need USB recovery")
    if r["net_mode"] not in CHOICES["rescue.net_mode"]:
        res.err("rescue.net_mode", "must be dhcp or static")
    elif r["net_mode"] == "static":
        _static_block(res, c, "rescue", need_gateway=False)
    if not 1 <= r["fail_limit"] <= 10:
        res.err("rescue.fail_limit", "must be 1-10")
    if not 1 <= r["grub_tries"] <= 4:
        res.err("rescue.grub_tries", "must be 1-4 (the GRUB countdown has four steps)")
    rk = _read_keys(res, "rescue", r, base_dir) if r.get("authorized_keys") or r.get("authorized_keys_file") else []
    r.pop("authorized_keys_file", None)
    if not rk and users:
        rk = list(users[0].get("authorized_keys", []))
    r["authorized_keys"] = rk
    rh = r.get("password_hash")
    if rh is not None and not sha512crypt.looks_like_hash(rh):
        res.err("rescue.password_hash", "not a '$6$' SHA-512 crypt hash; make one with 'percept hash-password'")
    if r["password_auth"]:
        first = users[0] if users else {}
        if rh is None:
            if first.get("password_mode") == "hash":
                r["password_hash"] = first["password_hash"]
            elif first.get("password_mode") == "generate":
                r["password_mode"] = "generate"  # build step reuses the generated password
            else:
                res.err("rescue.password_auth", "needs a password: set rescue.password_hash, or give the first user a password")
    elif rh is not None:
        res.warn("rescue.password_hash", "ignored because rescue.password_auth is false")
        r.pop("password_hash", None)
    if r["enabled"] and not rk and not r["password_auth"]:
        res.err("rescue.authorized_keys", "rescue needs a way in: at least one SSH key (on the first user or here), or rescue.password_auth = true with a password")
    lip, lpt = r.get("log_receiver_ip"), r.get("log_receiver_port")
    if lip:
        _ipv4(res, "rescue.log_receiver_ip", lip)
        if lpt is None:
            res.err("rescue.log_receiver_port", "required with log_receiver_ip")
        elif not 1 <= lpt <= 65535:
            res.err("rescue.log_receiver_port", "must be 1-65535")
    elif lpt is not None:
        res.err("rescue.log_receiver_ip", "required with log_receiver_port")

    # --- os ---------------------------------------------------------------------
    o = c["os"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", o["profile"]):
        res.err("os.profile", "invalid profile name")
    if o.get("mirror") and not re.fullmatch(r"https?://[^\s]+", o["mirror"]):
        res.err("os.mirror", "must be an http(s) URL")
    k = o["kernel"]
    if k["source"] not in CHOICES["os.kernel.source"]:
        res.err("os.kernel.source", "must be distro, files or custom")
    if k["source"] == "files":
        for field in ("image", "initrd", "release"):
            if not k.get(field):
                res.err("os.kernel." + field, "required when source = \"files\"")
        for field in ("image", "initrd", "modules", "config"):
            p = k.get(field)
            if p:
                full = os.path.expanduser(p)
                if not os.path.isabs(full):
                    full = os.path.join(base_dir, full)
                if not os.path.exists(full):
                    res.err("os.kernel." + field, "%s does not exist" % full)
        if not k.get("modules"):
            res.warn("os.kernel.modules", "no modules supplied; drivers built as modules will be missing")
        if not k.get("config"):
            res.warn("os.kernel.config", "no .config supplied; the kernel contract cannot be checked before booting")
    extra = k["cmdline_extra"]
    if not CMDLINE_RE.match(extra):
        res.err("os.kernel.cmdline_extra", "allowed characters: letters, digits and _ . , = : / + - and space")
    elif len(extra) > 1024:
        res.err("os.kernel.cmdline_extra", "too long (max 1024)")
    else:
        for tok in extra.split():
            if tok.split("=")[0] in ("root", "init", "rootfstype"):
                res.err("os.kernel.cmdline_extra", "%s= is managed by the installer; remove it" % tok.split("=")[0])
    feats = o["features"]
    if feats.get("vpu") and feats.get("gpu") is False:
        res.err("os.features.vpu", "video decode needs the GPU feature (the VPU device-tree fix builds on it)")
    for pkg in o["packages"]["extra"]:
        if not PKG_RE.match(pkg):
            res.err("os.packages.extra", "invalid package name %r" % pkg)

    # --- storage / install ----------------------------------------------------------
    st = c["storage"]
    if st["layout"] not in CHOICES["storage.layout"]:
        res.err("storage.layout", "must be auto, v2 or factory")
    rs = st["root_size"]
    if rs != "fill" and not (re.fullmatch(r"[0-9]{3,6}", rs) and int(rs) >= 512):
        res.err("storage.root_size", "must be \"fill\" or a size in MiB of at least 512")
    if st.get("esp_size_mib") is not None and not 8 <= st["esp_size_mib"] <= 512:
        res.err("storage.esp_size_mib", "must be 8-512")
    i = c["install"]
    if i["method"] not in CHOICES["install.method"]:
        res.err("install.method", "must be uuu or ssh")
    if i["method"] == "ssh":
        if not i.get("ssh_host"):
            res.err("install.ssh_host", "required for ssh installs")
        if st["layout"] == "v2":
            res.err("storage.layout", "v2 (64 MiB ESP) needs a repartitioned disk, so it is only available with install.method = \"uuu\"")
    if not 1 <= i["ssh_port"] <= 65535:
        res.err("install.ssh_port", "must be 1-65535")
    if not USER_RE.match(i["ssh_user"]):
        res.err("install.ssh_user", "invalid login name")
    return res
