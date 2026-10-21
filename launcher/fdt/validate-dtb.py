#!/usr/bin/env python3
"""Verify only GPU properties changed; prepare a negative resource fixture."""
import json
from pathlib import Path
import struct
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import prepare_percept_dtb as p

source=Path(sys.argv[1]); output=Path(sys.argv[2])
a,an=p.walk_properties(source.read_bytes()); b,bn=p.walk_properties(output.read_bytes())
allowed={('/gpu3d@38000000','status'),('/soc@0/gpu@38000000','status'),('/soc@0/gpu@38000000','assigned-clock-rates')}
assert an.keys()==bn.keys()
edits=[]
for path,props in an.items():
    assert props.keys()==bn[path].keys()
    for name,(value,*_) in props.items():
        if value!=bn[path][name][0]:
            assert (path,name) in allowed,(path,name)
            edits.append({'path':path,'property':name,'old':value.hex(),'new':bn[path][name][0].hex()})
assert {(e['path'],e['property']) for e in edits}==allowed
assert a['reservations']==b['reservations']
bad=bytearray(source.read_bytes()); _,start,_=an['/soc@0/gpu@38000000']['clocks']
struct.pack_into('>I',bad,start+16,999) # first clock's specifier, not its provider
source.with_name('bad-gpu-clock.dtb').write_bytes(bad)
source.with_name('truncated.dtb').write_bytes(source.read_bytes()[:100])
record={'edits':edits,'unchanged_nodes':len(an),'all_other_properties_identical':True,'reservations_identical':True}
output.with_suffix('.validation.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
