# SPDX-License-Identifier: MIT
import copy
import os
import unittest

import helpers
from percept import launcher_conf, profiles, validate

PROFILES = os.path.join(helpers.ROOT, "profiles")


def board(**os_over):
    cfg = helpers.minimal_cfg()
    if os_over:
        cfg["os"] = os_over
    res = validate.validate(copy.deepcopy(cfg))
    assert res.ok, res.errors
    return res.config


def trixie():
    return profiles.load_profile(os.path.join(PROFILES, "debian-trixie"))


class ShippedProfiles(unittest.TestCase):
    def test_all_check_clean(self):
        for name in profiles.list_profiles(helpers.ROOT):
            p = profiles.load_profile(os.path.join(PROFILES, name))
            self.assertEqual(profiles.check_profile(p, name), [], name)

    def test_template_checks_clean_apart_from_name(self):
        p = profiles.load_profile(os.path.join(PROFILES, "_template"))
        self.assertEqual(profiles.check_profile(p, None), [])

    def test_check_catches_mistakes(self):
        p = trixie()
        p["fixup"].append({"name": "made-up", "kernels": ["6.12.*"]})
        p["contract"]["cmdline_baseline"] = "bad;chars"
        p["rootfs"]["type"] = "magic"
        p["features"]["vpu"]["requires"] = ["nonsense"]
        problems = " | ".join(profiles.check_profile(p, "debian-trixie"))
        for needle in ("made-up", "cmdline_baseline", "rootfs.type", "nonsense"):
            self.assertIn(needle, problems)


class Resolve(unittest.TestCase):
    def test_defaults_enable_everything_for_612(self):
        r = profiles.resolve(board(), trixie(), "UUID-X")
        self.assertEqual(r["fixups"]["launcher"], ["upper-ram", "thermal", "media-gpu-vpu"])
        self.assertEqual(r["fixups"]["esp-dtb"], ["usbc-extcon"])
        self.assertTrue(r["cmdline"].startswith("root=UUID=UUID-X ro console=ttymxc0,115200"))
        self.assertEqual(r["problems"], [])

    def test_audio_default_follows_profile(self):
        self.assertTrue(profiles.resolve(board(), trixie())["features"]["audio"])
        byo = profiles.load_profile(os.path.join(PROFILES, "byo-kernel"))
        self.assertFalse(profiles.effective_features(board(), byo)[0]["audio"])

    def test_audio_explicit_false_honoured(self):
        r = profiles.resolve(board(features={"audio": False}), trixie())
        self.assertFalse(r["features"]["audio"])
        self.assertTrue(profiles.resolve(board(features={"audio": True}), trixie())["features"]["audio"])

    def test_gpu_only(self):
        r = profiles.resolve(board(features={"vpu": False}), trixie())
        self.assertEqual(r["fixups"]["launcher"], ["upper-ram", "thermal", "media-gpu"])

    def test_features_off(self):
        r = profiles.resolve(board(features={"gpu": False, "vpu": False, "upper_ram": False,
                                             "thermal": False, "usb_c_host": False}), trixie())
        self.assertEqual(r["fixups"], {"launcher": [], "esp-dtb": []})

    def test_cmdline_extra_appended_last(self):
        r = profiles.resolve(board(kernel={"cmdline_extra": "loglevel=3"}), trixie())
        self.assertTrue(r["cmdline"].endswith("cma=256M loglevel=3"))

    def test_fixups_are_kernel_specific(self):
        p = profiles.load_profile(os.path.join(PROFILES, "byo-kernel"))
        cfg = board(kernel={"source": "files", "image": __file__, "initrd": __file__, "release": "5.4.3-custom"})
        r = profiles.resolve(cfg, p)
        self.assertEqual(r["fixups"], {"launcher": [], "esp-dtb": []})  # 6.12 bindings do not apply to 5.4
        self.assertTrue(r["warnings"])  # outside validated releases
        cfg = board(kernel={"source": "files", "image": __file__, "initrd": __file__, "release": "6.12.20-custom"})
        self.assertEqual(profiles.resolve(cfg, p)["fixups"]["launcher"], ["upper-ram", "thermal", "media-gpu-vpu"])

    def test_unknown_feature_for_profile(self):
        p = trixie()
        del p["features"]["camera"]
        r = profiles.resolve(board(features={"camera": True}), p)
        self.assertTrue(any("camera" in x for x in r["problems"]))


class LauncherConf(unittest.TestCase):
    def test_matches_shipped_production_conf(self):
        """The generator must reproduce the hand-written conf that boots board 1."""
        with open(os.path.join(helpers.ROOT, "launcher", "launcher.conf.trixie"), encoding="utf-8") as f:
            shipped = launcher_conf.parse(f.read().replace("<ROOT-FS-UUID>", profiles.PLACEHOLDER_UUID))
        r = profiles.resolve(board(), trixie())
        generated = launcher_conf.parse(launcher_conf.render(r, board()))
        self.assertEqual(generated, shipped)

    def test_v2_has_new_keys_and_parses(self):
        cfg = board()
        cfg["rescue"].update(net_mode="static", address="10.0.0.5", prefix=24, gateway="10.0.0.1")
        text = launcher_conf.render(profiles.resolve(cfg, trixie()), cfg, compat="v2")
        d = launcher_conf.parse(text, "v2")
        self.assertEqual(d["net_ip"], "10.0.0.5")
        self.assertEqual(d["dtb_fixups"], "upper-ram,thermal,media-gpu-vpu")
        with self.assertRaises(launcher_conf.LauncherConfError):
            launcher_conf.parse(text, "current")  # the shipped init would reject these keys

    def test_parser_mirrors_init(self):
        bad = ["bogus=1", "no equals", "mode=other", "mode=kexec\nkernel=relative\ncmdline=a", "mode=kexec\ncmdline=a;b",
               "mode=kexec\ncmdline=ok\nmedia=huge", "mode=kexec\ncmdline=ok\nupper_ram=2"]
        for text in bad:
            with self.assertRaises(launcher_conf.LauncherConfError, msg=text):
                launcher_conf.parse(text + "\n")
        self.assertEqual(launcher_conf.parse("# c\n\nmode=rescue\r\n"), {"mode": "rescue"})

    def test_rescue_conf(self):
        self.assertEqual(launcher_conf.render_rescue(board()), "mode=rescue\n")
        launcher_conf.parse(launcher_conf.render_rescue(board(), "v2"), "v2")

    def test_grubenv_is_exactly_1024_bytes(self):
        for n in range(5):
            b = launcher_conf.grubenv(n)
            self.assertEqual(len(b), 1024)
            self.assertTrue(b.startswith(b"# GRUB Environment Block\npercept_tries=%d\n" % n))
            self.assertEqual(set(b[len(b.rstrip(b"#")):]), {ord("#")})
        with self.assertRaises(ValueError):
            launcher_conf.grubenv(5)

    def test_failcount(self):
        self.assertEqual(launcher_conf.failcount(0), b"0\n")


if __name__ == "__main__":
    unittest.main()
