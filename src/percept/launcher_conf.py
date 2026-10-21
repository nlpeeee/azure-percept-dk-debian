# SPDX-License-Identifier: MIT
"""Generate and lint the ESP files the launcher reads.

``compat="current"`` emits only the keys the shipped launcher/init understands.
``compat="v2"`` emits the generalised key set specified in docs/launcher-conf.md
(implemented by the launcher in milestone M4). ``parse`` mirrors init's rules,
including rejecting unknown keys, so generated files are checked against it.
"""
import re

CURRENT_KEYS = ("mode", "kernel", "initrd", "cmdline", "kernel_sha256", "initrd_sha256",
                "upper_ram", "thermal_fix", "media", "cpu_profile")
V2_KEYS = CURRENT_KEYS + (
    "profile", "root", "root_fstype", "root_opts", "kernel_format", "board_model",
    "net_mode", "net_if", "net_ip", "net_prefix", "net_gw",
    "log_receiver_ip", "log_receiver_port", "fail_limit", "rescue_console",
    "dtb_fixups", "dtb_fixups_policy",
)
CMDLINE_RE = re.compile(r"^[A-Za-z0-9_.,=:/+ -]+$")
PATH_RE = re.compile(r"^/[A-Za-z0-9_.+/-]*$")
GRUBENV_SIZE = 1024


class LauncherConfError(ValueError):
    pass


def render(resolved, cfg, compat="current"):
    """Production launcher.conf text for a resolved profile + board config."""
    f = resolved["fixups"]["launcher"]
    media = "gpu-vpu" if "media-gpu-vpu" in f else "gpu" if "media-gpu" in f else "none"
    lines = ["mode=kexec", "kernel=" + resolved["kernel_path"], "initrd=" + resolved["initrd_path"]]
    if compat == "current":
        lines += ["upper_ram=%d" % ("upper-ram" in f), "thermal_fix=%d" % ("thermal" in f), "media=" + media]
    else:
        lines += ["dtb_fixups=" + ",".join(f), "dtb_fixups_policy=skip-inapplicable"]
        lines += rescue_network_lines(cfg)
        lines.append("fail_limit=%d" % cfg["rescue"]["fail_limit"])
    lines.append("cmdline=" + resolved["cmdline"])
    text = "\n".join(lines) + "\n"
    parse(text, compat)  # never emit something the launcher would reject
    return text


def rescue_network_lines(cfg):
    r = cfg["rescue"]
    if r["net_mode"] == "dhcp":
        out = ["net_mode=dhcp", "net_if=auto"]
    else:
        out = ["net_mode=static", "net_if=auto", "net_ip=" + r["address"], "net_prefix=%d" % r["prefix"]]
        if r.get("gateway"):
            out.append("net_gw=" + r["gateway"])
    if r.get("log_receiver_ip"):
        out += ["log_receiver_ip=" + r["log_receiver_ip"], "log_receiver_port=%d" % r["log_receiver_port"]]
    return out


def render_rescue(cfg, compat="current"):
    """launcher.conf that forces rescue mode (also the safe default for a fresh ESP)."""
    if compat == "current":
        return "mode=rescue\n"
    return "mode=rescue\n" + "\n".join(rescue_network_lines(cfg)) + "\n"


def parse(text, compat="current"):
    """Parse like init: strict keys, simple value rules. Returns an ordered dict."""
    allowed = CURRENT_KEYS if compat == "current" else V2_KEYS
    out = {}
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip("\r")
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise LauncherConfError("line %d: malformed" % n)
        key, value = line.split("=", 1)
        if key not in allowed:
            raise LauncherConfError("line %d: unknown key %r" % (n, key))
        out[key] = value
    mode = out.get("mode", "kexec")
    if mode not in ("kexec", "rescue"):
        raise LauncherConfError("invalid mode")
    if compat != "current":
        _check_v2(out)
    if mode == "kexec":
        for key in ("kernel", "initrd"):
            if key in out and not PATH_RE.match(out[key]):
                raise LauncherConfError("invalid %s path" % key)
        if not out.get("cmdline") or not CMDLINE_RE.match(out["cmdline"]):
            raise LauncherConfError("invalid or empty cmdline")
        if out.get("media", "none") not in ("none", "gpu", "gpu-vpu"):
            raise LauncherConfError("invalid media")
        for key in ("upper_ram", "thermal_fix"):
            if out.get(key, "0") not in ("0", "1"):
                raise LauncherConfError("invalid " + key)
        if compat != "current":
            legacy = [k for k in ("upper_ram", "thermal_fix", "media") if k in out]
            if legacy and "dtb_fixups" in out:
                raise LauncherConfError("legacy fixup keys mixed with dtb_fixups")
    return out


def _check_v2(out):
    """Value rules of the v2 keys; must stay in step with launcher/lib/percept-config.sh."""
    import ipaddress

    def ip(key):
        try:
            ipaddress.IPv4Address(out[key])
        except ValueError:
            raise LauncherConfError("invalid " + key) from None

    def num(key, lo, hi):
        if not out[key].isdigit() or not lo <= int(out[key]) <= hi:
            raise LauncherConfError("invalid " + key)

    if out.get("net_mode", "dhcp") not in ("dhcp", "static", "none"):
        raise LauncherConfError("invalid net_mode")
    if out.get("net_mode") == "static":
        for key in ("net_ip", "net_prefix"):
            if key not in out:
                raise LauncherConfError("static net_mode needs " + key)
    for key in ("net_ip", "net_gw", "log_receiver_ip"):
        if out.get(key):
            ip(key)
    if "net_prefix" in out:
        num("net_prefix", 1, 30)
    if "log_receiver_port" in out:
        num("log_receiver_port", 1, 65535)
    if "fail_limit" in out:
        num("fail_limit", 1, 10)
    if out.get("dtb_fixups_policy", "skip-inapplicable") not in ("skip-inapplicable", "strict"):
        raise LauncherConfError("invalid dtb_fixups_policy")
    for name in filter(None, out.get("dtb_fixups", "").split(",")):
        if name not in ("upper-ram", "thermal", "media-gpu", "media-gpu-vpu"):
            raise LauncherConfError("invalid dtb_fixups entry")
    if out.get("profile", "percept-dk") != "percept-dk":
        raise LauncherConfError("invalid profile")
    if out.get("kernel_format", "auto") not in ("auto", "Image", "Image.gz"):
        raise LauncherConfError("invalid kernel_format")


def grubenv(tries):
    """The 1024-byte GRUB environment block with ``percept_tries=<tries>``."""
    if not 0 <= tries <= 4:
        raise ValueError("tries must be 0-4")
    head = ("# GRUB Environment Block\npercept_tries=%d\n" % tries).encode("ascii")
    return head + b"#" * (GRUBENV_SIZE - len(head))


def rescue_esp_files(cfg):
    """Files for the ESP's percept/ directory that carry rescue credentials: {name: bytes}.

    ``rescue_password_hash`` is present only when password login is enabled and a hash is known
    (a generated password is filled in by the build step).
    """
    r = cfg["rescue"]
    files = {}
    if r["authorized_keys"]:
        files["authorized_keys"] = ("\n".join(r["authorized_keys"]) + "\n").encode("ascii")
    if r["password_auth"] and r.get("password_hash"):
        files["rescue_password_hash"] = (r["password_hash"] + "\n").encode("ascii")
    return files


def failcount(value=0):
    return ("%d\n" % value).encode("ascii")
