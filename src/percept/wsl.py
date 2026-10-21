# SPDX-License-Identifier: MIT
"""Windows / WSL2 plumbing: detect where we run, list distros, translate paths,
and run Linux commands from Windows. All process execution goes through a
``Runner`` so tests can substitute a fake."""
import os
import re
import shutil
import subprocess

_DRIVE = re.compile(r"^([A-Za-z]):[\\/](.*)$")
_MNT = re.compile(r"^/mnt/([a-z])(?:/(.*))?$")
_UNC = re.compile(r"^\\\\(?:wsl\.localhost|wsl\$)\\([^\\]+)\\?(.*)$", re.I)


def run(argv, timeout=60, input_text=None):
    """Default runner: returns (returncode, stdout_text, stderr_text); never raises on exit status."""
    try:
        p = subprocess.run(argv, capture_output=True, timeout=timeout,
                           input=input_text.encode() if input_text else None)
    except FileNotFoundError:
        return 127, "", "%s: not found" % argv[0]
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after %ds" % timeout
    return p.returncode, decode_output(p.stdout), decode_output(p.stderr)


def decode_output(raw):
    """wsl.exe writes UTF-16LE; everything else is UTF-8."""
    if not raw:
        return ""
    if b"\x00" in raw:
        try:
            return raw.decode("utf-16-le").lstrip("\ufeff")
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace")


def host_kind(proc_version="/proc/version"):
    """'windows', 'wsl', 'linux', 'macos' or 'other'."""
    if os.name == "nt":
        return "windows"
    try:
        with open(proc_version, encoding="utf-8", errors="replace") as f:
            if "microsoft" in f.read().lower():
                return "wsl"
    except OSError:
        pass
    import sys
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    return "other"


def win_to_wsl_path(path):
    """C:\\Users\\me\\x -> /mnt/c/Users/me/x ; \\\\wsl.localhost\\Debian\\home\\me -> /home/me."""
    m = _UNC.match(path)
    if m:
        return "/" + m.group(2).replace("\\", "/").strip("/")
    m = _DRIVE.match(path)
    if not m:
        raise ValueError("not a Windows path: %r" % path)
    return "/mnt/%s/%s" % (m.group(1).lower(), m.group(2).replace("\\", "/"))


def wsl_to_win_path(path, distro=None):
    """/mnt/c/x -> C:\\x ; other absolute paths -> \\\\wsl.localhost\\<distro>\\..."""
    m = _MNT.match(path)
    if m:
        rest = (m.group(2) or "").replace("/", "\\")
        return "%s:\\%s" % (m.group(1).upper(), rest)
    if not path.startswith("/"):
        raise ValueError("not an absolute Linux path: %r" % path)
    if not distro:
        raise ValueError("distro name needed for a path outside /mnt")
    return "\\\\wsl.localhost\\%s%s" % (distro, path.replace("/", "\\"))


def wsl_exe():
    return shutil.which("wsl.exe") or shutil.which("wsl")


def list_distros(runner=run):
    """Names of installed WSL distros (docker-desktop helpers excluded)."""
    rc, out, _ = runner(["wsl.exe", "-l", "-q"])
    if rc != 0:
        return []
    names = [l.strip() for l in out.splitlines() if l.strip()]
    return [n for n in names if not n.startswith("docker-desktop")]


def wsl_version2(distro, runner=run):
    rc, out, _ = runner(["wsl.exe", "-l", "-v"])
    for line in out.splitlines():
        parts = line.replace("*", " ").split()
        if parts and parts[0] == distro:
            return parts[-1] == "2"
    return None


def in_distro(distro, shell_cmd, runner=run, timeout=60):
    """Run ``sh -c shell_cmd`` inside a distro as the default user."""
    return runner(["wsl.exe", "-d", distro, "--", "sh", "-c", shell_cmd], timeout)


def reexec_argv(distro, repo_wsl_path, args):
    """argv to run ``python3 -m percept <args>`` inside the distro from the repo root."""
    return ["wsl.exe", "-d", distro, "--cd", repo_wsl_path, "--", "env", "PYTHONPATH=src",
            "python3", "-m", "percept"] + list(args)
