#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prove exact original CPU OPP contract and byte-only output change."""
import argparse, hashlib, json, struct, sys
from pathlib import Path
from fdt_contract import walk_properties

def sha(b): return hashlib.sha256(b).hexdigest()
def validate(source, output, profile):
    _,nodes=walk_properties(source)
    expected=bytearray(source)
    masks=[(15,4),(14,3),(12,4),(8,3)]
    paths=[f'/opp-table/opp-{h}' for h in (800000000,1000000000,1300000000,1500000000)]
    assert {p for p in nodes if p.startswith('/opp-table/')}==set(paths)
    for p,h,uv,mask in zip(paths,(800000000,1000000000,1300000000,1500000000),(900000,900000,1000000,1000000),masks):
        props=nodes[p]
        want={'opp-hz':struct.pack('>Q',h),'opp-microvolt':struct.pack('>I',uv),'opp-supported-hw':struct.pack('>II',*mask),'clock-latency-ns':struct.pack('>I',150000),'opp-suspend':b''}
        assert {k:v[0] for k,v in props.items()}==want,p
    _,start,_=nodes[paths[-1]]['opp-supported-hw']
    if profile=='oc1500': expected[start+12:start+20]=struct.pack('>II',4,4)
    assert output==expected,'unexpected byte changed'
    active=[h for h,m in zip((800,1000,1300,1500),masks[:-1]+([(4,4)] if profile=='oc1500' else [masks[-1]])) if m[0]&4 and m[1]&4]
    assert active==([800,1300,1500] if profile=='oc1500' else [800,1300])
    return {'profile':profile,'input_sha256':sha(source),'output_sha256':sha(output),'original_1500_mask':[8,3],'active_mhz_for_grade_4_4':active,'all_other_bytes_identical':True,'voltage_max_uv':1000000}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('profile',choices=['rated','oc1500']);a=p.parse_args()
    record=validate(a.source.read_bytes(),a.output.read_bytes(),a.profile)
    a.output.with_suffix(a.output.suffix+'.cpu.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
