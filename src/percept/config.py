# SPDX-License-Identifier: MIT
"""Loading, merging and saving per-board configuration.

A board lives in ``boards/<name>/`` as ``board.toml`` (shareable) plus an
optional ``secrets.toml`` (never share). Both are merged on load. Secret fields
also accept ``<field>_file`` and ``<field>_env`` so secrets can live elsewhere.
"""
import copy
import os
import subprocess
import sys

from . import tomlmini
from .schema import allowed_paths, section_paths


class ConfigError(Exception):
    pass


BOARD_FILE = "board.toml"
SECRETS_FILE = "secrets.toml"


def boards_dir(root):
    return os.path.join(root, "boards")


def board_path(root, name):
    return os.path.join(boards_dir(root), name)


def merge(base, over):
    """Deep-merge ``over`` into a copy of ``base``; ``user`` entries merge by name."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k == "user" and isinstance(v, list) and isinstance(out.get(k), list):
            by_name = {u.get("name"): u for u in out[k]}
            for u in v:
                if u.get("name") in by_name:
                    by_name[u["name"]].update(copy.deepcopy(u))
                else:
                    out[k].append(copy.deepcopy(u))
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_board(directory):
    """Load and merge board.toml + secrets.toml. Does not validate."""
    main = os.path.join(directory, BOARD_FILE)
    if not os.path.isfile(main):
        raise ConfigError("no %s in %s" % (BOARD_FILE, directory))
    try:
        cfg = tomlmini.load_file(main)
        sec = os.path.join(directory, SECRETS_FILE)
        if os.path.isfile(sec):
            cfg = merge(cfg, tomlmini.load_file(sec))
    except tomlmini.TomlError as exc:
        raise ConfigError(str(exc)) from None
    return cfg


def unknown_keys(cfg):
    """Dotted paths in ``cfg`` that are not in the schema (typos are errors)."""
    allowed = allowed_paths()
    sections = section_paths()
    bad = []

    def walk(node, prefix):
        for k, v in node.items():
            path = prefix + k
            if isinstance(v, dict):
                if path not in sections:
                    bad.append(path)
                else:
                    walk(v, path + ".")
            elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                if path not in sections:
                    bad.append(path)
                else:
                    for item in v:
                        walk(item, path + ".")
            elif path not in allowed:
                bad.append(path)

    walk(cfg, "")
    return sorted(set(bad))


def resolve_references(cfg, base_dir, env=None):
    """Replace ``x_file`` / ``x_env`` with ``x`` for secret-bearing fields.

    Returns a new dict. Raises ConfigError for unreadable files / unset vars.
    """
    env = os.environ if env is None else env
    out = copy.deepcopy(cfg)

    def fix(table, where):
        for key in [k for k in list(table) if k.endswith("_file") or k.endswith("_env")]:
            stem = key.rsplit("_", 1)[0]
            if stem == "authorized_keys":  # handled by validate (list of lines)
                continue
            if key.endswith("_file"):
                path = os.path.expanduser(table[key])
                if not os.path.isabs(path):
                    path = os.path.join(base_dir, path)
                try:
                    with open(path, encoding="utf-8") as f:
                        value = f.read().strip()
                except OSError as exc:
                    raise ConfigError("%s.%s: cannot read %s (%s)" % (where, key, path, exc.strerror)) from None
            else:
                name = table[key]
                if name not in env:
                    raise ConfigError("%s.%s: environment variable %s is not set" % (where, key, name))
                value = env[name].strip()
            if stem in table and table[stem] != value:
                raise ConfigError("%s: both %s and %s are set" % (where, stem, key))
            table[stem] = value
            del table[key]

    for sect, val in out.items():
        if isinstance(val, dict):
            for sub, v2 in list(val.items()):
                if isinstance(v2, dict):
                    fix(v2, "%s.%s" % (sect, sub))
            fix(val, sect)
        elif isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, dict):
                    fix(item, "%s[%d]" % (sect, i))
    return out


def restrict_permissions(path):
    """Owner-only access: chmod 600 on POSIX, icacls on Windows (best effort)."""
    try:
        if os.name == "nt":
            user = os.environ.get("USERNAME")
            if user:
                subprocess.run(["icacls", path, "/inheritance:r", "/grant:r", "%s:(F)" % user],
                               capture_output=True, check=False)
        else:
            os.chmod(path, 0o600)
    except OSError as exc:  # pragma: no cover
        print("warning: could not restrict permissions on %s: %s" % (path, exc), file=sys.stderr)


def write_private(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    restrict_permissions(path)


def split_secrets(cfg):
    """Split a config into (public, secret) halves by schema secret paths."""
    from .schema import secret_paths
    secret = secret_paths()
    pub = copy.deepcopy(cfg)
    sec = {}

    def move(table_pub, table_sec, prefix):
        for k in list(table_pub):
            path = prefix + k
            v = table_pub[k]
            if isinstance(v, dict):
                sub = {}
                move(v, sub, path + ".")
                if sub:
                    table_sec[k] = sub
            elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                subs = []
                for item in v:
                    s = {}
                    move(item, s, path + ".")
                    if s:
                        if "name" in item:
                            s["name"] = item["name"]
                        subs.append(s)
                if subs:
                    table_sec[k] = subs
            elif path in secret:
                table_sec[k] = v
                del table_pub[k]

    move(pub, sec, "")
    return pub, sec


def absolutize_file_refs(cfg, base_dir):
    """Make relative ``*_file`` / ``authorized_keys_file`` paths absolute (for configs read from elsewhere)."""
    out = copy.deepcopy(cfg)

    def fix(table):
        for k, v in list(table.items()):
            if isinstance(v, dict):
                fix(v)
            elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                for item in v:
                    fix(item)
            elif k.endswith("_file") and isinstance(v, str):
                path = os.path.expanduser(v)
                table[k] = path if os.path.isabs(path) else os.path.abspath(os.path.join(base_dir, path))

    fix(out)
    return out
