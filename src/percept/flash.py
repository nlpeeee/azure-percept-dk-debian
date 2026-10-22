# SPDX-License-Identifier: MIT
"""Verify a personal image and invoke Windows uuu using its matching script."""
import json
import os
import platform
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

def resolve_tool(repo, uuu=None):
    if uuu:
        tool = Path(uuu).resolve()
    else:
        record_path = Path(repo)/'release/tools.json'
        if record_path.is_file():
            key = platform.system().lower()+'-'+platform.machine().lower()
            record = json.loads(record_path.read_text())[key]
            tool = Path(repo)/record['file']
            tool.resolve().relative_to(Path(repo).resolve())
            if sha(tool) != record['sha256']: raise ValueError('bundled uuu hash mismatch')
        elif os.name == 'nt':
            tool = download(inputs(repo)['uuu-1.5.243'],Path(repo)/'cache/downloads/uuu-1.5.243.exe')
        else:
            raise ValueError('native uuu is not bundled in this source checkout; pass --uuu PATH. Check Linux USB permissions/udev rules if detection is denied.')
    if not tool.is_file(): raise ValueError('uuu executable not found')
    return tool


def flash(repo,manifest,board,uuu=None,confirm=input,report=None):
    def out(message, **kwargs):
        if report: report.emit('flash', message)
        else: print(message, **kwargs)
    out('Checking installer hashes; large images may take a few minutes.', flush=True)
    data,script=verify_manifest(manifest)
    if script.name!=board+'-PERSONAL.uuu':raise ValueError('selected board and image name differ')
    tool=resolve_tool(repo,uuu)
    environment = os.environ.copy()
    if os.name != 'nt':
        inherited = environment.get('LD_LIBRARY_PATH_ORIG') if getattr(__import__('sys'), 'frozen', False) else environment.get('LD_LIBRARY_PATH')
        environment['LD_LIBRARY_PATH'] = str(tool.parent/'lib') + (':'+inherited if inherited else '')
    out('USB recovery: power OFF; set the internal four-way DIP block from normal')
    out('1001 (up-down-down-up) to 0101 (down-up-down-up), using the official photo')
    out('orientation linked in docs/install.md. Connect USB-C to this PC, then power ON.')
    out('The board must already be in USB recovery before detection; there is no established external recovery button.')
    result=subprocess.run([str(tool),'-lsusb'],capture_output=True,text=True,env=environment)
    if result.returncode:
        raise ValueError('USB detection failed. On Windows check the USB driver; on Linux check udev permissions. No flash was started.')
    count=len(connected_devices(result.stdout))
    if count!=1:
        raise ValueError('expected one Percept in USB recovery, found '+str(count)+
            '. Check power, DIP orientation and a data-capable USB-C cable; disconnect other recovery devices, then rerun. Nothing was flashed.')
    out('This replaces the selected Percept installation with '+script.name)
    if confirm('Type ERASE '+board+' to flash: ')!='ERASE '+board:raise ValueError('flash cancelled')
    out('Flashing eMMC. Keep power and USB connected until uuu finishes.', flush=True)
    if report:
        proc = subprocess.Popen([str(tool),script.name],cwd=script.parent,
                                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace',env=environment)
        for line in proc.stdout:
            out(line.rstrip())
        status = proc.wait()
    else:
        status = subprocess.run([str(tool),script.name],cwd=script.parent,env=environment).returncode
    if status == 0:
        out('Flash completed. Power OFF, restore DIP 1001 (up-down-down-up), then power ON.')
        out('First boot expands storage and generates host keys. Follow docs/install.md for login and checks.')
    else:
        out('uuu failed (exit %s). Keep the output for diagnosis; do not assume the image is installed.' % status)
        out('Check connections and use the original Microsoft factory restoration package if needed. See docs/install.md.')
    return status
