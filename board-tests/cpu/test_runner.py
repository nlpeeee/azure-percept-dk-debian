# SPDX-License-Identifier: MIT
"""Local read/write fixtures only; never executes a real CPU workload or sysfs write.

python test_runner.py [--shell /path/to/sh]
On Windows use Git's usr/bin/sh.exe. On Linux /bin/sh is the default.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SHELL = '/bin/sh'
if '--shell' in sys.argv:
    at = sys.argv.index('--shell')
    SHELL = sys.argv[at + 1]
    del sys.argv[at:at + 2]
SOURCE = Path(__file__).with_name('run-cpu-test.sh').read_text()


class RunnerTests(unittest.TestCase):
    def run_shell(self, script):
        env = os.environ.copy()
        env['PATH'] = str(Path(SHELL).parent) + os.pathsep + env.get('PATH', '')
        return subprocess.run([SHELL, '-c', script], text=True, capture_output=True, env=env)

    def test_syntax(self):
        result = subprocess.run([SHELL, '-n'], input=SOURCE, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_default_help(self):
        result = self.run_shell(SOURCE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Usage:', result.stdout)

    def test_invalid_inputs_fail_before_root_or_system_access(self):
        for args in ('--frequency-khz 1500000 --duration-seconds 1',
                     '--frequency-khz 1300000 --duration-seconds 0',
                     '--frequency-khz 1300000 --duration-seconds 3601',
                     '--frequency-khz 900000 --duration-seconds 10',
                     '--frequency-khz 1300000 --duration-seconds 1 --workload mixed'):
            with self.subTest(args=args):
                result = self.run_shell('set -- ' + args + '\n' + SOURCE)
                self.assertEqual(result.returncode, 2, result.stderr)

    def fixture(self, *, temp='40000', minimum='1500000', errors=''):
        fixture = tempfile.TemporaryDirectory()
        root = Path(fixture.name)
        for sub in ('policy', 'thermal/thermal_zone0', 'output'):
            (root / sub).mkdir(parents=True)
        for name, value in {'policy/scaling_min_freq': minimum, 'policy/scaling_max_freq': '1500000',
                            'policy/scaling_cur_freq': '1300000', 'clock': 'arm_a53_core 1 1 0 1300000000\n',
                            'boot': 'fixture-boot', 'regulator': 'vdd_arm selector-report',
                            'gpio': 'gpio-13 vdd_arm out hi', 'thermal/thermal_zone0/temp': temp,
                            'thermal/thermal_zone0/type': 'cpu-thermal',
                            'output/new-kernel-errors.log': errors}.items():
            (root / name).write_text(value)
        # Translate only a test copy of the actual helper; production has no
        # path override or test mode that could bypass safety checks.
        path = root.as_posix()
        if os.name == 'nt':
            path = '/' + path[0].lower() + path[2:]
        prefix = f'''set -eu
policy='{path}/policy'
clock='{path}/clock'
boot='{path}/boot'
regulator='{path}/regulator'
gpio='{path}/gpio'
output='{path}/output'
freq=1300000
expected_boot=fixture-boot
log() {{ printf '%s\\n' "$*" >>"$output/events.log"; }}
fail() {{ echo "$*" >&2; exit 1; }}
'''
        sample = SOURCE[SOURCE.index('sample() {'):SOURCE.index('\nlog "start boot=')]
        sample = sample.replace('/sys/class/thermal/thermal_zone*', f"'{path}'/thermal/thermal_zone*")
        sample = sample.replace('/sys/class/thermal/cooling_device*', f"'{path}'/thermal/cooling_device*")
        cap = SOURCE[SOURCE.index('cap() {'):SOURCE.index('\ncleanup() {')]
        return fixture, root, prefix, sample, cap

    def test_cap_drops_overclock_and_does_not_raise_low_minimum(self):
        for minimum, expected in [('1500000', '1300000'), ('800000', '800000')]:
            fixture, root, prefix, _, cap = self.fixture(minimum=minimum)
            with fixture:
                result = self.run_shell(prefix + cap + '\ncap\n')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((root / 'policy/scaling_max_freq').read_text().strip(), '1300000')
                self.assertEqual((root / 'policy/scaling_min_freq').read_text().strip(), expected)

    def test_normal_sample_records_requested_and_actual(self):
        fixture, root, prefix, sample, _ = self.fixture()
        with fixture:
            result = self.run_shell(prefix + sample + '\nsample\n')
            self.assertEqual(result.returncode, 0, result.stderr)
            events = (root / 'output/events.log').read_text()
            self.assertIn('requested_khz=1300000 actual_arm_a53_core_hz=1300000000', events)
            self.assertIn('millidegrees=40000', events)
            self.assertIn('gpio-13', (root / 'output/power-state.log').read_text())

    def test_thermal_boundary_sensor_loss_and_kernel_error_stop(self):
        for temperature, errors, message in [('80000', '', 'Thermal stop'),
                                             ('bad', '', 'Invalid temperature'),
                                             ('40000', 'new kernel WARN', 'New kernel error')]:
            fixture, _, prefix, sample, _ = self.fixture(temp=temperature, errors=errors)
            with fixture:
                result = self.run_shell(prefix + sample + '\nsample\n')
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(message, result.stderr)


if __name__ == '__main__':
    unittest.main()
