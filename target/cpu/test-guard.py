#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Isolate the actual shell guard with fixture paths, no module/device access."""
from pathlib import Path
import tempfile,subprocess,json,sys,os
shell=sys.argv[1] if len(sys.argv)>1 else '/bin/sh'
env=dict(os.environ);env['MODPROBE_OPTIONS']='-qb';env['PATH']=str(Path(shell).parent)+os.pathsep+env.get('PATH','')
with tempfile.TemporaryDirectory(prefix='percept-guard-') as tmp:
 d=Path(tmp);posix=lambda p:str(p).replace(chr(92),'/')
 guard=Path(__file__).absolute().with_name('cpufreq-load-guard').read_text()
 for old,new in [('/sys/module/cpufreq_powersave',posix(d/'registered')),('/proc/cmdline',posix(d/'cmdline')),('/etc/percept-cpu/enable-cpufreq',posix(d/'approval')),('/sbin/modprobe',posix(d/'modprobe'))]:guard=guard.replace(old,new)
 (d/'guard').write_text(guard);(d/'modprobe').write_text('#!/bin/sh\n[ -z "${MODPROBE_OPTIONS+x}" ] || exit 97\nprintf "%s\\n" "$*" > "'+posix(d/'called')+'"\n');(d/'modprobe').chmod(0o755)
 records=[]
 for name,registered,cmdline,approval,want in [('valid',True,'cpufreq.default_governor=powersave','voltage-contract-approved-v1',0),('no-module',False,'cpufreq.default_governor=powersave','voltage-contract-approved-v1',1),('no-arg',True,'','voltage-contract-approved-v1',1),('override',True,'cpufreq.default_governor=powersave cpufreq.default_governor=schedutil','voltage-contract-approved-v1',1),('duplicate',True,'cpufreq.default_governor=powersave cpufreq.default_governor=powersave','voltage-contract-approved-v1',1),('unapproved',True,'cpufreq.default_governor=powersave','',1)]:
  if registered:(d/'registered').mkdir(exist_ok=True)
  elif (d/'registered').exists():(d/'registered').rmdir()
  (d/'cmdline').write_text(cmdline);(d/'approval').write_text(approval)
  if (d/'called').exists():(d/'called').unlink()
  r=subprocess.run([shell,posix(d/'guard'),'imx_cpufreq_dt'],capture_output=True,env=env)
  assert (r.returncode==0)==(want==0),(name,r.stderr)
  assert (d/'called').exists()==(want==0),name
  records.append({'case':name,'passed':True})
 print(json.dumps({'isolated_shell_fixture_cases':records,'real_initramfs_executed':False},indent=2))
