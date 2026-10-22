#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail if the tree contains per-board identifiers, secrets or oversized files.

    python dev/scrub-scan.py [ROOT]            # scan a working tree
    python dev/scrub-scan.py --git [ROOT]      # scan only tracked + staged-untracked files

A line can opt out with ``scrub-ok`` in a comment (use sparingly, say why).
Files listed in dev/scrub-debt.txt are known board-bound code awaiting
generalisation: their hits are reported as debt and do not fail the scan unless
--strict is given (the release gate). Any hit elsewhere always fails.
"""
import os
import re
import subprocess
import sys

MAX_BYTES = 1_000_000
SKIP_DIRS = {".git", "__pycache__", "cache", "out", "boards", "node_modules", ".venv"}
SKIP_FILES = {"scrub-scan.py"}  # holds the patterns themselves

# (name, regex). Case-insensitive unless noted in the pattern.
PATTERNS = [
    ("board-1 MAC", r"fc:34:97:65:90:a0"),
    ("lab IP 192.168.1.60/.47", r"192\.168\.1\.(60|47)\b"),
    ("board-1 root UUID", r"a842734f-25d2-4bc4-8e1f-11ede151471f"),
    ("other board UUID", r"4df3ecc1-[0-9a-f-]{27}"),
    ("board-1 ESP serial", r"\b8AB1-C6BE\b"),
    ("lab serial port", r"\bCOM8\b"),
    ("lab Windows path", r"\b[A-Z]:[/\\]percept\b"),
    ("lab build dir", r"/root/percept-kexec-work"),
    ("default password", r"(?<![\w/.-])percept/percept(?![\w-])|PASSWORD=\"percept\"|password: percept"),
    ("SSH public key material", r"ssh-(ed25519|rsa|dss)\s+AAAA[0-9A-Za-z+/=]{20,}|ecdsa-sha2-\S+\s+AAAA[0-9A-Za-z+/=]{20,}"),
    ("private key block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("host key checking off", r"StrictHostKeyChecking[= ]+no\b"),
    ("test key name", r"claude-percept-test|copilot-deploy"),
    ("personal e-mail", r"neil@polli\.co\.tt"),
]
COMPILED = [(n, re.compile(p, re.I)) for n, p in PATTERNS]


def tracked_files(root):
    out = subprocess.run(["git", "-c", "safe.directory=*", "ls-files", "-z", "--cached", "--others",
                          "--exclude-standard"], cwd=root, check=True, capture_output=True).stdout
    return [os.path.join(root, p) for p in out.decode().split("\0") if p]


def walk(root):
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            yield os.path.join(base, f)


def scan(root, use_git=False):
    findings = []
    files = tracked_files(root) if use_git else walk(root)
    for path in files:
        rel = os.path.relpath(path, root).replace("\\", "/")
        if os.path.basename(path) in SKIP_FILES or not os.path.isfile(path):
            continue
        size = os.path.getsize(path)
        if size > MAX_BYTES:
            findings.append((rel, 0, "file over 1 MB (%d bytes)" % size, ""))
            continue
        with open(path, "rb") as f:
            data = f.read()
        if b"\0" in data[:4096]:
            continue  # binary; size already checked
        for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            if "scrub-ok" in line:
                continue
            for name, rx in COMPILED:
                if rx.search(line):
                    findings.append((rel, n, name, line.strip()[:100]))
    return findings


def load_debt(root):
    path = os.path.join(root, "dev", "scrub-debt.txt")
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip() and not l.startswith("#")}


def main(argv):
    use_git = "--git" in argv
    strict = "--strict" in argv
    args = [a for a in argv if not a.startswith("--")]
    root = os.path.abspath(args[0] if args else os.path.join(os.path.dirname(__file__), ".."))
    debt = set() if strict else load_debt(root)
    findings = scan(root, use_git)
    new = [f for f in findings if f[0] not in debt]
    old = [f for f in findings if f[0] in debt]
    for rel, n, name, text in new:
        print("%s:%d: %s: %s" % (rel, n, name, text))
    print("%d finding(s) in %s (%d known-debt hits in %d files)" % (
        len(new), root, len(old), len({f[0] for f in old})))
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
