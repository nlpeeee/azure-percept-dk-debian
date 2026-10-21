#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run compiled helper against original DT and reject unsafe/unexpected inputs."""
import importlib.util,json,struct,subprocess,sys,tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('cpu_validator',Path(__file__).absolute().with_name('validate-dtb.py'))
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
helper=Path(sys.argv[1]).absolute();source=Path(sys.argv[2]).read_bytes()
with tempfile.TemporaryDirectory(prefix='percept-cpu-test-') as tmp:
    d=Path(tmp);inp=d/'input.dtb';inp.write_bytes(source);records=[]
    for profile in ('rated','oc1500'):
        out=d/(profile+'.dtb');subprocess.run([str(helper),str(inp),str(out),profile],check=True)
        records.append(v.validate(source,out.read_bytes(),profile))
    _,nodes=v.walk_properties(source)
    bads=[source[:100],(d/'oc1500.dtb').read_bytes()]
    for prop in ('opp-supported-hw','opp-microvolt','opp-hz','clock-latency-ns'):
        bad=bytearray(source);_,off,_=nodes['/opp-table/opp-1500000000'][prop];bad[off+12]^=1;bads.append(bytes(bad))
    for i,bad in enumerate(bads):
        inp.write_bytes(bad);out=d/f'bad-{i}.dtb'
        r=subprocess.run([str(helper),str(inp),str(out),'oc1500'])
        assert r.returncode!=0 and not out.exists(),i
    print(json.dumps({'native_profiles':records,'negative_inputs_rejected':len(bads)},indent=2))
