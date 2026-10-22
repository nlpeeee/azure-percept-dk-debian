# SPDX-License-Identifier: MIT
"""Build native GUI/CLI candidate packages; never publish or contact a board."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import importlib.metadata

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from percept.build.pipeline import inputs, sha, download

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--uuu',type=Path,required=True,help='native uuu 1.5.243 executable')
p.add_argument('--uuu-sha256',required=True,help='expected reviewed native executable digest')
p.add_argument('--output',type=Path,default=ROOT/'out/application')
a=p.parse_args()
a.output=a.output.resolve()
a.uuu=a.uuu.resolve()
if platform.system() not in ('Windows','Linux') or platform.machine().lower() not in ('amd64','x86_64'):
    p.error('v1 packages support Windows/Linux x64')
if a.output.exists(): p.error('output already exists; choose a fresh directory')
if sha(a.uuu)!=a.uuu_sha256: p.error('uuu hash differs from the reviewed digest')
if platform.system()=='Windows' and a.uuu_sha256!=inputs(ROOT)['uuu-1.5.243']['sha256']:
    p.error('Windows uuu must match the pinned vendor manifest')
if platform.system()=='Linux' and a.uuu_sha256!=inputs(ROOT)['uuu-linux-1.5.243']['sha256']:
    p.error('Linux uuu must match the pinned vendor manifest')
a.output.mkdir(parents=True)
resources=a.output/'resources';resources.mkdir()
for name in ('profiles','vendor','release'):
    shutil.copytree(ROOT/name,resources/name)
# Exclude optional private/local manifests from shipped resource directories.
tools=resources/'tools';tools.mkdir()
tool=tools/('uuu.exe' if platform.system()=='Windows' else 'uuu')
shutil.copy2(a.uuu,tool);tool.chmod(0o755)
key=platform.system().lower()+'-'+platform.machine().lower()
if platform.system()=='Linux':
    listing=subprocess.check_output(['ldd',str(tool)],text=True)
    if 'not found' in listing:p.error('native uuu has missing shared libraries: '+listing)
    libs=tools/'lib';libs.mkdir()
    for line in listing.splitlines():
        words=line.strip().split()
        candidate=words[2] if len(words)>2 and words[1]=='=>' else ''
        if candidate.startswith('/') and Path(candidate).is_file():
            # Use the host loader/libc; bundle the native tool's other dependencies.
            if Path(candidate).name.startswith(('libc.so','libpthread.so','libm.so','libdl.so','librt.so')):continue
            shutil.copy2(candidate,libs/Path(candidate).name)
(resources/'release/tools.json').write_text(json.dumps({key:{'file':'tools/'+tool.name,
    'version':'1.5.243','sha256':sha(tool)}})+'\n',encoding='utf-8')
for gui,name in ((False,'percept'),(True,'PerceptInstaller')):
    entry=a.output/(name+'-entry.py')
    entry.write_text('from percept.cli import main\nraise SystemExit(main('+('["gui"]' if gui else '')+'))\n',encoding='utf-8')
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--name',name,
        '--paths',str(ROOT/'src'),'--collect-all','pyfatfs','--collect-all','fs',
        '--hidden-import','cryptography.hazmat.primitives.asymmetric.ed25519',
        '--hidden-import','tkinter','--hidden-import','tkinter.ttk',
        '--add-data',str(resources)+':percept-resources',
        '--distpath',str(a.output/'dist'),'--workpath',str(a.output/'pyinstaller-work'),
        '--specpath',str(a.output)]
    if gui: command+=['--windowed']
    subprocess.run(command+[str(entry)],check=True,cwd=ROOT)
for name in ('LICENSE','NOTICE.md','LICENSES'):
    src=ROOT/name;dst=a.output/'dist'/name
    if src.is_dir():shutil.copytree(src,dst)
    else:shutil.copy2(src,dst)
guide=(ROOT/'docs/portable-installer.md').read_text(encoding='utf-8')
guide=guide.replace('](install.md','](docs/install.md').replace('](build-wsl.md','](docs/build-wsl.md')
(a.output/'dist/INSTALL.md').write_text(guide,encoding='utf-8')
documentation=a.output/'dist/docs';documentation.mkdir()
for name in ('install.md','build-wsl.md','configuration.md'):
    shutil.copy2(ROOT/'docs'/name,documentation/name)
inventory=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True)
(a.output/'dist/python-dependencies.txt').write_text(inventory,encoding='utf-8')
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
(a.output/'dist/application-build.json').write_text(json.dumps({'schema':1,'source_commit':commit,
    'platform':key,'python':platform.python_version(),'uuu_version':'1.5.243','uuu_sha256':sha(tool),
    'qualification':{'native_smoke':'pending','clean_machine':'pending','hardware':'pending'}},indent=2)+'\n',encoding='utf-8')
third=a.output/'dist/third-party';third.mkdir()
for candidate in (Path(sys.base_prefix)/'LICENSE.txt', Path(sys.base_prefix)/'LICENSE',
                  Path('/usr/share/doc/python3.13/copyright')):
    if candidate.is_file():
        target=third/'Python';target.mkdir(exist_ok=True);shutil.copy2(candidate,target/candidate.name)
for distribution in importlib.metadata.distributions():
    for file in distribution.files or []:
        if any(word in str(file).lower() for word in ('license','copying','notice')) and not str(file).endswith('.py'):
            source=Path(distribution.locate_file(file))
            if source.is_file():
                target=third/distribution.metadata['Name']/Path(file).name
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
source=download(inputs(ROOT)['uuu-source-1.5.243'],ROOT/'cache/downloads/uuu-source-1.5.243.tar.gz')
shutil.copy2(source,third/'uuu-source-1.5.243.tar.gz')
shutil.copy2(ROOT/'release/uuu-NOTICE.md',third/'uuu-NOTICE.md')
archive=shutil.make_archive(str(a.output/('percept-'+platform.system().lower()+'-x64-candidate')),'zip',a.output/'dist')
Path(archive+'.sha256').write_text(sha(archive)+'  '+Path(archive).name+'\n',encoding='utf-8')
print('Local candidate: '+archive+'; clean-machine and hardware qualification still required')
