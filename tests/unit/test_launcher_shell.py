# SPDX-License-Identifier: MIT
"""Run launcher/lib/percept-config.sh under busybox and check it against the Python generator.

busybox must be on PATH (Debian: busybox-static) or reachable through WSL on Windows;
otherwise these tests are skipped.
"""
import copy
import os
import shutil
import subprocess
import tempfile
import unittest

import helpers
from percept import launcher_conf, profiles, validate, wsl

LIB = os.path.join(helpers.ROOT, "launcher", "lib", "percept-config.sh")
HARNESS = os.path.join(helpers.ROOT, "tests", "launcher", "harness.sh")


def _runner():
    if shutil.which("busybox"):
        return lambda argv: ["busybox", "sh"] + argv, lambda p: p
    if os.name == "nt" and wsl.wsl_exe():
        probe = subprocess.run(["wsl.exe", "-e", "busybox", "true"], capture_output=True)
        if probe.returncode == 0:
            return (lambda argv: ["wsl.exe", "-e", "busybox", "sh"] + argv), wsl.win_to_wsl_path
    return None, None


BUILD, TOPATH = _runner()


@unittest.skipIf(BUILD is None, "busybox not available")
class LauncherShell(unittest.TestCase):
    def sh(self, mode, *args):
        argv = [TOPATH(HARNESS), TOPATH(LIB), mode] + list(args)
        out = subprocess.run(BUILD(argv), capture_output=True, text=True, timeout=60)
        return dict(l.split("=", 1) for l in out.stdout.splitlines() if "=" in l and not l.startswith("LOG ")), out.stdout

    def read(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False, newline="") as f:
            f.write(text)
        try:
            return self.sh("read", TOPATH(f.name))
        finally:
            os.unlink(f.name)

    def call(self, fn, *args):
        return self.sh("call", fn, *args)[0]

    # --- primitives -------------------------------------------------------
    def test_validators(self):
        cases = {
            "valid_path": [("/vmlinuz", 0), ("/boot/vmlinuz-6.12+deb13", 0), ("vmlinuz", 1), ("/a/../b", 1), ("/a b", 1), ("//x", 1)],
            "valid_ipv4": [("10.0.0.1", 0), ("255.255.255.255", 0), ("256.1.1.1", 1), ("1.2.3", 1), ("1..2.3", 1), ("a.b.c.d", 1), ("", 1)],
            "valid_devspec": [("/dev/mmcblk0p3", 0), ("UUID=1234-ABCD", 0), ("LABEL=percept-root", 0), ("PARTUUID=abc-01", 0),
                              ("UUID=", 1), ("UUID=a b", 1), ("root", 1), ("/dev/../x", 1)],
            "valid_cmdline": [("root=UUID=x ro console=ttymxc0,115200", 0), ("a;b", 1), ("$(x)", 1), ("", 1)],
            "valid_iface_spec": [("auto", 0), ("eth0", 0), ("fc:34:97:00:00:01", 0), ("eth0;x", 1), ("zz:zz:zz:zz:zz:zz", 1)],
        }
        for fn, rows in cases.items():
            for arg, rc in rows:
                self.assertEqual(self.call(fn, arg)["rc"], str(rc), "%s %r" % (fn, arg))
        self.assertEqual(self.call("valid_uint", "5", "1", "10")["rc"], "0")
        self.assertEqual(self.call("valid_uint", "11", "1", "10")["rc"], "1")
        self.assertEqual(self.call("valid_uint", "x", "1", "10")["rc"], "1")

    def test_esp_spec(self):
        self.assertEqual(self.call("esp_spec", "console=x percept.esp=UUID=1234-ABCD quiet")["out"], "UUID=1234-ABCD")
        self.assertEqual(self.call("esp_spec", "quiet")["out"], "/dev/mmcblk0p1")
        self.assertEqual(self.call("esp_spec", "percept.esp=bad;value")["out"], "/dev/mmcblk0p1")

    # --- reading real configs ---------------------------------------------------
    def test_shipped_legacy_conf_still_parses(self):
        with open(os.path.join(helpers.ROOT, "launcher", "launcher.conf.trixie"), encoding="utf-8") as f:
            text = f.read().replace("<ROOT-FS-UUID>", "0f0f0f0f-1111-2222-3333-444444444444")
        v, raw = self.read(text)
        self.assertEqual(v["rc"], "0", raw)
        self.assertEqual(v["conf_fixups"], "upper-ram,thermal,media-gpu-vpu")  # legacy keys translated
        self.assertEqual(v["root_spec"], "UUID=0f0f0f0f-1111-2222-3333-444444444444")  # from root= in cmdline
        self.assertEqual(v["conf_net_mode"], "dhcp")
        self.assertEqual(v["conf_fail_limit"], "3")

    def test_v2_conf_values(self):
        v, raw = self.read("mode=kexec\nkernel=/vmlinuz\ninitrd=/initrd.img\ndtb_fixups=upper-ram,media-gpu\n"
                           "dtb_fixups_policy=strict\nnet_mode=static\nnet_ip=10.1.2.3\nnet_prefix=24\nnet_gw=10.1.2.1\n"
                           "fail_limit=5\nroot=LABEL=percept-root\nrescue_console=ttymxc0\ncmdline=root=/dev/x ro\r\n")
        self.assertEqual(v["rc"], "0", raw)
        self.assertEqual((v["conf_net_ip"], v["conf_net_gw"], v["conf_fail_limit"]), ("10.1.2.3", "10.1.2.1", "5"))
        self.assertEqual(v["root_spec"], "LABEL=percept-root")  # explicit root wins
        self.assertEqual(v["conf_fixups_policy"], "strict")

    def test_root_spec_fallback_is_factory_device(self):
        v, _ = self.read("mode=kexec\nkernel=/vmlinuz\ninitrd=/initrd.img\ncmdline=root=/dev/mmcblk1p3 ro\n")
        self.assertEqual(v["root_spec"], "/dev/mmcblk0p3")  # Debian-style /dev name is not valid under the stock kernel

    def test_initrd_optional(self):
        v, raw = self.read("kernel=/vmlinuz\ncmdline=ro\n")
        self.assertEqual(v["rc"], "0", raw)
        self.assertEqual(v["conf_initrd"], "")

    def test_rescue_mode_needs_little(self):
        v, raw = self.read("mode=rescue\nnet_mode=static\nnet_ip=192.0.2.5\nnet_prefix=24\n")
        self.assertEqual(v["rc"], "0", raw)

    def test_rejections(self):
        base = "kernel=/vmlinuz\ninitrd=/initrd.img\ncmdline=ro\n"
        bad = [
            "bogus=1\n", "no equals sign\n", "mode=other\n", "net_mode=wifi\n", "net_mode=static\n",
            "net_mode=static\nnet_ip=300.1.1.1\nnet_prefix=24\n", "net_mode=static\nnet_ip=1.2.3.4\nnet_prefix=31\n",
            "fail_limit=0\n", "fail_limit=11\n", "dtb_fixups=magic\n", "dtb_fixups_policy=maybe\n",
            "upper_ram=1\ndtb_fixups=thermal\n", "upper_ram=2\n", "media=huge\n", "cpu_profile=oc1500\n",
            "profile=other\n", "root=nothing\n", "root_opts=a;b\n", "kernel_format=zip\n", "log_receiver_ip=1.2.3.4\n",
            "board_model=a;b\n", "rescue_console=tty/0\n",
        ]
        for extra in bad:
            v, raw = self.read(base + extra)
            self.assertEqual(v["rc"], "1", "should reject %r: %s" % (extra, raw))
        for text in ("cmdline=a;b\nkernel=/v\n", "kernel=bad\ncmdline=ro\n", "cmdline=ro\n", "kernel=/v\ncmdline=\n"):
            self.assertEqual(self.read(text)[0]["rc"], "1", text)

    # --- agreement with the Python generator --------------------------------------
    def board(self, **rescue):
        cfg = helpers.minimal_cfg()
        cfg["rescue"] = rescue
        res = validate.validate(copy.deepcopy(cfg))
        self.assertTrue(res.ok, res.errors)
        return res.config

    def test_generated_files_are_accepted_by_the_shell_parser(self):
        prof = profiles.load_profile(os.path.join(helpers.ROOT, "profiles", "debian-trixie"))
        for rescue in ({}, {"net_mode": "static", "address": "10.9.8.7", "prefix": 24, "gateway": "10.9.8.1"},
                       {"log_receiver_ip": "10.9.8.2", "log_receiver_port": 6666}):
            cfg = self.board(**rescue)
            r = profiles.resolve(cfg, prof, "0f0f0f0f-1111-2222-3333-444444444444")
            for compat in ("current", "v2"):
                text = launcher_conf.render(r, cfg, compat)
                v, raw = self.read(text)
                self.assertEqual(v["rc"], "0", "%s %s\n%s\n%s" % (compat, rescue, text, raw))
                self.assertEqual(v["conf_fixups"], ",".join(r["fixups"]["launcher"]))
            self.assertEqual(self.read(launcher_conf.render_rescue(cfg, "v2"))[0]["rc"], "0")

    def test_python_and_shell_parsers_agree(self):
        samples = ["mode=rescue\n", "mode=kexec\nkernel=/v\ncmdline=ro\n", "kernel=/v\ncmdline=ro\nnet_mode=static\n",
                   "kernel=/v\ncmdline=ro\nfail_limit=11\n", "kernel=/v\ncmdline=a;b\n", "mode=kexec\nbogus=1\n",
                   "kernel=/v\ncmdline=ro\ndtb_fixups=upper-ram,thermal\ndtb_fixups_policy=strict\n",
                   "kernel=/v\ncmdline=ro\nupper_ram=1\ndtb_fixups=thermal\n", "kernel=/v\ncmdline=ro\nnet_mode=dhcp\nnet_if=eth0\n"]
        for text in samples:
            try:
                launcher_conf.parse(text, "v2")
                py_ok = True
            except launcher_conf.LauncherConfError:
                py_ok = False
            sh_ok = self.read(text)[0]["rc"] == "0"
            self.assertEqual(py_ok, sh_ok, "parsers disagree on %r (python=%s shell=%s)" % (text, py_ok, sh_ok))


if __name__ == "__main__":
    unittest.main()
