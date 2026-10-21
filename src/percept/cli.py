# SPDX-License-Identifier: MIT
"""Command-line entry point: ``python percept <command>``."""
import argparse
import getpass
import os
import sys
import subprocess

from . import __version__, config as cfgmod, configdoc, configure, doctor, launcher_conf, profiles
from . import redact, sha512crypt, tomlmini, validate

PLANNED = {
    "flash": "M5 - flash an image with uuu",
    "install-over-ssh": "M6 - convert a running board",
    "verify": "M7 - run board-tests against a board",
    "recover": "M7 - USB recovery helpers",
    "find": "M7 - locate a board on the LAN",
}


def repo_root():
    env = os.environ.get("PERCEPT_ROOT")
    if env:
        return os.path.abspath(env)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _board_dir(root, spec):
    if os.path.isdir(spec) and os.path.isfile(os.path.join(spec, cfgmod.BOARD_FILE)):
        return os.path.abspath(spec)
    return cfgmod.board_path(root, spec)


def _load_validated(root, spec, out=print):
    d = _board_dir(root, spec)
    try:
        cfg = cfgmod.load_board(d)
    except cfgmod.ConfigError as exc:
        out("error: %s" % exc)
        return None, None, d
    res = validate.validate(cfg, d)
    return res, cfg, d


def _print_result(res, out=print):
    secrets = redact.collect_secrets(res.config) if res.config else set()
    red = redact.Redactor(secrets)
    for e in res.errors:
        out("error:   " + red(e))
    for w in res.warnings:
        out("warning: " + red(w))
    return red


def cmd_doctor(args, root):
    checks = doctor.run_all(root)
    print(doctor.format_checks(checks))
    return doctor.exit_code(checks)


def cmd_configure(args, root):
    if args.from_file:
        try:
            cfg = tomlmini.load_file(args.from_file)
        except (OSError, tomlmini.TomlError) as exc:
            print("error: %s" % exc)
            return 2
        base = os.path.dirname(os.path.abspath(args.from_file))
        cfg = cfgmod.absolutize_file_refs(cfg, base)
    else:
        pr = configure.Prompter()
        cfg = configure.run_wizard(pr, defaults_name=args.name)
        base = root
    res = validate.validate(cfg, base)
    red = _print_result(res)
    if not res.ok:
        print("\nNothing was written. Fix the problems above and try again.")
        return 1
    # Write the *resolved* file contents the user supplied, not secrets from files/env:
    # keep references (authorized_keys_file etc.) as given.
    try:
        d = configure.write_board(root, cfg, force=args.force)
    except cfgmod.ConfigError as exc:
        print("error: %s" % exc)
        return 1
    print("\nWrote %s\n  board.toml   shareable settings\n  secrets.toml private (git-ignored)\nNext: python percept validate --board %s"
          % (d, cfg["board"]["name"]))
    return 0


def cmd_validate(args, root):
    res, _cfg, d = _load_validated(root, args.board)
    if res is None:
        return 2
    _print_result(res)
    print("%s: %d error(s), %d warning(s)" % (d, len(res.errors), len(res.warnings)))
    return 0 if res.ok else 1


def cmd_show(args, root):
    res, _cfg, d = _load_validated(root, args.board)
    if res is None or not res.ok:
        if res is not None:
            _print_result(res)
        return 1
    red = redact.Redactor(redact.collect_secrets(res.config))
    shown = dict(res.config)
    text = red(tomlmini.dumps(shown))
    print(text)
    return 0


def cmd_launcher_conf(args, root):
    res, _cfg, d = _load_validated(root, args.board)
    if res is None or not res.ok:
        if res is not None:
            _print_result(res)
        return 1
    prof_dir = os.path.join(profiles.profiles_root(root), res.config["os"]["profile"])
    try:
        prof = profiles.load_profile(prof_dir)
    except profiles.ProfileError as exc:
        print("error: %s" % exc)
        return 2
    r = profiles.resolve(res.config, prof)
    for p in r["problems"]:
        print("error: " + p)
    for w in r["warnings"]:
        print("warning: " + w)
    if r["problems"]:
        return 1
    print("# root UUID is a placeholder here; the real one is generated at build time", file=sys.stderr)
    print(launcher_conf.render(r, res.config, compat=args.compat), end="")
    return 0


def cmd_profile(args, root):
    if args.action == "list":
        for name in profiles.list_profiles(root):
            p = profiles.load_profile(os.path.join(profiles.profiles_root(root), name))
            print("%-16s %-13s %s" % (name, p.get("status", "?"), p.get("title", "")))
        return 0
    path = args.path
    try:
        p = profiles.load_profile(path)
    except profiles.ProfileError as exc:
        print("error: %s" % exc)
        return 2
    base = os.path.basename(os.path.abspath(path))
    problems = profiles.check_profile(p, None if base.startswith("_") else base)
    for pr in problems:
        print("problem: " + pr)
    print("%s: %s" % (path, "OK" if not problems else "%d problem(s)" % len(problems)))
    return 1 if problems else 0


def cmd_hash_password(args, root):
    p1 = getpass.getpass("Password: ")
    if len(p1) < 8:
        print("error: use at least 8 characters")
        return 1
    if getpass.getpass("Repeat: ") != p1:
        print("error: passwords differ")
        return 1
    print(sha512crypt.crypt(p1))
    return 0


def cmd_config_doc(args, root):
    text = configdoc.render()
    if args.write:
        with open(os.path.join(root, "docs", "configuration.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote docs/configuration.md")
    else:
        print(text, end="")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="percept", description="Debian installer for the Azure Percept DK")
    ap.add_argument("--version", action="version", version="percept " + __version__)
    sub = ap.add_subparsers(dest="cmd", metavar="command")

    sub.add_parser("doctor", help="check this PC (and WSL2) and print fixes")
    c = sub.add_parser("configure", help="ask for your settings and write boards/<name>/")
    c.add_argument("--name", help="suggested board name")
    c.add_argument("--from", dest="from_file", metavar="FILE", help="read settings from a TOML file instead of asking")
    c.add_argument("--force", action="store_true", help="overwrite an existing board")
    v = sub.add_parser("validate", help="check a board's settings")
    v.add_argument("--board", required=True, help="board name or directory")
    s = sub.add_parser("show", help="print the fully defaulted settings with secrets hidden")
    s.add_argument("--board", required=True)
    lc = sub.add_parser("launcher-conf", help="print the launcher.conf this board would get")
    lc.add_argument("--board", required=True)
    lc.add_argument("--compat", choices=["current", "v2"], default="current")
    pf = sub.add_parser("profile", help="list or check OS profiles")
    pf.add_argument("action", choices=["list", "check"])
    pf.add_argument("path", nargs="?", help="profile directory (check)")
    sub.add_parser("hash-password", help="make a $6$ password hash for board.toml")
    cd = sub.add_parser("config-doc", help="render docs/configuration.md from the schema")
    cd.add_argument("--write", action="store_true")
    for command in ("fetch", "build"):
        p = sub.add_parser(command, help="fetch verified vendor inputs" if command == "fetch" else "build a personalized USB image in WSL/Linux")
        p.add_argument("--distro", help="WSL distro (Windows only)")
        p.add_argument("--wsl-repo", help="WSL source checkout (Windows only)")
        if command == "fetch": p.add_argument("--recovery", help="existing hash-verified Microsoft recovery ZIP")
        else:
            p.add_argument("--board", required=True)
            p.add_argument("--target", choices=["image"], default="image")
            p.add_argument("--resolved-stdin", action="store_true", help=argparse.SUPPRESS)
    for name, text in PLANNED.items():
        sub.add_parser(name, help="(planned) " + text)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 0
    if args.cmd in PLANNED:
        print("'%s' is not implemented yet (%s). See the roadmap in README.md." % (args.cmd, PLANNED[args.cmd]))
        return 2
    if args.cmd == "profile" and args.action == "check" and not args.path:
        ap.error("profile check needs a directory")
    if args.cmd in ("fetch", "build"):
        from .build.commands import dispatch
        try:
            return dispatch(args, repo_root())
        except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
            print("error: " + str(exc))
            return 1
    handler = {
        "doctor": cmd_doctor, "configure": cmd_configure, "validate": cmd_validate, "show": cmd_show,
        "launcher-conf": cmd_launcher_conf, "profile": cmd_profile, "hash-password": cmd_hash_password,
        "config-doc": cmd_config_doc,
    }[args.cmd]
    try:
        return handler(args, repo_root())
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
