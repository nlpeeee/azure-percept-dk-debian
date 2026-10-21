# SPDX-License-Identifier: MIT
"""Orchestrator fixtures: replace the adjacent runner, never invoke real DVFS."""
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SHELL = '/bin/sh'
if '--shell' in sys.argv:
    at = sys.argv.index('--shell')
    SHELL = sys.argv[at + 1]
    del sys.argv[at:at + 2]
HERE = Path(__file__).parent


class SuiteTests(unittest.TestCase):
    def fixture(self):
        fixture = tempfile.TemporaryDirectory()
        root = Path(fixture.name)
        (root / 'test-suite.sh').write_text((HERE / 'test-suite.sh').read_text())
        (root / 'run-cpu-test.sh').write_text('''#!/bin/sh
printf '%s\\n' "$*" >>"$MOCK_LEDGER"
output=
while [ "$#" -gt 0 ]; do
    case "$1" in --output) output=$2; shift 2 ;; *) shift ;; esac
done
mkdir "$output"
trap 'echo cap1300000 >"$MOCK_CAP"; exit 143' TERM HUP INT
[ "${MOCK_WAIT:-0}" != 1 ] || { while :; do sleep 1; done; }
case "$output" in *"${MOCK_FAIL:-never-matches}"*) exit 7 ;; esac
echo cap1300000 >"$MOCK_CAP"
''')
        env = os.environ.copy()
        env['PATH'] = str(Path(SHELL).parent) + os.pathsep + env.get('PATH', '')
        env['MOCK_LEDGER'] = str(root / 'ledger').replace('\\', '/')
        env['MOCK_CAP'] = str(root / 'cap').replace('\\', '/')
        return fixture, root, env

    def command(self, root, suite, oc=False):
        cmd = [SHELL, str(root / 'test-suite.sh'), '--suite', suite, '--boot-id', 'fixture-boot',
               '--output-root', str(root / 'logs'), '--network', 'fixture-peer', '--temp-parent', str(root)]
        return cmd + (['--allow-overclock'] if oc else [])

    def stages(self, root):
        result = []
        for line in (root / 'ledger').read_text().splitlines():
            args = shlex.split(line)
            args = [arg for arg in args if arg != '--allow-overclock']
            result.append(dict(zip(args[::2], args[1::2])))
        return result

    def test_syntax_and_help(self):
        env = os.environ.copy()
        env['PATH'] = str(Path(SHELL).parent) + os.pathsep + env.get('PATH', '')
        result = subprocess.run([SHELL, '-n', str(HERE / 'test-suite.sh')], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([SHELL, str(HERE / 'test-suite.sh')], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Usage:', result.stdout)

    def test_stage_sequences_and_durations(self):
        for suite, count, duration in [('smoke', 3, 15), ('rated', 32, 2700), ('oc1500', 4, 5760)]:
            with self.subTest(suite=suite):
                fixture, root, env = self.fixture()
                with fixture:
                    result = subprocess.run(self.command(root, suite, suite == 'oc1500'), env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    stages = self.stages(root)
                    self.assertEqual(len(stages), count)
                    self.assertEqual(sum(int(s['--duration-seconds']) for s in stages), duration)
                    self.assertEqual(len({s['--output'] for s in stages}), count)
                    if suite == 'rated':
                        self.assertEqual([s['--frequency-khz'] for s in stages[:2]], ['800000', '1300000'])
                        self.assertEqual([s['--workload'] for s in stages[2:]], ['idle', 'mixed'] * 15)
                    if suite == 'oc1500':
                        # Flag has no value, so assert it separately in recorded argv.
                        self.assertEqual((root / 'ledger').read_text().count('--allow-overclock'), 4)
                    self.assertIn('PASS suite=', (root / 'logs/suite.log').read_text())

    def test_stops_after_first_failure(self):
        fixture, root, env = self.fixture()
        with fixture:
            env['MOCK_FAIL'] = '02-1300-mixed'
            result = subprocess.run(self.command(root, 'smoke'), env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertEqual(len(self.stages(root)), 2)
            self.assertIn('FAIL stage=02-1300-mixed', (root / 'logs/suite.log').read_text())

    def test_overclock_needs_explicit_authorization(self):
        fixture, root, env = self.fixture()
        with fixture:
            result = subprocess.run(self.command(root, 'oc1500'), env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((root / 'ledger').exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX process signals require Linux/Unix')
    def test_signal_forward_waits_for_runner_cap(self):
        fixture, root, env = self.fixture()
        with fixture:
            env['MOCK_WAIT'] = '1'
            process = subprocess.Popen(self.command(root, 'smoke'), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 5
                while not (root / 'logs/01-800-cpu').exists() and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue((root / 'logs/01-800-cpu').exists())
                process.send_signal(signal.SIGTERM)
                process.communicate(timeout=8)
                self.assertEqual(process.returncode, 143)
                self.assertEqual((root / 'cap').read_text().strip(), 'cap1300000')
                self.assertEqual(len(self.stages(root)), 1)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    @unittest.skipIf(os.name == 'nt', 'setsid process-group semantics require Linux/Unix')
    def test_runner_stops_own_group_and_preserves_unrelated_process(self):
        import shutil
        if not shutil.which('setsid'):
            self.skipTest('setsid unavailable')
        source = (HERE / 'run-cpu-test.sh').read_text()
        stop = source[source.index('stop_group() {'):source.index('\ncap() {')]
        # One owned group with a worker and one unrelated process. Assert the
        # worker's TERM handler executes, while the unrelated process survives.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / 'worker.sh'
            worker.write_text('trap \'echo stopped >"$1"; exit 0\' TERM\nwhile :; do sleep 1; done\n')
            script = f'''set -eu
{stop}
setsid sh {shlex.quote(str(worker))} {shlex.quote(str(root / 'stopped'))} &
owned=$!
sleep 20 &
unrelated=$!
trap 'kill "$owned" "$unrelated" 2>/dev/null || :' 0
sleep 1
stop_group "$owned"
test -s {shlex.quote(str(root / 'stopped'))}
kill -0 "$unrelated"
kill "$unrelated"
wait "$unrelated" 2>/dev/null || :
'''
            result = subprocess.run([SHELL, '-c', script], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
