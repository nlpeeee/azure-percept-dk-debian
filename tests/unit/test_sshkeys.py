# SPDX-License-Identifier: MIT
import unittest

import helpers
from percept import sshkeys


class SshKeys(unittest.TestCase):
    def test_good_keys(self):
        norm, warn = sshkeys.check_key(helpers.ed25519_key(comment="me@pc"))
        self.assertTrue(norm.endswith("me@pc"))
        self.assertIsNone(warn)
        self.assertIsNone(sshkeys.check_key(helpers.rsa_key(4096))[1])

    def test_rsa_sizes(self):
        self.assertIsNotNone(sshkeys.check_key(helpers.rsa_key(2048))[1])  # warns
        with self.assertRaises(sshkeys.PublicKeyError):
            sshkeys.check_key(helpers.rsa_key(1024))

    def test_rejects(self):
        good = helpers.ed25519_key()
        for bad in ("", "ssh-ed25519", "-----BEGIN OPENSSH PRIVATE KEY-----",  # scrub-ok: deliberate fixture
                    'command="rm -rf /" ' + good, "ssh-ed25519 !!!notbase64!!!",
                    "ssh-rsa " + good.split()[1], good + "\nssh-ed25519 AAAA"):
            with self.assertRaises(sshkeys.PublicKeyError, msg=bad):
                sshkeys.check_key(bad)

    def test_ed25519_wrong_length(self):
        import base64
        blob = helpers._s(b"ssh-ed25519") + helpers._s(b"\x01" * 31)
        with self.assertRaises(sshkeys.PublicKeyError):
            sshkeys.check_key("ssh-ed25519 " + base64.b64encode(blob).decode())


if __name__ == "__main__":
    unittest.main()
