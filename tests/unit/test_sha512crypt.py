# SPDX-License-Identifier: MIT
import shutil
import subprocess
import unittest

import helpers  # noqa: F401
from percept import sha512crypt as c


class Sha512Crypt(unittest.TestCase):
    def test_drepper_vectors(self):
        self.assertEqual(c.crypt("Hello world!", "saltstring"),
                         "$6$saltstring$svn8UoSVapNtMuq1ukKS4tPQd8iKwSMHWjl/O817G3uBnIFNjnQJuesI68u4OTLiBFdcbYEdFCoEOfaS35inz1")
        self.assertEqual(c.crypt("Hello world!", "saltstringsaltstring", 10000),
                         "$6$rounds=10000$saltstringsaltst$OW1/O6BYHV6BcXZu8QVeXbDWra3Oeqh0sbHbbMCVNSnCM/UrjmM0Dp8vOuZeHBy/YTBmSK6H9qs/y3RnOaw5v.")

    def test_matches_openssl(self):
        if not shutil.which("openssl"):
            self.skipTest("no openssl")
        out = subprocess.run(["openssl", "passwd", "-6", "-salt", "abcdefgh", "hunter2-Test"],
                             capture_output=True, text=True)
        if out.returncode != 0:
            self.skipTest("openssl lacks -6")
        self.assertEqual(c.crypt("hunter2-Test", "abcdefgh"), out.stdout.strip())

    def test_verify_and_shape(self):
        h = c.crypt("correct horse")
        self.assertTrue(c.looks_like_hash(h))
        self.assertTrue(c.verify("correct horse", h))
        self.assertFalse(c.verify("wrong", h))
        self.assertFalse(c.looks_like_hash("plaintext"))
        self.assertNotEqual(c.crypt("x"), c.crypt("x"))  # random salt


if __name__ == "__main__":
    unittest.main()
