# SPDX-License-Identifier: MIT
"""Guided, local-only preparation; build and flash remain explicit commands."""
from pathlib import Path
from types import SimpleNamespace
from . import configure, validate


def summary(cfg, out=print):
    out("\nSettings summary (passwords and key material hidden):")
    out("  Board folder: %s; hostname: %s; timezone: %s" % (
        cfg['board']['name'], cfg['board']['hostname'], cfg['board']['timezone']))
    for user in cfg['user']:
        out("  User %s: password %s; %d public key(s)" % (
            user['name'], user['password_mode'], len(user['authorized_keys'])))
    out("  Debian SSH password login: %s" % cfg['ssh']['password_auth'])
    eth = cfg['network']['ethernet']
    out("  Ethernet: %s %s" % (eth['mode'], eth.get('address', '')))
    out("  Wi-Fi: %s" % ('enabled' if cfg['network']['wifi']['enabled'] else 'disabled'))
    rescue = cfg['rescue']
    out("  Recovery: user %s; %s %s; password login %s; %d public key(s)" % (
        rescue['username'], rescue['net_mode'], rescue.get('address', ''),
        rescue['password_auth'], len(rescue['authorized_keys'])))
    out("  CPU: %s; OS: %s; install: %s" % (
        cfg['os']['cpu_profile'], cfg['os']['profile'], cfg['install']['method']))


def run(args, root, pr=None):
    from . import cli
    pr = pr or configure.Prompter()
    saved = sorted(p.parent.name for p in (Path(root)/'boards').glob('*/board.toml'))
    if saved:
        pr.out("Saved boards: " + ", ".join(saved))
    name = args.board or pr.ask("Board to reuse or create", saved[0] if len(saved) == 1 else "percept-1")
    if not validate.NAME_RE.fullmatch(name):
        pr.out("Invalid board name: use lowercase letters, digits, - and _ only.")
        return 1
    if name not in saved:
        status = cli.cmd_configure(SimpleNamespace(name=name, from_file=None, force=False), root)
        if status:
            return status
    while True:
        result, _, directory = cli._load_validated(root, name, pr.out)
        if result is None:
            return 1
        cli._print_result(result, pr.out)
        if result.ok:
            summary(result.config, pr.out)
        pr.out("Edit settings in %s; passwords/hashes belong in secrets.toml." % directory)
        action = pr.choose("Review", ["continue", "edit", "quit"], "continue" if result.ok else "edit")
        if action == "quit":
            return 0
        if action == "edit":
            pr.ask("Save your edits in your editor, then press Enter to reload", "")
            continue
        if not result.ok:
            pr.out("Correct the validation errors before continuing.")
            continue
        if result.config['board']['name'] != name:
            pr.out("board.name must match the saved folder name: " + name)
            return 1
        if result.config['install']['method'] != 'uuu':
            pr.out("SSH conversion is not implemented. Select install.method = \"uuu\" for the USB installer.")
            return 1
        pr.out("\nNext, from the Windows repository:")
        pr.out("  python percept doctor")
        pr.out("  python percept fetch")
        pr.out("  python percept build --board " + name)
        pr.out("Use the exact manifest path printed by that successful build for flash.")
        pr.out("See docs/install.md for WSL sync, USB switches and first-login checks.")
        return 0
