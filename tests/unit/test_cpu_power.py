# SPDX-License-Identifier: MIT
"""CPU profile generation and offline staging; never accesses device hardware."""
import copy
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

import helpers
from percept import launcher_conf, profiles, validate
import test_launcher_shell as launcher_shell

ROOT = Path(helpers.ROOT)
spec = importlib.util.spec_from_file_location("cpu_stage", ROOT/"target/cpu/stage.py")
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)

def config(profile="unchanged", **extra):
    c = helpers.minimal_cfg()
    c["os"] = {"cpu_profile": profile, **extra}
    r = validate.validate(copy.deepcopy(c))
    assert r.ok, r.errors
    return r.config

def resolve(c):
    return profiles.resolve(c, profiles.load_profile(str(ROOT/"profiles/debian-trixie")))

class CpuProfiles(unittest.TestCase):
    def test_default_preserves_blacklists_and_noop(self):
        c = config()
        r = resolve(c)
        self.assertEqual(r["cpu_profile"], "unchanged")
        self.assertIn("module_blacklist=rohm_bd718x7,bd718x7_regulator,imx_cpufreq_dt", r["cmdline"])
        self.assertNotIn("cpu_pmic=", launcher_conf.render(r, c))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(stage.stage(tmp, "unchanged"), [])
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_profiles_render_for_both_config_versions(self):
        for name in ("rated", "oc1500"):
            c = config(name)
            r = resolve(c)
            self.assertEqual(r["problems"], [])
            self.assertEqual(r["rootfs_env"], {"PERCEPT_CPU_PROFILE":name})
            self.assertNotIn("module_blacklist=", r["cmdline"])
            for token in ("cpuidle.off=1", "clk_ignore_unused", "pd_ignore_unused"):
                self.assertIn(token, r["cmdline"].split())
            for compat in ("current", "v2"):
                values = launcher_conf.parse(launcher_conf.render(r,c,compat), compat)
                self.assertEqual(values["cpu_pmic"], "1")
                self.assertEqual(values["cpu_profile"], name)

    def test_unrelated_blacklist_is_retained(self):
        r = resolve(config("rated", kernel={"cmdline_extra":"module_blacklist=other,imx_cpufreq_dt cpufreq.default_governor=powersave"}))
        self.assertIn("module_blacklist=other", r["cmdline"].split())
        self.assertEqual(r["cmdline"].split().count("cpufreq.default_governor=powersave"),1)

    def test_unsupported_kernel_and_missing_thermal_are_errors(self):
        self.assertTrue(resolve(config("rated", features={"thermal":False}))["problems"])
        c = config("rated", kernel={"source":"files", "image":__file__, "initrd":__file__, "release":"5.4.3-custom"})
        self.assertTrue(resolve(c)["problems"])
        self.assertTrue(resolve(config("rated", kernel={"cmdline_extra":"cpufreq.default_governor=schedutil"}))["problems"])

    def test_invalid_cpu_choice_is_rejected(self):
        c = helpers.minimal_cfg()
        c["os"]={"cpu_profile":"oc1800"}
        self.assertFalse(validate.validate(c).ok)

    def test_parser_rejects_incomplete_activation(self):
        prefix="kernel=/vmlinuz\ncmdline=ro cpufreq.default_governor=powersave\n"
        for suffix in ("cpu_profile=oc1500\n", "cpu_pmic=2\n", "cpu_profile=bad\n"):
            with self.assertRaises(launcher_conf.LauncherConfError):
                launcher_conf.parse(prefix+suffix,"v2")

    @unittest.skipIf(launcher_shell.BUILD is None, "busybox not available")
    def test_shell_accepts_generated_cpu_profiles_and_rejects_incomplete(self):
        harness=launcher_shell.LauncherShell()
        for name in ("rated","oc1500"):
            c=config(name)
            for compat in ("current","v2"):
                text=launcher_conf.render(resolve(c),c,compat)
                values,raw=harness.read(text)
                self.assertEqual(values["rc"],"0",raw)
                self.assertEqual(values["conf_cpu_profile"],name)
                self.assertNotEqual(harness.read(text.replace("cpu_pmic=1\n",""))[0]["rc"],"0")
                self.assertNotEqual(harness.read(text.replace("cpufreq.default_governor=powersave","cpufreq.default_governor=schedutil"))[0]["rc"],"0")

@unittest.skipIf(os.name == "nt", "Unix rootfs symlink semantics; run under WSL")
class CpuStaging(unittest.TestCase):
    def test_stage_profiles_idempotently_without_changing_unrelated_files(self):
        for profile,cap in (("rated","1300000"),("oc1500","1500000")):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                (root/"sentinel").write_bytes(b"preserve me")
                for _ in range(2): stage.stage(root,profile)
                self.assertEqual((root/"sentinel").read_bytes(),b"preserve me")
                self.assertEqual((root/"etc/percept-cpu/max-khz").read_text().strip(),cap)
                self.assertEqual((root/"etc/percept-cpu/enable-cpufreq").read_text().strip(),"voltage-contract-approved-v1")
                self.assertTrue((root/"etc/systemd/system/multi-user.target.wants/percept-cpu-policy.service").is_file())
                self.assertEqual((root/"lib/percept/cpufreq-load-guard").read_bytes(),(root/"usr/lib/percept/cpufreq-load-guard").read_bytes())
                self.assertEqual((root/"usr/lib/percept/cpu-policy.sh").stat().st_mode & 0o777,0o755)
                self.assertNotIn(b"\r",(root/"etc/initramfs-tools/hooks/percept-cpu").read_bytes())

    def test_symlink_escape_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root=Path(tmp)
            (root/"etc").symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):stage.stage(root,"rated")
            self.assertEqual(list(Path(outside).iterdir()),[])
            self.assertFalse((root/"usr").exists())
