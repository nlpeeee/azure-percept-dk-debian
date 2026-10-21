#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record exact build inputs, source revision, outputs and builder packages."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def record(path):
    return {"name":path.name,"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--kind',required=True)
    p.add_argument('--source-commit',required=True)
    p.add_argument('--artifact',action='append',default=[],type=Path)
    p.add_argument('--input',action='append',default=[],type=Path)
    a=p.parse_args()
    packages=subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}=${Version}\n'],text=True).splitlines()
    data={'schema':1,'kind':a.kind,'source_commit':a.source_commit,'artifacts':[record(x) for x in a.artifact],
          'inputs':[record(x) for x in a.input],'builder_packages':sorted(packages)}
    a.output.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
if __name__=='__main__': main()
