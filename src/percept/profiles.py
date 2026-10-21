# SPDX-License-Identifier: MIT
"""OS/kernel profiles: what a profile declares and how a board config resolves
against it (features, device-tree fixups chosen by kernel release, cmdline)."""
import fnmatch
import os
import re

from . import tomlmini

KNOWN_FIXUPS = ("upper-ram", "thermal", "media-gpu", "media-gpu-vpu", "usbc-extcon")
LAUNCHER_ORDER = ("upper-ram", "thermal", "media-gpu", "media-gpu-vpu")  # order the launcher runs them
FIXUP_STAGES = ("launcher", "esp-dtb")
STATUSES = ("tested", "community", "experimental")
ROOTFS_TYPES = ("debootstrap", "tarball", "prebuilt")
BUILDERS = ("qemu-user", "container", "native-board")
KERNEL_SOURCES = ("distro", "files", "custom")
KERNEL_FORMATS = ("Image", "Image.gz")
FEATURES = ("gpu", "vpu", "usb_c_host", "camera", "upper_ram", "thermal")
CMDLINE_RE = re.compile(r"^[A-Za-z0-9_.,=:/+ -]*$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class ProfileError(Exception):
    pass


def profiles_root(repo_root):
    return os.path.join(repo_root, "profiles")


def list_profiles(repo_root):
    root = profiles_root(repo_root)
    out = []
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if os.path.isfile(os.path.join(root, name, "profile.toml")) and not name.startswith("_"):
            out.append(name)
    return out


def load_profile(path):
    """Load ``profiles/<id>/profile.toml`` (or a directory containing it)."""
    f = os.path.join(path, "profile.toml") if os.path.isdir(path) else path
    try:
        p = tomlmini.load_file(f)
    except (OSError, tomlmini.TomlError) as exc:
        raise ProfileError(str(exc)) from None
    p["_dir"] = os.path.dirname(os.path.abspath(f))
    return p


def check_profile(p, dir_name=None):
    """Return a list of problems (empty = fine)."""
    bad = []

    def need(table, key, where, kinds=(str,)):
        v = table.get(key)
        if v is None:
            bad.append("%s.%s is required" % (where, key))
        elif not isinstance(v, kinds):
            bad.append("%s.%s has the wrong type" % (where, key))
        return v

    if p.get("schema") != 1:
        bad.append("schema must be 1")
    pid = need(p, "id", "profile")
    if isinstance(pid, str):
        if not ID_RE.match(pid):
            bad.append("profile.id is not a valid name")
        if dir_name and pid != dir_name:
            bad.append("profile.id %r does not match directory %r" % (pid, dir_name))
    need(p, "title", "profile")
    if need(p, "status", "profile") not in STATUSES:
        bad.append("profile.status must be one of %s" % ", ".join(STATUSES))

    rf = p.get("rootfs", {})
    rt = need(rf, "type", "rootfs")
    if rt not in ROOTFS_TYPES:
        bad.append("rootfs.type must be one of %s" % ", ".join(ROOTFS_TYPES))
    if rt == "debootstrap":
        need(rf, "suite", "rootfs")
        need(rf, "mirror", "rootfs")
    if rt in ("tarball", "prebuilt"):
        need(rf, "sha256", "rootfs")
    if rf.get("builder", "qemu-user") not in BUILDERS:
        bad.append("rootfs.builder must be one of %s" % ", ".join(BUILDERS))
    if not isinstance(rf.get("min_size_mib", 2048), int):
        bad.append("rootfs.min_size_mib must be a number")
    hooks = rf.get("hooks", [])
    if not isinstance(hooks, list) or any(not isinstance(h, str) or "/" in h or ".." in h for h in hooks):
        bad.append("rootfs.hooks must be a list of file names inside hooks/")
    else:
        for h in hooks:
            if not os.path.isfile(os.path.join(p.get("_dir", "."), "hooks", h)):
                bad.append("rootfs.hooks: hooks/%s does not exist" % h)

    k = p.get("kernel", {})
    if need(k, "source", "kernel") not in KERNEL_SOURCES:
        bad.append("kernel.source must be one of %s" % ", ".join(KERNEL_SOURCES))
    if k.get("format", "Image") not in KERNEL_FORMATS:
        bad.append("kernel.format must be Image or Image.gz")
    for key in ("validated_releases",):
        v = k.get(key, [])
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
            bad.append("kernel.%s must be a list of strings" % key)

    c = p.get("contract", {})
    base = need(c, "cmdline_baseline", "contract")
    if isinstance(base, str) and not CMDLINE_RE.match(base):
        bad.append("contract.cmdline_baseline has characters the launcher rejects")
    for key in ("config_required", "initramfs_modules"):
        v = c.get(key, [])
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
            bad.append("contract.%s must be a list of strings" % key)

    feats = p.get("features", {})
    for name, spec in feats.items():
        if name not in FEATURES:
            bad.append("features.%s is not a known feature" % name)
            continue
        if not isinstance(spec, dict) or not isinstance(spec.get("default", False), bool):
            bad.append("features.%s needs 'default = true|false'" % name)
            continue
        for r in spec.get("requires", []):
            if r not in FEATURES:
                bad.append("features.%s.requires unknown feature %r" % (name, r))

    seen = set()
    for i, fx in enumerate(p.get("fixup", [])):
        w = "fixup[%d]" % i
        name = fx.get("name")
        if name not in KNOWN_FIXUPS:
            bad.append("%s.name %r must be one of %s" % (w, name, ", ".join(KNOWN_FIXUPS)))
        elif name in seen:
            bad.append("%s.name %r listed twice" % (w, name))
        seen.add(name)
        ks = fx.get("kernels")
        if not isinstance(ks, list) or not ks or any(not isinstance(x, str) for x in ks):
            bad.append("%s.kernels must be a non-empty list of release globs" % w)
        if fx.get("stage", "launcher") not in FIXUP_STAGES:
            bad.append("%s.stage must be launcher or esp-dtb" % w)
        for r in fx.get("when", {}):
            if r not in FEATURES:
                bad.append("%s.when has unknown feature %r" % (w, r))
    return bad


def kernel_release(cfg, profile):
    """The release string fixups are matched against."""
    k = cfg["os"]["kernel"]
    if k["source"] == "files":
        return k["release"]
    validated = profile.get("kernel", {}).get("validated_releases") or []
    return validated[0] if validated else profile.get("kernel", {}).get("pin", "")


def effective_features(cfg, profile):
    """Merge profile defaults with the board's explicit choices; return (features, problems)."""
    spec = profile.get("features", {})
    chosen = cfg["os"]["features"]
    out, problems = {}, []
    for name in FEATURES:
        default = bool(spec.get(name, {}).get("default", False))
        v = chosen.get(name)
        out[name] = default if v is None else bool(v)
    for name, on in out.items():
        if not on:
            continue
        if name not in spec:
            problems.append("feature %r is not offered by profile %s" % (name, profile.get("id")))
            continue
        for r in spec[name].get("requires", []):
            if not out.get(r):
                problems.append("feature %r requires %r" % (name, r))
    return out, problems


PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"


def resolve(cfg, profile, rootfs_uuid=PLACEHOLDER_UUID):
    """Turn (validated board config, profile) into launcher-ready settings."""
    release = kernel_release(cfg, profile)
    feats, problems = effective_features(cfg, profile)
    warnings = []
    validated = profile.get("kernel", {}).get("validated_releases", [])
    if cfg["os"]["kernel"]["source"] == "files" and not any(fnmatch.fnmatch(release, g) for g in validated):
        warnings.append("kernel %s is outside this profile's validated releases %s" % (release, validated or "(none)"))

    fixups = {"launcher": [], "esp-dtb": []}
    for fx in profile.get("fixup", []):
        if not any(fnmatch.fnmatch(release, g) for g in fx["kernels"]):
            continue
        feat = fx.get("feature")
        if feat and not feats.get(feat):
            continue
        when = fx.get("when", {})
        if any(feats.get(f) != bool(v) for f, v in when.items()):
            continue
        fixups[fx.get("stage", "launcher")].append(fx["name"])
    fixups["launcher"].sort(key=lambda n: LAUNCHER_ORDER.index(n) if n in LAUNCHER_ORDER else 99)

    base = profile["contract"]["cmdline_baseline"]
    extra = cfg["os"]["kernel"]["cmdline_extra"].strip()
    cmdline = " ".join(x for x in ("root=UUID=%s ro" % rootfs_uuid, base, extra) if x)
    boot = profile.get("boot", {})
    return {
        "release": release,
        "features": feats,
        "fixups": fixups,
        "cmdline": cmdline,
        "kernel_path": boot.get("kernel_path", "/vmlinuz"),
        "initrd_path": boot.get("initrd_path", "/initrd.img"),
        "problems": problems,
        "warnings": warnings,
    }
