# SPDX-License-Identifier: MIT
"""Exercise the actual persistent-policy script on isolated files, never sysfs."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

shell = sys.argv[1] if len(sys.argv) > 1 else '/bin/sh'
env = dict(os.environ)
env['PATH'] = str(Path(shell).parent) + os.pathsep + env.get('PATH', '')
source = Path(__file__).with_name('cpu-policy.sh').read_text()
cases = [('rated', '1300000', '800000 1300000', True, 0),
         ('oc', '1500000', '800000 1300000 1500000', True, 0),
         ('missing-opp', '1500000', '800000 1300000', True, 1),
         ('invalid-limit', '1800000', '800000 1300000', True, 1),
         ('no-cooling', '1500000', '800000 1300000 1500000', False, 1)]
for name, limit, available, cooling, expected in cases:
    with tempfile.TemporaryDirectory(prefix='percept-policy-') as tmp:
        root = Path(tmp)
        policy = root/'policy'
        policy.mkdir()
        values = {'scaling_min_freq':'800000', 'scaling_max_freq':'1300000',
                  'affected_cpus':'0 1 2 3 ', 'scaling_available_frequencies':available,
                  'scaling_available_governors':'performance powersave schedutil',
                  'scaling_governor':'powersave'}
        for key, value in values.items(): (policy/key).write_text(value+'\n')
        (root/'limit').write_text(limit+'\n')
        zone = root/'thermal'
        zone.mkdir()
        if cooling:
            (zone/'cdev0').mkdir()
            (zone/'cdev0'/'type').write_text('cpufreq-cpu0\n')
        posix = lambda path: str(path).replace('\\','/')
        script = source.replace('/sys/devices/system/cpu/cpufreq/policy0',posix(policy))
        script = script.replace('/etc/percept-cpu/max-khz',posix(root/'limit'))
        script = script.replace('/sys/class/thermal/thermal_zone0',posix(zone))
        script = script.replace('seq 1 60','seq 1 1').replace('sleep 1','true')
        result = subprocess.run([shell,'-c',script],capture_output=True,text=True,env=env)
        assert (result.returncode == 0) == (expected == 0), (name,result.stderr)
        if expected == 0:
            assert (policy/'scaling_max_freq').read_text().strip() == limit
            assert (policy/'scaling_governor').read_text().strip() == 'schedutil'
        else:
            assert (policy/'scaling_max_freq').read_text().strip() == '1300000'
        print(name+': pass')
