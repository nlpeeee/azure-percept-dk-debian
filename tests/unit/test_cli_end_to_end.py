# SPDX-License-Identifier: MIT
"""Wizard, board files, CLI and the 'secrets never leak' canary test."""
import contextlib
import io
import os
import stat
import tempfile
import unittest

import helpers
from percept import cli, config, configdoc, configure, tomlmini, validate

CANARY_PSK = "canary-wifi-passphrase-7731"
CANARY_PW = "canary-user-password-4482"


def run_cli(root, *argv):
    out = io.StringIO()
    old = os.environ.get("PERCEPT_ROOT")
    os.environ["PERCEPT_ROOT"] = root
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = cli.main(list(argv))
    finally:
        if old is None:
            del os.environ["PERCEPT_ROOT"]
        else:
            os.environ["PERCEPT_ROOT"] = old
    return rc, out.getvalue()


class Scripted:
    def __init__(self, answers):
        self.answers = list(answers)
        self.log = []

    def __call__(self, prompt):
        self.log.append(prompt)
        return self.answers.pop(0)


def wizard_answers(key_choice="p"):
    return [
        "bench",          # board name
        "",               # hostname (default)
        "Europe/London",  # tz
        "percept",        # user
        key_choice, helpers.ed25519_key(9, "wiz@test"),  # key menu, pasted key
        "type",           # password mode
        CANARY_PW, CANARY_PW,
        "n",              # password ssh
        "static", "192.168.50.20", "24", "192.168.50.1", "",   # ethernet (dns default = gateway)
        "y", "HomeNet", "wpa2", CANARY_PSK, "gb", "n",          # wifi
        "static", "192.168.50.21", "24", "",                    # rescue
        "uuu",
    ]


class Wizard(unittest.TestCase):
    def test_full_run_writes_split_files_with_no_plaintext(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as root:
            ans = Scripted(wizard_answers())
            pr = configure.Prompter(ans, ans, lambda *_: None)
            cfg = configure.run_wizard(pr, home=home)
            self.assertEqual(ans.answers, [], "wizard did not consume all answers")
            res = validate.validate(cfg)
            self.assertEqual(res.errors, [])
            d = configure.write_board(root, cfg)
            board = open(os.path.join(d, "board.toml"), encoding="utf-8").read()
            secrets = open(os.path.join(d, "secrets.toml"), encoding="utf-8").read()
            for text in (board, secrets):
                self.assertNotIn(CANARY_PW, text)  # never stored in plaintext anywhere
            self.assertNotIn(CANARY_PSK, board)
            self.assertIn(CANARY_PSK, secrets)
            self.assertNotIn("password_hash", board)
            self.assertIn("password_hash", secrets)
            self.assertIn('country = "GB"', board)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, "secrets.toml")).st_mode), 0o600)
            # reload round-trip is valid and identical
            again = validate.validate(config.load_board(d), d)
            self.assertEqual(again.errors, [])
            self.assertEqual(again.config["network"]["wifi"]["psk"], CANARY_PSK)

    def test_invalid_answer_is_reasked(self):
        ans = Scripted(["Bad Name", "ok-name"])
        pr = configure.Prompter(ans, ans, lambda *_: None)
        v = pr.ask("name", None, lambda x: None if validate.NAME_RE.match(x) else "bad")
        self.assertEqual(v, "ok-name")

    def test_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = helpers.minimal_cfg()
            configure.write_board(root, cfg)
            with self.assertRaises(config.ConfigError):
                configure.write_board(root, cfg)
            configure.write_board(root, cfg, force=True)


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        # profiles are read from the root, so link the real ones in
        import shutil
        shutil.copytree(os.path.join(helpers.ROOT, "profiles"), os.path.join(self.root, "profiles"))
        os.makedirs(os.path.join(self.root, "docs"))
        src = os.path.join(self.root, "in.toml")
        with open(src, "w", encoding="utf-8") as f:
            f.write(tomlmini.dumps({
                "schema": 1, "board": {"name": "cli1"},
                "user": [{"name": "percept", "authorized_keys": [helpers.ed25519_key(4)]}],
                "network": {"wifi": {"enabled": True, "ssid": "Home", "psk": CANARY_PSK, "country": "DE"}}}))
        self.src = src

    def tearDown(self):
        self.tmp.cleanup()

    def test_configure_validate_show_launcher_conf(self):
        rc, out = run_cli(self.root, "configure", "--from", self.src)
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "boards", "cli1", "secrets.toml")))
        rc, out = run_cli(self.root, "configure", "--from", self.src)
        self.assertEqual(rc, 1)  # exists
        self.assertIn("already exists", out)

        rc, out = run_cli(self.root, "validate", "--board", "cli1")
        self.assertEqual(rc, 0, out)
        self.assertNotIn(CANARY_PSK, out)

        rc, out = run_cli(self.root, "show", "--board", "cli1")
        self.assertEqual(rc, 0, out)
        self.assertNotIn(CANARY_PSK, out)
        self.assertIn('ssid = "Home"', out)

        rc, out = run_cli(self.root, "launcher-conf", "--board", "cli1")
        self.assertEqual(rc, 0, out)
        self.assertIn("mode=kexec", out)
        self.assertNotIn(CANARY_PSK, out)
        self.assertNotIn("authorized_keys", out)

    def test_bad_config_reports_and_writes_nothing(self):
        with open(self.src, "w", encoding="utf-8") as f:
            f.write('schema = 1\n[board]\nname = "bad"\n[[user]]\nname = "u"\n')
        rc, out = run_cli(self.root, "configure", "--from", self.src)
        self.assertEqual(rc, 1)
        self.assertIn("no way to log in", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "boards")))

    def test_validate_errors_never_echo_secrets(self):
        d = os.path.join(self.root, "boards", "leaky")
        os.makedirs(d)
        with open(os.path.join(d, "board.toml"), "w", encoding="utf-8") as f:
            f.write('schema = 1\n[board]\nname = "leaky"\n[[user]]\nname = "u"\nauthorized_keys = []\n'
                    '[network.wifi]\nenabled = true\nssid = "Home"\ncountry = "ZZ"\npsk = "%s"\n' % CANARY_PSK)
        rc, out = run_cli(self.root, "validate", "--board", "leaky")
        self.assertEqual(rc, 1)
        self.assertNotIn(CANARY_PSK, out)

    def test_profile_commands(self):
        rc, out = run_cli(self.root, "profile", "list")
        self.assertEqual(rc, 0)
        self.assertIn("debian-trixie", out)
        rc, out = run_cli(self.root, "profile", "check", os.path.join(self.root, "profiles", "debian-trixie"))
        self.assertEqual(rc, 0, out)

    def test_planned_commands_say_so(self):
        rc, out = run_cli(self.root, "build")
        self.assertEqual(rc, 2)
        self.assertIn("not implemented yet", out)


class Docs(unittest.TestCase):
    def test_configuration_md_is_current(self):
        with open(os.path.join(helpers.ROOT, "docs", "configuration.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), configdoc.render(),
                             "run: python percept config-doc --write")

    def test_examples_validate(self):
        env = {"PERCEPT_WIFI_PSK": "example-passphrase-1"}
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, ".ssh"))
            with open(os.path.join(home, ".ssh", "id_ed25519.pub"), "w") as f:
                f.write(helpers.ed25519_key(7) + "\n")
            old = os.environ.get("HOME"), os.environ.get("USERPROFILE")
            os.environ["HOME"] = os.environ["USERPROFILE"] = home
            try:
                for name in ("board.minimal.toml", "board.full.toml"):
                    cfg = tomlmini.load_file(os.path.join(helpers.ROOT, "examples", name))
                    res = validate.validate(cfg, helpers.ROOT, env=env)
                    self.assertEqual(res.errors, [], name)
            finally:
                for k, v in zip(("HOME", "USERPROFILE"), old):
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
