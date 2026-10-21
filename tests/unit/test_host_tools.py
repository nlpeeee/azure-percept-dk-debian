# SPDX-License-Identifier: MIT
import os
import unittest

import helpers
from percept import doctor, redact, wsl


class Paths(unittest.TestCase):
    def test_win_to_wsl(self):
        self.assertEqual(wsl.win_to_wsl_path("C:\\Users\\me\\x y"), "/mnt/c/Users/me/x y")
        self.assertEqual(wsl.win_to_wsl_path("e:/proj"), "/mnt/e/proj")
        self.assertEqual(wsl.win_to_wsl_path("\\\\wsl.localhost\\Debian\\home\\me"), "/home/me")
        with self.assertRaises(ValueError):
            wsl.win_to_wsl_path("/already/linux")

    def test_wsl_to_win(self):
        self.assertEqual(wsl.wsl_to_win_path("/mnt/c/Users/me"), "C:\\Users\\me")
        self.assertEqual(wsl.wsl_to_win_path("/mnt/e"), "E:\\")
        self.assertEqual(wsl.wsl_to_win_path("/home/me", "Debian"), "\\\\wsl.localhost\\Debian\\home\\me")
        with self.assertRaises(ValueError):
            wsl.wsl_to_win_path("/home/me")

    def test_utf16_output_decoding(self):
        raw = "Debian\r\nUbuntu\r\n".encode("utf-16-le")
        self.assertEqual(wsl.decode_output(raw).split(), ["Debian", "Ubuntu"])
        self.assertEqual(wsl.decode_output(b"plain"), "plain")

    def test_reexec_argv(self):
        a = wsl.reexec_argv("Debian", "/mnt/e/repo", ["build", "--board", "x"])
        self.assertEqual(a[:5], ["wsl.exe", "-d", "Debian", "--cd", "/mnt/e/repo"])
        self.assertEqual(a[-3:], ["build", "--board", "x"])


def fake_runner(distros=("Debian",), v2=True, tools_missing=(), binfmt=True, userns=True, git_ignored=True):
    def run(argv, timeout=60, input_text=None):
        if argv[:2] == ["wsl.exe", "-l"] and argv[2] == "-q":
            return 0, "\r\n".join(distros) + "\r\n", ""
        if argv[:3] == ["wsl.exe", "-l", "-v"]:
            return 0, "  NAME  STATE  VERSION\r\n* %s  Running  %d\r\n" % (distros[0], 2 if v2 else 1), ""
        if argv[:2] == ["wsl.exe", "-d"]:
            cmd = argv[-1]
            return linux(cmd)
        if argv[0] == "git":
            return (0 if git_ignored else 1), "", ""
        return 127, "", "unexpected " + " ".join(argv)

    def linux(cmd):
        if cmd.startswith("command -v "):
            return (1 if cmd.split()[-1] in tools_missing else 0), "", ""
        if cmd.startswith("unshare"):
            return (0 if userns else 1), "", ""
        if "binfmt_misc" in cmd:
            return (0, "enabled\ninterpreter /usr/bin/qemu-aarch64-static\n", "") if binfmt else (1, "", "")
        return 0, "", ""
    return run


class Doctor(unittest.TestCase):
    def names(self, checks, status):
        return {c.name for c in checks if c.status == status}

    def test_all_good_on_windows(self):
        checks = doctor.run_all(helpers.ROOT, runner=fake_runner(), which=lambda n: "C:\\x\\" + n, kind="windows")
        self.assertEqual(self.names(checks, "fail"), set(), doctor.format_checks(checks))
        self.assertEqual(doctor.exit_code(checks), 0)

    def test_no_wsl(self):
        checks = doctor.run_all(helpers.ROOT, runner=fake_runner(), which=lambda n: None, kind="windows")
        self.assertIn("WSL", self.names(checks, "fail"))
        self.assertIn("wsl --install", doctor.format_checks(checks))

    def test_no_distro_wsl1_missing_tools(self):
        which = lambda n: "x"
        c = doctor.run_all(helpers.ROOT, runner=fake_runner(distros=()), which=which, kind="windows")
        self.assertIn("WSL distro", self.names(c, "fail"))
        c = doctor.run_all(helpers.ROOT, runner=fake_runner(v2=False), which=which, kind="windows")
        self.assertIn("WSL version", self.names(c, "fail"))
        c = doctor.run_all(helpers.ROOT, runner=fake_runner(tools_missing=("debootstrap", "mcopy"), binfmt=False, userns=False),
                           which=which, kind="windows")
        failed = self.names(c, "fail")
        self.assertTrue({"debootstrap", "mcopy", "arm64 emulation", "rootless namespaces"} <= failed)
        text = doctor.format_checks(c)
        self.assertIn("sudo apt install", text)
        self.assertIn("debootstrap", text)

    def test_unignored_boards_dir_is_fatal(self):
        c = doctor.run_all(helpers.ROOT, runner=fake_runner(git_ignored=False), which=lambda n: "x", kind="windows")
        self.assertIn("secrets ignored", self.names(c, "fail"))

    def test_unsupported_host(self):
        c = doctor.run_all(helpers.ROOT, runner=fake_runner(), kind="macos")
        self.assertEqual(doctor.exit_code(c), 1)

    def test_python_and_disk(self):
        self.assertEqual(doctor.check_python((3, 8, 0)).status, "fail")
        self.assertEqual(doctor.check_python((3, 12, 1)).status, "ok")
        self.assertEqual(doctor.check_disk(".", free_bytes=5e9).status, "warn")
        self.assertEqual(doctor.check_disk(".", free_bytes=500e9).status, "ok")


class Redaction(unittest.TestCase):
    def test_collects_and_masks_everything(self):
        cfg = {"network": {"wifi": {"ssid": "Home", "psk": "super-secret-psk"}},
               "user": [{"name": "u", "password_hash": "$6$salt$" + "a" * 86}]}
        secrets = redact.collect_secrets(cfg)
        r = redact.Redactor(secrets)
        derived = redact.wifi_psk_hex("Home", "super-secret-psk")
        text = "psk=super-secret-psk hex=%s hash=%s tail=%s" % (derived, cfg["user"][0]["password_hash"], "a" * 86)
        out = r(text)
        for s in ("super-secret-psk", derived, "a" * 86, "$6$salt$"):
            self.assertNotIn(s, out)
        self.assertIn("***", out)

    def test_longest_first_and_short_ignored(self):
        r = redact.Redactor(["abcd", "abcdefgh", "xy"])
        self.assertEqual(r("abcdefgh xy"), "*** xy")

    def test_known_wpa_vector(self):
        # IEEE 802.11i test vector
        self.assertEqual(redact.wifi_psk_hex("IEEE", "password"),
                         "f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e")


if __name__ == "__main__":
    unittest.main()
