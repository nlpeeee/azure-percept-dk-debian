# SPDX-License-Identifier: MIT
"""Build a personal flash image using the repository's rootless WSL primitives."""
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import urllib.request
import uuid
from .. import launcher_conf, profiles, redact, tomlmini
from . import gpt, overlay

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def private(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as f:f.write(text)
    path.chmod(0o600)
def download(item,dest):
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    if not item.get('sha256'):raise ValueError('download is not hash-pinned: '+item['id'])
    if not dest.exists():
        partial=dest.with_suffix(dest.suffix+'.part')
        with urllib.request.urlopen(item['url'],timeout=120) as src, partial.open('wb') as out:shutil.copyfileobj(src,out)
        if sha(partial)!=item['sha256']:
            partial.unlink();raise ValueError('download hash mismatch: '+item['id'])
        partial.replace(dest)
    if sha(dest)!=item['sha256']:raise ValueError('cached download hash mismatch: '+item['id'])
    return dest
def inputs(repo):return {x['id']:x for x in tomlmini.load_file(str(Path(repo)/'vendor/vendor-manifest.toml'))['input']}
def fetch(repo,recovery=None):
    repo=Path(repo);items=inputs(repo)
    source=Path(recovery).resolve() if recovery else download(items['ms-recovery-zip'],repo/'cache/downloads/recovery.zip')
    if sha(source)!=items['ms-recovery-zip']['sha256']:raise ValueError('recovery ZIP hash mismatch')
    subprocess.run(['bash',str(repo/'build/ms-extract.sh'),str(source)],cwd=repo,check=True)
    return repo/'cache/vendor/ms'
def grub(repo):
    return (Path(repo)/'launcher/grub.cfg.production').read_text().replace('linux /boot/vmlinuz-5.4.3-mariner','linux $efiroot/percept/stock-Image')
def build(repo,cfg):
    repo=Path(repo).resolve();cfg=copy.deepcopy(cfg)
    if cfg['os']['profile']!='debian-trixie' or cfg['os']['kernel']['source']!='distro':
        raise ValueError('image v1 supports the Debian trixie distro-kernel profile')
    if cfg['storage']['layout']=='factory':raise ValueError('USB images require the v2 64 MiB ESP layout')
    if subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip():
        raise ValueError('commit source changes before building an installer')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    name=cfg['board']['name'];stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=repo/'out'/name/stamp;out.mkdir(parents=True,exist_ok=False);out.chmod(0o700)
    work=out/'work';work.mkdir(mode=0o700)
    generated=overlay.credentials(cfg)
    if generated:private(out/'credentials.txt',''.join(user+': '+pw+'\n' for user,pw in generated))
    red=redact.Redactor(redact.collect_secrets(cfg)|{pw for _,pw in generated})
    log=out/'build.log'
    def run(argv):
        print('Build stage: '+Path(str(argv[0])).name+' '+(Path(str(argv[1])).name if len(argv)>1 else ''),flush=True)
        with log.open('a') as logfile:
            log.chmod(0o600)
            proc=subprocess.Popen([str(x) for x in argv],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=dict(os.environ,PYTHONPATH=str(repo/'src')))
            for line in proc.stdout:logfile.write(red(line));logfile.flush()
            if proc.wait():raise RuntimeError('build stage failed; inspect private log '+str(log))
    vendor=repo/'cache/vendor/ms';items=inputs(repo)
    for file in ('Image','pe100.dtb','System.map','config','fast-hab-fw.raw','emmc_full.txt','platform-prefix.bin','secondary-esp.img'):
        if not (vendor/file).is_file():raise ValueError('missing vendor input '+file+'; run percept fetch first')
    for file,key in [('Image','ms-stock-kernel'),('pe100.dtb','ms-pe100-dtb'),('fast-hab-fw.raw','ms-fast-hab-fw'),('emmc_full.txt','ms-emmc-script')]:
        if sha(vendor/file)!=items[key]['sha256']:raise ValueError('vendor hash mismatch: '+file)
    if not (repo/'out/kexecmod/SHA256SUMS').is_file():run(['bash',repo/'kexecmod/build.sh'])
    run(['bash',repo/'launcher/build.sh'])
    root_uuid=str(uuid.uuid4());serial=secrets.token_hex(4).upper();esp_uuid=serial[:4]+'-'+serial[4:]
    settings=work/'settings.json'
    private(settings,json.dumps({'config':cfg,'root_uuid':root_uuid,'esp_uuid':esp_uuid}))
    root=work/'rootfs'
    run(['bash',repo/'build/rootfs.sh',root,settings,repo/'profiles'/cfg['os']['profile']])
    release=(root/'percept-kernel-release').read_text().strip()
    prof=profiles.load_profile(str(repo/'profiles'/cfg['os']['profile']))
    selected=copy.deepcopy(cfg);selected['os']['kernel'].update(source='files',release=release)
    resolved=profiles.resolve(selected,prof,root_uuid)
    if resolved['problems']:raise ValueError('; '.join(resolved['problems']))
    values={}
    for line in (root/'boot'/('config-'+release)).read_text().splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            k,v=line.split('=',1);values[k[7:]]=v
    required=list(prof['contract']['config_required'])
    if cfg['os']['cpu_profile']!='unchanged':required+=prof['cpu_power']['config_required']
    missing=[k for k in required if values.get(k) not in ('y','m')]
    if missing:raise ValueError('kernel contract missing: '+','.join(missing))
    if values.get('ARM64_4K_PAGES')!='y':raise ValueError('standard 4 KiB arm64 kernel required')
    members=(root/'percept-initramfs-members').read_text()
    for module in ('imx2_wdt','sdhci-esdhc-imx','ext4'):
        if module.replace('-','_') not in members.replace('-','_'):
            raise ValueError('required initramfs module absent: '+module)
    kernel=(root/'boot'/('vmlinuz-'+release)).read_bytes()
    if kernel[56:60]!=b'ARMd':raise ValueError('target is not an uncompressed arm64 Image')
    if not (root/'boot'/('initrd.img-'+release)).is_file():raise ValueError('target initramfs missing')
    stage=work/'esp';(stage/'percept').mkdir(parents=True);(stage/'EFI/BOOT').mkdir(parents=True);(stage/'boot/grub2').mkdir(parents=True)
    for f in ('bootaa64.efi','grubaa64.efi'):shutil.copy2(vendor/'efi'/f,stage/'EFI/BOOT'/f)
    shutil.copy2(vendor/'Image',stage/'percept/stock-Image')
    shutil.copy2(repo/'out/launcher/launcher.cpio.gz',stage/'percept/launcher.cpio.gz')
    shutil.copy2(vendor/'pe100.dtb',stage/'pe100.dtb')
    normal='pe100.dtb'
    if 'usbc-extcon' in resolved['fixups']['esp-dtb']:
        run(['python3','-m','percept.build.strip_dtb_property',vendor/'pe100.dtb',stage/'pe100-usbc.dtb','--remove','/soc@0/usb@38100000:extcon'])
        normal='pe100-usbc.dtb'
    text=grub(repo)
    if normal=='pe100.dtb':text=text.replace('pe100-usbc.dtb','pe100.dtb')
    (stage/'boot/grub2/grub.cfg').write_text(text)
    (stage/'boot/grub2/grubenv').write_bytes(launcher_conf.grubenv(cfg['rescue']['grub_tries']))
    (stage/'percept/launcher.conf').write_text(launcher_conf.render(resolved,cfg,'v2'))
    (stage/'percept/failcount').write_bytes(launcher_conf.failcount())
    for f,data in launcher_conf.rescue_esp_files(cfg).items():(stage/'percept'/f).write_bytes(data)
    esp=work/'esp.img'
    with esp.open('wb') as f:f.truncate(64*1024*1024)
    run(['mkfs.vfat','-F','16','-i',serial,'-n','PERCEPT-EFI',esp])
    for p in sorted(stage.iterdir()):run(['mcopy','-s','-i',esp,p,'::'])
    run(['fsck.vfat','-n',esp])
    size=4096 if cfg['storage']['root_size']=='fill' else int(cfg['storage']['root_size'])
    root_image=work/'rootfs.img'
    run(['bash',repo/'build/pack-rootfs.sh',root,root_image,root_uuid,str(size)])
    disk=out/(name+'-PERSONAL.raw')
    layout=gpt.compose(disk,esp,vendor/'secondary-esp.img',root_image,vendor/'platform-prefix.bin')
    run(['sfdisk','--verify',disk])
    firmware=out/'fast-hab-fw.raw';shutil.copy2(vendor/'fast-hab-fw.raw',firmware)
    script=(vendor/'emmc_full.txt').read_text().replace('_flash.bin',firmware.name).replace('_image.raw',disk.name)
    flash=out/(name+'-PERSONAL.uuu');flash.write_text(script)
    manifest={'schema':1,'source_commit':commit,'kernel_release':release,'root_uuid':root_uuid,'esp_uuid':esp_uuid,
        'rootfs_packages':(root/'percept-package-versions').read_text().splitlines(),
        'kernel_sha256':hashlib.sha256(kernel).hexdigest(),
        'layout':layout,'cpu_profile':cfg['os']['cpu_profile'],'personal':True,'hardware_tested':False,
        'artifacts':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in (disk,firmware,flash)},
        'launcher_build':json.loads((repo/'out/launcher/build.manifest.json').read_text()),
        'module_build':json.loads((repo/'out/kexecmod/modules.manifest.json').read_text())}
    manifest_path=out/(name+'-PERSONAL.manifest.json');private(manifest_path,json.dumps(manifest,indent=2)+'\n')
    private(out/'SHA256SUMS',''.join(sha(p)+'  '+p.name+'\n' for p in (disk,firmware,flash,manifest_path)))
    settings.unlink()
    print('Personal installer built: '+str(out))
    return out
