# SPDX-License-Identifier: MIT
"""Verify a personal image and invoke Windows uuu using its matching script."""
import json
from pathlib import Path
import re
import subprocess
from .build.pipeline import download, inputs, sha

def verify_manifest(path):
    path=Path(path).resolve()
    data=json.loads(path.read_text())
    if data.get('personal') is not True:raise ValueError('not a personal installer manifest')
    files={}
    for name,record in data['artifacts'].items():
        candidate=path.parent/name
        candidate.resolve().relative_to(path.parent)
        if sha(candidate)!=record['sha256']:raise ValueError('artifact hash mismatch: '+name)
        files[name]=candidate
    scripts=[p for p in files.values() if p.suffix=='.uuu']
    if len(scripts)!=1:raise ValueError('manifest must contain exactly one flash script')
    return data,scripts[0]

def connected_devices(text):
    return [line for line in text.splitlines() if re.search(r'0x(?:1fc9|0525|18d1)\b',line,re.I)]

def flash(repo,manifest,board,uuu=None,confirm=input):
    print('Checking installer hashes; large images may take a few minutes.', flush=True)
    data,script=verify_manifest(manifest)
    if script.name!=board+'-PERSONAL.uuu':raise ValueError('selected board and image name differ')
    tool=Path(uuu) if uuu else download(inputs(repo)['uuu-1.5.243'],Path(repo)/'cache/downloads/uuu-1.5.243.exe')
    if not tool.is_file():raise ValueError('uuu executable not found')
    print('USB recovery: power OFF; set the internal four-way DIP block from normal')
    print('1001 (up-down-down-up) to 0101 (down-up-down-up), using the official photo')
    print('orientation linked in docs/install.md. Connect USB-C to this PC, then power ON.')
    print('The board must already be in USB recovery before detection; there is no established external recovery button.')
    result=subprocess.run([str(tool),'-lsusb'],capture_output=True,text=True,check=True)
    count=len(connected_devices(result.stdout))
    if count!=1:
        raise ValueError('expected one Percept in USB recovery, found '+str(count)+
            '. Check power, DIP orientation and a data-capable USB-C cable; disconnect other recovery devices, then rerun. Nothing was flashed.')
    print('This replaces the selected Percept installation with '+script.name)
    if confirm('Type ERASE '+board+' to flash: ')!='ERASE '+board:raise ValueError('flash cancelled')
    print('Flashing eMMC. Keep power and USB connected until uuu finishes.', flush=True)
    status = subprocess.run([str(tool),script.name],cwd=script.parent).returncode
    if status == 0:
        print('Flash completed. Power OFF, restore DIP 1001 (up-down-down-up), then power ON.')
        print('First boot expands storage and generates host keys. Follow docs/install.md for login and checks.')
    else:
        print('uuu failed (exit %s). Keep the output for diagnosis; do not assume the image is installed.' % status)
        print('Check connections and use the original Microsoft factory restoration package if needed. See docs/install.md.')
    return status
