# SPDX-License-Identifier: MIT
import copy
import os
import tempfile
import unittest

import helpers
from percept import sha512crypt, validate


def check(cfg, **kw):
    return validate.validate(copy.deepcopy(cfg), **kw)


def errs(res, needle):
    return [e for e in res.errors if needle in e]


class Basics(unittest.TestCase):
    def test_minimal_is_valid_and_defaulted(self):
        r = check(helpers.minimal_cfg())
        self.assertEqual(r.errors, [])
        c = r.config
        self.assertEqual(c["board"]["hostname"], "t1")
        self.assertEqual(c["network"]["ethernet"]["mode"], "dhcp")
        self.assertEqual(c["user"][0]["sudo"], "nopasswd")
        self.assertEqual(c["rescue"]["authorized_keys"], c["user"][0]["authorized_keys"])
        self.assertFalse(c["ssh"]["password_auth"])
        self.assertEqual(c["ssh"]["root_login"], "disabled")

    def test_unknown_keys_are_errors(self):
        cfg = helpers.minimal_cfg()
        cfg["network"] = {"wifi": {"enabld": True}}
        cfg["bogus"] = 1
        r = check(cfg)
        self.assertTrue(errs(r, "network.wifi.enabld"))
        self.assertTrue(errs(r, "bogus"))

    def test_type_errors(self):
        cfg = helpers.minimal_cfg()
        cfg["ssh"] = {"port": "22"}
        cfg["board"]["timezone"] = 5
        r = check(cfg)
        self.assertTrue(errs(r, "ssh.port"))
        self.assertTrue(errs(r, "board.timezone"))

    def test_names(self):
        for bad in ("Has Space", "UPPER", "-lead", "", "x" * 40):
            cfg = helpers.minimal_cfg()
            cfg["board"]["name"] = bad
            self.assertTrue(errs(check(cfg), "board.name"), bad)
        cfg = helpers.minimal_cfg()
        cfg["board"]["hostname"] = "bad_host"
        self.assertTrue(errs(check(cfg), "hostname"))


class Users(unittest.TestCase):
    def test_no_users_or_no_login_path(self):
        cfg = helpers.minimal_cfg()
        del cfg["user"]
        self.assertTrue(errs(check(cfg), "user"))
        cfg = helpers.minimal_cfg()
        cfg["user"][0]["authorized_keys"] = []
        r = check(cfg)
        self.assertTrue(errs(r, "no way to log in"))

    def test_private_key_rejected(self):
        cfg = helpers.minimal_cfg()
        cfg["user"][0]["authorized_keys"] = ["-----BEGIN OPENSSH PRIVATE KEY-----"]  # scrub-ok: deliberate fixture
        self.assertTrue(errs(check(cfg), "PRIVATE"))

    def test_plaintext_password_rejected(self):
        cfg = helpers.minimal_cfg()
        cfg["user"][0]["password_hash"] = "hunter2hunter2"
        self.assertTrue(errs(check(cfg), "SHA-512"))

    def test_hash_sets_mode_and_sudo(self):
        cfg = helpers.minimal_cfg()
        cfg["user"][0]["password_hash"] = sha512crypt.crypt("correct horse")
        r = check(cfg)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.config["user"][0]["password_mode"], "hash")
        self.assertEqual(r.config["user"][0]["sudo"], "password")

    def test_generate_conflicts_with_hash(self):
        cfg = helpers.minimal_cfg()
        cfg["user"][0].update(password_hash=sha512crypt.crypt("correct horse"), password_mode="generate")
        self.assertTrue(errs(check(cfg), "conflicts"))

    def test_password_auth_needs_password(self):
        cfg = helpers.minimal_cfg()
        cfg["ssh"] = {"password_auth": True}
        self.assertTrue(errs(check(cfg), "no user has a password"))

    def test_reserved_and_duplicate(self):
        cfg = helpers.minimal_cfg()
        cfg["user"].append({"name": "root", "authorized_keys": [helpers.ed25519_key(2)]})
        cfg["user"].append({"name": "percept", "authorized_keys": [helpers.ed25519_key(3)]})
        r = check(cfg)
        self.assertTrue(errs(r, "reserved"))
        self.assertTrue(errs(r, "duplicate"))

    def test_keys_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "k.pub")
            with open(p, "w") as f:
                f.write("# my key\n%s\n\n%s\n" % (helpers.ed25519_key(5), helpers.ed25519_key(5)))
            cfg = helpers.minimal_cfg()
            cfg["user"][0] = {"name": "percept", "authorized_keys_file": p}
            r = check(cfg)
            self.assertEqual(r.errors, [])
            self.assertEqual(len(r.config["user"][0]["authorized_keys"]), 1)  # de-duplicated
            cfg["user"][0]["authorized_keys_file"] = os.path.join(d, "missing.pub")
            self.assertTrue(errs(check(cfg), "cannot read"))


class Network(unittest.TestCase):
    def static(self, **o):
        cfg = helpers.minimal_cfg()
        eth = {"mode": "static", "address": "192.168.50.20", "prefix": 24, "gateway": "192.168.50.1", "dns": ["1.1.1.1"]}
        eth.update(o)
        cfg["network"] = {"ethernet": eth}
        return cfg

    def test_static_ok(self):
        self.assertEqual(check(self.static()).errors, [])

    def test_static_problems(self):
        self.assertTrue(errs(check(self.static(gateway="10.0.0.1")), "outside"))
        self.assertTrue(errs(check(self.static(gateway="192.168.50.20")), "differ"))
        self.assertTrue(errs(check(self.static(address="192.168.50.255")), "broadcast"))
        self.assertTrue(errs(check(self.static(address="nope")), "not an IPv4"))
        self.assertTrue(errs(check(self.static(prefix=31)), "prefix"))
        self.assertTrue(errs(check(self.static(dns=["x"])), "dns"))
        cfg = self.static()
        del cfg["network"]["ethernet"]["gateway"]
        self.assertTrue(errs(check(cfg), "gateway"))

    def wifi(self, **o):
        cfg = helpers.minimal_cfg()
        w = {"enabled": True, "ssid": "Home", "psk": "passphrase1", "country": "GB"}
        w.update(o)
        w = {k: v for k, v in w.items() if v is not None}
        cfg["network"] = {"wifi": w}
        return cfg

    def test_wifi(self):
        self.assertEqual(check(self.wifi()).errors, [])
        self.assertEqual(check(self.wifi(psk="a" * 64)).errors, [])
        self.assertTrue(errs(check(self.wifi(psk="short")), "psk"))
        self.assertTrue(errs(check(self.wifi(country="XX")), "country"))
        self.assertTrue(errs(check(self.wifi(country=None)), "country"))
        self.assertTrue(errs(check(self.wifi(ssid="x" * 33)), "ssid"))
        self.assertEqual(check(self.wifi(security="open", psk=None)).errors, [])
        self.assertTrue(errs(check(self.wifi(psk="café-passphrase")), "ASCII"))

    def test_wifi_disabled_warns(self):
        r = check(self.wifi(enabled=False))
        self.assertEqual(r.errors, [])
        self.assertTrue(any("ignored" in w for w in r.warnings))

    def test_secret_from_env_and_file(self):
        cfg = helpers.minimal_cfg()
        cfg["network"] = {"wifi": {"enabled": True, "ssid": "Home", "psk_env": "T_PSK", "country": "GB"}}
        r = validate.validate(copy.deepcopy(cfg), env={"T_PSK": "from-environment"})
        self.assertEqual(r.errors, [])
        self.assertEqual(r.config["network"]["wifi"]["psk"], "from-environment")
        r = validate.validate(copy.deepcopy(cfg), env={})
        self.assertTrue(errs(r, "T_PSK"))
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "psk.txt"), "w") as f:
                f.write("from-a-file\n")
            cfg["network"]["wifi"] = {"enabled": True, "ssid": "Home", "psk_file": "psk.txt", "country": "GB"}
            r = validate.validate(cfg, base_dir=d)
            self.assertEqual(r.config["network"]["wifi"]["psk"], "from-a-file")


class RescueAndOs(unittest.TestCase):
    def test_rescue_needs_keys(self):
        cfg = helpers.minimal_cfg()
        cfg["user"][0].update(authorized_keys=[], password_mode="generate")
        cfg["ssh"] = {"password_auth": True}
        self.assertTrue(errs(check(cfg), "rescue.authorized_keys"))
        cfg["rescue"] = {"enabled": False}
        r = check(cfg)
        self.assertEqual(r.errors, [])
        self.assertTrue(r.warnings)

    def test_rescue_static_and_limits(self):
        cfg = helpers.minimal_cfg()
        cfg["rescue"] = {"net_mode": "static", "address": "10.1.1.5", "prefix": 24, "fail_limit": 11, "grub_tries": 5}
        r = check(cfg)
        self.assertTrue(errs(r, "fail_limit"))
        self.assertTrue(errs(r, "grub_tries"))
        cfg["rescue"] = {"net_mode": "static", "address": "10.1.1.5", "prefix": 24}
        self.assertEqual(check(cfg).errors, [])

    def test_log_receiver_pair(self):
        cfg = helpers.minimal_cfg()
        cfg["rescue"] = {"log_receiver_ip": "10.0.0.2"}
        self.assertTrue(errs(check(cfg), "log_receiver_port"))

    def test_cmdline_extra(self):
        for bad in ("quiet; reboot", "root=/dev/sda1", "init=/bin/sh", "a" * 1100, "x=$(y)"):
            cfg = helpers.minimal_cfg()
            cfg["os"] = {"kernel": {"cmdline_extra": bad}}
            self.assertTrue(errs(check(cfg), "cmdline_extra"), bad)
        cfg["os"] = {"kernel": {"cmdline_extra": "loglevel=3 quiet"}}
        self.assertEqual(check(cfg).errors, [])

    def test_vpu_needs_gpu(self):
        cfg = helpers.minimal_cfg()
        cfg["os"] = {"features": {"gpu": False, "vpu": True}}
        self.assertTrue(errs(check(cfg), "os.features.vpu"))

    def test_files_kernel_requirements(self):
        cfg = helpers.minimal_cfg()
        cfg["os"] = {"kernel": {"source": "files"}}
        r = check(cfg)
        for f in ("image", "initrd", "release"):
            self.assertTrue(errs(r, "os.kernel." + f), f)

    def test_storage_install(self):
        cfg = helpers.minimal_cfg()
        cfg["install"] = {"method": "ssh"}
        self.assertTrue(errs(check(cfg), "ssh_host"))
        cfg["install"] = {"method": "ssh", "ssh_host": "10.0.0.9"}
        cfg["storage"] = {"layout": "v2"}
        self.assertTrue(errs(check(cfg), "storage.layout"))
        cfg["storage"] = {"root_size": "12"}
        self.assertTrue(errs(check(cfg), "root_size"))
        cfg["storage"] = {"root_size": "4096"}
        self.assertEqual(check(cfg).errors, [])


if __name__ == "__main__":
    unittest.main()
