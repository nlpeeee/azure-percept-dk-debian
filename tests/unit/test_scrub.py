# SPDX-License-Identifier: MIT
import importlib.util
import os
import tempfile
import unittest

import helpers

spec = importlib.util.spec_from_file_location("scrub_scan", os.path.join(helpers.ROOT, "dev", "scrub-scan.py"))
scrub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scrub)

# Assembled at runtime so this file itself carries no identifiers.
MAC = ":".join(["fc", "34", "97", "65", "90", "a0"])
IP = "192.168." + "1.60"


class Scrub(unittest.TestCase):
    def scan(self, files):
        with tempfile.TemporaryDirectory() as d:
            for name, text in files.items():
                p = os.path.join(d, name)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                mode = "wb" if isinstance(text, bytes) else "w"
                with open(p, mode) as f:
                    f.write(text)
            return scrub.scan(d)

    def test_finds_identifiers_and_secrets(self):
        hits = self.scan({"a.sh": "mac=%s\n" % MAC, "b.md": "ssh to %s now\n" % IP,
                          "c.txt": "StrictHostKeyChecking=no\n",  # scrub-ok: deliberate fixture
                          "d.txt": "-----BEGIN OPENSSH PRIVATE KEY-----\n",  # scrub-ok: deliberate fixture
                          "e.txt": "ssh-ed25519 " + "AAAA" + "C3NzaC1lZDI1NTE5AAAAIx" * 2 + " me\n"})
        kinds = {h[2] for h in hits}
        self.assertEqual(len(hits), 5, hits)
        self.assertTrue({"board-1 MAC", "host key checking off", "private key block"} <= kinds)

    def test_clean_and_optout(self):
        self.assertEqual(self.scan({"a.md": "nothing here\n", "b.md": "%s  # scrub-ok: documented example\n" % MAC}), [])

    def test_big_file_flagged_binary_ignored(self):
        hits = self.scan({"big.bin": b"\0" * 1_200_000, "small.bin": b"\0" + MAC.encode()})
        self.assertEqual([h[2] for h in hits], ["file over 1 MB (1200000 bytes)"])

    def test_repository_is_clean(self):
        """New leaks fail the build; legacy board-bound code is tracked in dev/scrub-debt.txt."""
        debt = scrub.load_debt(helpers.ROOT)
        new = [h for h in scrub.scan(helpers.ROOT) if h[0] not in debt]
        self.assertEqual(new, [], "\n".join("%s:%d %s" % h[:3] for h in new))

    def test_debt_entries_still_exist_and_still_leak(self):
        """A debt entry that no longer leaks must be deleted from the list."""
        hits = {h[0] for h in scrub.scan(helpers.ROOT)}
        for path in scrub.load_debt(helpers.ROOT):
            self.assertTrue(os.path.exists(os.path.join(helpers.ROOT, path)), path)
            self.assertIn(path, hits, "%s is clean now: remove it from dev/scrub-debt.txt" % path)


if __name__ == "__main__":
    unittest.main()
