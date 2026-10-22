# SPDX-License-Identifier: MIT
"""The interactive `percept configure` wizard and board-directory writer."""
import getpass
import glob
import os
import shutil
import subprocess

from . import config as cfgmod
from . import sha512crypt, sshkeys, tomlmini, validate

HEADER_BOARD = (
    "# Percept DK board settings (safe to share; secrets live in secrets.toml).\n"
    "# Edit freely, then run:  python percept validate --board {name}\n\n"
)
HEADER_SECRETS = (
    "# SECRETS for board {name}. Never commit, post or share this file.\n"
    "# It is git-ignored; permissions are restricted to your account.\n\n"
)


class Prompter:
    """Thin wrapper over input()/getpass so the wizard is testable."""

    def __init__(self, input_fn=input, secret_fn=getpass.getpass, out=print):
        self.input, self.secret, self.out = input_fn, secret_fn, out

    def ask(self, question, default=None, check=None, secret=False):
        while True:
            suffix = " [%s]" % default if default not in (None, "") and not secret else ""
            raw = (self.secret if secret else self.input)("%s%s: " % (question, suffix))
            value = raw.strip() if raw is not None else ""
            if value == "" and default is not None:
                value = default
            if check is None:
                return value
            problem = check(value)
            if not problem:
                return value
            self.out("  ! " + problem)

    def choose(self, question, options, default):
        opts = "/".join(o.upper() if o == default else o for o in options)
        return self.ask("%s (%s)" % (question, opts), default,
                        lambda v: None if v in options else "please enter one of: " + ", ".join(options))

    def yes(self, question, default=False):
        return self.choose(question, ["y", "n"], "y" if default else "n") == "y"


def find_public_keys(home=None):
    """(path, key_line) for each usable ~/.ssh/*.pub."""
    home = home or os.path.expanduser("~")
    found = []
    for p in sorted(glob.glob(os.path.join(home, ".ssh", "*.pub"))):
        try:
            with open(p, encoding="utf-8") as f:
                line = f.read().strip().splitlines()[0]
            sshkeys.check_key(line)
            found.append((p, line))
        except (OSError, IndexError, sshkeys.PublicKeyError):
            continue
    return found


def _key_check(value):
    try:
        sshkeys.check_key(value)
    except sshkeys.PublicKeyError as exc:
        return str(exc)
    return None


def pick_ssh_key(pr, name, home=None, keygen=shutil.which("ssh-keygen"), allow_skip=False):
    keygen = keygen or getattr(pr, 'generate_key', None)
    pr.out("Keys are optional when password login is enabled. Only public keys go on the board.")
    pr.out("An encrypted PC private key needs its passphrase for interactive SSH; unattended checks need it loaded with ssh-add first.")
    keys = find_public_keys(home)
    if keys:
        pr.out("SSH public keys found on this PC:")
        for i, (p, line) in enumerate(keys, 1):
            pr.out("  %d) %s  (%s)" % (i, p, line.split()[0]))
        pr.out("  p) paste a key    g) generate a new one" + ("    s) skip (password only)" if allow_skip else ""))
        choice = pr.ask("Which key should be allowed to log in", "1" if keys else "p")
    else:
        pr.out("No SSH public key found in ~/.ssh.")
        choice = pr.ask("Paste a public key (p), generate one (g)" + (", or skip for password login (s)" if allow_skip else ""), "s" if allow_skip else "g" if keygen else "p")
    if choice == "s" and allow_skip:
        return None
    if choice.isdigit() and 1 <= int(choice) <= len(keys):
        return keys[int(choice) - 1][1]
    if choice == "g":
        if not keygen:
            pr.out("  ssh-keygen not found; paste a key instead.")
        else:
            path = os.path.join(home or os.path.expanduser("~"), ".ssh", "percept_%s_ed25519" % name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            pr.out("Generating %s (you will be asked for a passphrase; a passphrase is recommended)." % path)
            if getattr(pr, 'generate_key', None):
                pr.generate_key(path)
            else:
                subprocess.run([keygen, "-t", "ed25519", "-f", path, "-C", "percept-" + name], check=False)
            try:
                with open(path + ".pub", encoding="utf-8") as f:
                    return f.read().strip()
            except OSError:
                pr.out("  key generation did not complete; paste a key instead.")
    return pr.ask("Paste the public key (one line, starts with ssh-ed25519 ...)", None, _key_check)


def run_wizard(pr, home=None, defaults_name=None):
    """Ask the questions; return a (not yet validated) config dict."""
    pr.out("Percept DK setup. Press Enter to accept the value in [brackets].\n")
    if defaults_name is not None:
        if not validate.NAME_RE.fullmatch(defaults_name):
            raise cfgmod.ConfigError("board name: lowercase letters, digits, - and _ only")
        name = defaults_name
        pr.out("Board folder: boards/%s (selected by --name)" % name)
    else:
        name = pr.ask("Name for this board (used for the folder boards/<name>)", "percept-1",
                      lambda v: None if validate.NAME_RE.fullmatch(v) else "lowercase letters, digits, - and _ only")
    cfg = {"schema": 1, "board": {"name": name}}
    cfg["board"]["hostname"] = pr.ask("Hostname", name,
                                      lambda v: None if validate.HOST_RE.match(v) else "not a valid hostname")
    cfg["board"]["timezone"] = pr.ask("Time zone (e.g. Europe/London)", "UTC",
                                      lambda v: None if validate.TZ_RE.match(v) else "expected something like Europe/London or UTC")

    # --- user ------------------------------------------------------------
    user = pr.ask("Login user name", "percept",
                  lambda v: None if validate.USER_RE.match(v) and v not in validate.RESERVED_USERS else "invalid or reserved name")
    mode = pr.choose("Password for %s: none = SSH key only, generate = random password saved for you, type = enter one" % user,
                     ["none", "generate", "type"], "type")
    key = pick_ssh_key(pr, name, home, allow_skip=(mode != "none"))
    u = {"name": user, "authorized_keys": [key] if key else []}
    if mode == "generate":
        u["password_mode"] = "generate"
    elif mode == "type":
        while True:
            p1 = pr.ask("Password", None, lambda v: None if len(v) >= 8 else "use at least 8 characters", secret=True)
            if p1 == pr.ask("Repeat password", None, secret=True):
                break
            pr.out("  ! passwords differ")
        u["password_hash"] = sha512crypt.crypt(p1)
        u["password_mode"] = "hash"
    cfg["user"] = [u]
    rescue_pw = False
    if mode != "none":
        cfg["ssh"] = {"password_auth": pr.yes("Allow SSH password logins on the installed system", True)}
        rescue_pw = pr.yes("Allow the same password for SSH login (as root) in rescue mode", True)

    # --- ethernet --------------------------------------------------------
    eth = {"mode": pr.choose("Ethernet addressing", ["dhcp", "static"], "dhcp")}
    if eth["mode"] == "static":
        eth["address"] = pr.ask("  IPv4 address", None, lambda v: None if _is_ip(v) else "not an IPv4 address")
        eth["prefix"] = int(pr.ask("  Prefix length (24 = 255.255.255.0)", "24",
                                   lambda v: None if v.isdigit() and 1 <= int(v) <= 30 else "1-30"))
        eth["gateway"] = pr.ask("  Gateway", None, lambda v: None if _is_ip(v) else "not an IPv4 address")
        dns = pr.ask("  DNS servers (space separated)", eth["gateway"],
                     lambda v: None if v and all(_is_ip(x) for x in v.split()) else "not IPv4 addresses")
        eth["dns"] = dns.split()
    cfg["network"] = {"ethernet": eth}

    # --- wifi ------------------------------------------------------------
    if pr.yes("Configure Wi-Fi", False):
        w = {"enabled": True}
        w["ssid"] = pr.ask("  Network name (SSID)", None,
                           lambda v: None if 1 <= len(v.encode("utf-8")) <= 32 else "1-32 bytes")
        w["security"] = pr.choose("  Security", ["wpa2", "wpa3", "open"], "wpa2")
        if w["security"] != "open":
            w["psk"] = pr.ask("  Passphrase (hidden)", None,
                              lambda v: None if (8 <= len(v) <= 63) or len(v) == 64 else "8-63 characters (or 64 hex digits)",
                              secret=True)
        w["country"] = pr.ask("  Country code for Wi-Fi regulations (e.g. GB, US, DE)", None,
                              lambda v: None if v.upper() in validate.countries() else "use a 2-letter ISO country code").upper()
        w["hidden"] = pr.yes("  Is the network hidden", False)
        cfg["network"]["wifi"] = w

    # --- rescue ----------------------------------------------------------
    r = {"net_mode": pr.choose("Rescue-mode addressing (used if the board fails to boot; static is easiest to find)",
                               ["dhcp", "static"], "dhcp")}
    if r["net_mode"] == "static":
        r["address"] = pr.ask("  Rescue IPv4 address", None, lambda v: None if _is_ip(v) else "not an IPv4 address")
        r["prefix"] = int(pr.ask("  Prefix length", str(eth.get("prefix", 24)),
                                 lambda v: None if v.isdigit() and 1 <= int(v) <= 30 else "1-30"))
        gw = pr.ask("  Gateway (optional)", eth.get("gateway", "") or "", lambda v: None if not v or _is_ip(v) else "not an IPv4 address")
        if gw:
            r["gateway"] = gw
    if rescue_pw:
        r["password_auth"] = True
    r["username"] = pr.ask("Recovery SSH user name (administrator)", "root",
        lambda v: None if validate.USER_RE.fullmatch(v) and (v == "root" or v not in validate.RESERVED_USERS) else "invalid or reserved user name")
    if pr.yes("Use a separate recovery password", False):
        while True:
            value = pr.ask("Recovery password", None, lambda v: None if len(v)>=8 else "use at least 8 characters", secret=True)
            if value == pr.ask("Repeat recovery password", None, secret=True): break
            pr.out("  ! passwords differ")
        r["password_auth"] = True
        r["password_hash"] = sha512crypt.crypt(value)
    cfg["rescue"] = r
    cfg["os"] = {"cpu_profile": pr.choose("CPU profile: unchanged, rated 800/1300 MHz, experimental oc1500", ["unchanged", "rated", "oc1500"], "unchanged")}

    # --- install ---------------------------------------------------------
    method = pr.choose("How will you install: uuu = flash over USB, ssh = conversion (not implemented yet)",
                       ["uuu", "ssh"], "uuu")
    cfg["install"] = {"method": method}
    if method == "ssh":
        cfg["install"]["ssh_host"] = pr.ask("  Current address of the board", None, lambda v: None if v else "required")
    return cfg


def _is_ip(v):
    import ipaddress
    try:
        ipaddress.IPv4Address(v)
        return True
    except ValueError:
        return False


def write_board(root, cfg, force=False):
    """Write boards/<name>/{board.toml,secrets.toml}. Returns the directory."""
    name = cfg["board"]["name"]
    d = cfgmod.board_path(root, name)
    if os.path.exists(os.path.join(d, cfgmod.BOARD_FILE)) and not force:
        raise cfgmod.ConfigError("boards/%s already exists (use --force to overwrite)" % name)
    pub, sec = cfgmod.split_secrets(cfg)
    cfgmod.write_private(os.path.join(d, cfgmod.BOARD_FILE), HEADER_BOARD.format(name=name) + tomlmini.dumps(pub))
    sp = os.path.join(d, cfgmod.SECRETS_FILE)
    if sec:
        cfgmod.write_private(sp, HEADER_SECRETS.format(name=name) + tomlmini.dumps(sec))
    elif os.path.exists(sp):
        os.remove(sp)
    return d


def import_board(root, directory):
    """Copy saved settings without modifying the source or replacing a saved board."""
    directory=os.path.abspath(directory)
    cfg=cfgmod.absolutize_file_refs(cfgmod.load_board(directory),directory)
    result=validate.validate(cfg,directory)
    if not result.ok:
        from .redact import Redactor, collect_secrets
        red=Redactor(collect_secrets(cfg))
        raise cfgmod.ConfigError('Imported settings are invalid: '+red('; '.join(result.errors)))
    write_board(root,cfg,force=False)
    return cfg['board']['name']
