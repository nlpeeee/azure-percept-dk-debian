# SPDX-License-Identifier: MIT
"""Produce unsigned release metadata from local, inspected generic bundles."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from percept.bundles import read_manifest
from percept.build.pipeline import sha

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--version',required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('bundles',nargs='+',type=Path)
a=p.parse_args()
if a.output.exists():p.error('output already exists')
data={'schema':1,'version':a.version,'bundles':{}}
for path in a.bundles:
    manifest=read_manifest(path)
    cpu=manifest['cpu_profile']
    if cpu in data['bundles']:p.error('duplicate CPU variant')
    data['bundles'][cpu]={'file':path.name,'bytes':path.stat().st_size,'sha256':sha(path),
        'source_commit':manifest['source_commit'],'kernel_release':manifest['kernel_release'],
        'features':manifest['features'],'qualification':manifest['qualification']}
a.output.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
