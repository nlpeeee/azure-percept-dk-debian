# SPDX-License-Identifier: MIT
"""`percept doctor`: check this PC (and WSL2) and say exactly how to fix gaps."""
import os
import shutil
import sys
from collections import namedtuple

from . import wsl

Check = namedtuple("Check", "status name detail fix")  # status: ok | warn | fail | info
MIN_FREE_GB = 30
MIN_PYTHON = (3, 9)

# command -> (apt package, why)
LINUX_TOOLS = {
    "debootstrap": ("debootstrap", "builds the Debian root filesystem"),
    "mke2fs": ("e2fsprogs", "creates the root filesystem image without root"),
    "debugfs": ("e2fsprogs", "extracts files from Microsoft's image without root"),
    "mkfs.vfat": ("dosfstools", "creates the EFI system partition"),
    "mcopy": ("mtools", "writes files into the EFI partition image"),
    "unshare": ("util-linux", "private mount namespaces and rootless chroot"),
    "newuidmap": ("uidmap", "gives the rootless build a full range of user ids (debootstrap needs them)"),
    "xz": ("xz-utils", "unpacks kernel sources"),
    "zstd": ("zstd", "compresses the root filesystem"),
    "tar": ("tar", "archives"),
    "curl": ("curl", "downloads vendor inputs"),
    "unzip": ("unzip", "reads Microsoft's recovery package"),
    "qemu-aarch64-static": ("qemu-user-static", "runs arm64 programs while building"),
}


def _ok(name, detail=""):
    return Check("ok", name, detail, "")


def _warn(name, detail, fix=""):
    return Check("warn", name, detail, fix)


def _fail(name, detail, fix=""):
    return Check("fail", name, detail, fix)


def check_python(version=None):
    v = tuple(version or sys.version_info[:3])
    s = ".".join(str(x) for x in v)
    if v[:2] < MIN_PYTHON:
        return _fail("python", "%s is too old" % s, "install Python %d.%d or newer" % MIN_PYTHON)
    return _ok("python", s)


def check_disk(path, free_bytes=None, need_gb=MIN_FREE_GB):
    free = free_bytes if free_bytes is not None else shutil.disk_usage(path).free
    gb = free / 1e9
    if gb < need_gb:
        return _warn("disk space", "%.0f GB free in %s, %d GB recommended" % (gb, path, need_gb),
                     "free some space; builds and the 1.1 GB Microsoft download need room")
    return _ok("disk space", "%.0f GB free" % gb)


def check_boards_ignored(repo_root, runner=wsl.run):
    """boards/ and secrets must be git-ignored so they cannot be committed by accident."""
    if not os.path.isdir(os.path.join(repo_root, ".git")):
        return _ok("secrets ignored", "not a git checkout")
    probe = ["boards/example/secrets.toml", "boards/example/board.toml"]
    for p in probe:
        rc, _, _ = runner(["git", "-c", "safe.directory=*", "-C", repo_root, "check-ignore", "-q", p])
        if rc == 127:
            return _ok("secrets ignored", "git not available to check")
        if rc != 0:
            return _fail("secrets ignored", "%s is not git-ignored" % p, "restore the boards/ rules in .gitignore")
    return _ok("secrets ignored", "boards/ is git-ignored")


def check_windows_side(runner=wsl.run, which=shutil.which, repo_root="."):
    out = []
    uuu = which("uuu.exe") or which("uuu")
    cached = os.path.join(repo_root, "cache", "tools", "uuu.exe")
    if uuu or os.path.isfile(cached):
        out.append(_ok("uuu", uuu or cached))
    else:
        out.append(_warn("uuu", "not found yet", "'percept flash' downloads it (needed only to flash)"))
    out.append(_ok("ssh", which("ssh") or which("ssh.exe")) if (which("ssh") or which("ssh.exe")) else
               _warn("ssh", "OpenSSH client not found", "Settings > Apps > Optional features > OpenSSH Client"))
    return out


def check_wsl(runner=wsl.run, which=shutil.which):
    """Windows-only: WSL2 installed with a usable distro. Returns (checks, distro_or_None)."""
    if not (which("wsl.exe") or which("wsl")):
        return [_fail("WSL", "wsl.exe not found", "run 'wsl --install' in an administrator PowerShell, then reboot")], None
    distros = wsl.list_distros(runner)
    if not distros:
        return [_fail("WSL distro", "WSL has no Linux distribution installed",
                      "run 'wsl --install -d Debian' (or Ubuntu), finish its first-run user setup")], None
    distro = distros[0]
    v2 = wsl.wsl_version2(distro, runner)
    checks = [_ok("WSL distro", distro)]
    if v2 is False:
        checks.append(_fail("WSL version", "%s is WSL1" % distro, "run 'wsl --set-version %s 2'" % distro))
    elif v2:
        checks.append(_ok("WSL version", "2"))
    return checks, distro


def check_linux_tools(run_cmd):
    """``run_cmd(shell_command) -> (rc, out, err)`` runs on the Linux side (native or via WSL)."""
    checks = []
    missing = {}
    for tool, (pkg, why) in LINUX_TOOLS.items():
        rc, _, _ = run_cmd("command -v %s" % tool)
        if rc == 0:
            checks.append(_ok(tool))
        else:
            missing[pkg] = why
            checks.append(Check("fail", tool, "not installed (%s)" % why, ""))
    if missing:
        checks.append(Check("info", "install missing tools", "sudo apt install " + " ".join(sorted(missing)), ""))
    rc, _, _ = run_cmd("unshare -Ur true")
    checks.append(_ok("rootless namespaces") if rc == 0 else
                  _fail("rootless namespaces", "'unshare -Ur' failed",
                        "enable unprivileged user namespaces (sysctl kernel.unprivileged_userns_clone=1) or upgrade WSL: 'wsl --update'"))
    rc, out, _ = run_cmd("cat /proc/sys/fs/binfmt_misc/qemu-aarch64 2>/dev/null")
    if rc == 0 and "enabled" in out:
        checks.append(_ok("arm64 emulation", "binfmt qemu-aarch64 enabled"))
    else:
        checks.append(_fail("arm64 emulation", "binfmt for qemu-aarch64 is not active",
                            "sudo apt install qemu-user-static binfmt-support, then 'sudo update-binfmts --enable qemu-aarch64' "
                            "(on WSL, 'wsl --shutdown' afterwards if it still shows disabled)"))
    return checks


def run_all(repo_root=".", runner=wsl.run, which=shutil.which, kind=None, linux_runner=None):
    """Return a list of Check results for this host."""
    kind = kind or wsl.host_kind()
    out = [_ok("host", kind), check_python(), check_disk(repo_root), check_boards_ignored(repo_root, runner)]
    if kind == "windows":
        out += check_windows_side(runner, which, repo_root)
        wsl_checks, distro = check_wsl(runner, which)
        out += wsl_checks
        if distro:
            out += check_linux_tools(linux_runner or (lambda cmd: wsl.in_distro(distro, cmd, runner)))
    elif kind in ("linux", "wsl"):
        lr = linux_runner or (lambda cmd: runner(["sh", "-c", cmd]))
        out += check_linux_tools(lr)
        if kind == "wsl":
            out.append(_ok("uuu", "flash from the Windows side with uuu.exe"))
    else:
        out.append(_fail("host", "%s is not supported" % kind, "use Windows with WSL2, or Linux"))
    return out


def run_installer(repo_root):
    """Check the fast path without probing USB, starting WSL or downloading files."""
    out = [check_python(), check_disk(repo_root)]
    for module in ('pyfatfs', 'cryptography'):
        try:
            __import__(module)
            out.append(_ok(module))
        except ImportError:
            out.append(_fail(module, 'not installed', 'install requirements-installer.txt, or use the packaged application'))
    from pathlib import Path
    if (Path(repo_root)/'release/tools.json').is_file():
        try:
            from .flash import resolve_tool
            out.append(_ok('native uuu', str(resolve_tool(repo_root))))
        except (OSError,ValueError,KeyError) as exc:
            out.append(_fail('native uuu',str(exc),'restore the original application package'))
    else:
        out.append(_warn('native uuu','development checkout; use flash --uuu PATH or a packaged application'))
    out.append(_ok('preparation','no WSL, compiler, chroot or filesystem mounts required'))
    return out


def format_checks(checks):
    tag = {"ok": "[ ok ]", "warn": "[warn]", "fail": "[FAIL]", "info": "[info]"}
    lines = []
    for c in checks:
        line = "%s %s" % (tag[c.status], c.name)
        if c.detail:
            line += ": " + c.detail
        lines.append(line)
        if c.fix:
            lines.append("       fix: " + c.fix)
    nfail = sum(c.status == "fail" for c in checks)
    nwarn = sum(c.status == "warn" for c in checks)
    lines.append("")
    lines.append("%d problem(s) to fix, %d warning(s)." % (nfail, nwarn) if nfail or nwarn else
                 "Everything needed so far is in place.")
    return "\n".join(lines)


def exit_code(checks):
    return 1 if any(c.status == "fail" for c in checks) else 0
