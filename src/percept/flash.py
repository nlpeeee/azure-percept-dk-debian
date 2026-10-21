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
    data,script=verify_manifest(manifest)
    if script.name!=board+'-PERSONAL.uuu':raise ValueError('selected board and image name differ')
    tool=Path(uuu) if uuu else download(inputs(repo)['uuu-1.5.243'],Path(repo)/'cache/downloads/uuu-1.5.243.exe')
    if not tool.is_file():raise ValueError('uuu executable not found')
    result=subprocess.run([str(tool),'-lsusb'],capture_output=True,text=True,check=True)
    count=len(connected_devices(result.stdout))
    if count!=1:raise ValueError('expected one Percept in USB recovery, found '+str(count))
    print('This replaces the selected Percept installation with '+script.name)
    if confirm('Type ERASE '+board+' to flash: ')!='ERASE '+board:raise ValueError('flash cancelled')
    return subprocess.run([str(tool),script.name],cwd=script.parent).returncode
