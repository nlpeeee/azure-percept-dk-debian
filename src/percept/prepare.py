# SPDX-License-Identifier: MIT
"""Prepare personal artifacts using ordinary files: no WSL, mounts or chroot."""
import copy
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import threading
import time
import urllib.request

from . import bundles, config, launcher_conf, profiles, tomlmini, vendor_recipe
from .build import gpt, overlay
from .build.pipeline import inputs, sha
from .events import Reporter


def fetch_file(url, destination, digest, report, cancel=None, max_bytes=16*1024**3):
    destination = Path(destination); destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha(destination) != digest: raise ValueError('cached file hash mismatch: '+destination.name)
        report.emit('download', 'Using verified cache: '+destination.name)
        return destination
    if not url.startswith('https://'): raise ValueError('downloads require HTTPS')
    partial = destination.with_suffix(destination.suffix+'.part')
    try:
        with urllib.request.urlopen(url, timeout=120) as src, partial.open('wb') as dst:
            total = int(src.headers.get('Content-Length', '0')); current = 0; last = 0
            if total > max_bytes: raise ValueError('download exceeds size limit')
            while True:
                if cancel and cancel.is_set(): raise InterruptedError('preparation cancelled')
                block = src.read(1024**2)
                if not block: break
                current += len(block)
                if current > max_bytes: raise ValueError('download exceeds size limit')
                dst.write(block)
                if time.monotonic()-last >= 1:
                    report.emit('download', 'Downloading '+destination.name, current=current, total=total)
                    last = time.monotonic()
        if sha(partial) != digest: raise ValueError('download hash mismatch: '+destination.name)
        partial.replace(destination)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return destination


def small_download(url):
    if not url.startswith('https://'): raise ValueError('release URL must use HTTPS')
    with urllib.request.urlopen(url, timeout=60) as src:
        value = src.read(2*1024**2+1)
    if len(value) > 2*1024**2: raise ValueError('oversized release metadata')
    return value


def release_bundle(repo, version, cfg, report, cancel=None):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', version):
        raise ValueError('invalid release version')
    policy = json.loads((Path(repo)/'release/policy.json').read_text(encoding='utf-8'))
    if not policy['public_keys']:
        raise ValueError('no trusted release signing key is configured in this candidate application; use an explicitly trusted local build')
    base = policy['base_url'].rstrip('/')+'/'+version+'/'
    message = small_download(base+'release.json')
    signature = json.loads(small_download(base+'release.sig'))
    key = policy['public_keys'].get(signature['key_id'])
    if not key: raise ValueError('release uses an unknown signing key')
    bundles.verify_signature(message, signature['signature'], key)
    data = json.loads(message)
    if data.get('schema') != 1 or data.get('version') != version:
        raise ValueError('release version/format mismatch')
    record = data['bundles'][cfg['os']['cpu_profile']]
    name = record['file']
    if Path(name).name != name or '/' in name or '\\' in name or not name.endswith('.bundle.tar.gz'):
        raise ValueError('invalid release bundle name')
    return fetch_file(base+name, Path(repo)/'cache/releases'/version/name,
                      record['sha256'], report, cancel, record['bytes'])


def remove_extcon(data):
    """FDT_NOP the known USB-C extcon property, preserving all offsets."""
    value = bytearray(data)
    if len(value) < 40 or struct.unpack_from('>I', value)[0] != 0xd00dfeed:
        raise ValueError('invalid vendor device tree')
    _, total, offset, strings, _, _, _, _, strings_size, struct_size = struct.unpack_from('>10I', value)
    if total > len(value) or offset+struct_size > len(value) or strings+strings_size > len(value):
        raise ValueError('truncated device tree')
    stack = []; removed = 0; end = offset+struct_size
    while offset+4 <= end:
        start = offset; token = struct.unpack_from('>I', value, offset)[0]; offset += 4
        if token == 1:
            stop = value.index(0, offset, end)
            stack.append(bytes(value[offset:stop]).decode()); offset = (stop+4)&~3
        elif token == 2:
            if not stack: raise ValueError('invalid device tree nesting')
            stack.pop()
        elif token == 3:
            length, name_offset = struct.unpack_from('>II', value, offset); offset += 8
            if name_offset >= strings_size: raise ValueError('invalid FDT property name')
            name_end = value.index(0, strings+name_offset, strings+strings_size)
            name = bytes(value[strings+name_offset:name_end]).decode()
            offset = (offset+length+3)&~3
            if offset > end: raise ValueError('invalid FDT property length')
            if '/'.join(stack) == '/soc@0/usb@38100000' and name == 'extcon':
                value[start:offset] = struct.pack('>I', 4)*((offset-start)//4); removed += 1
        elif token == 9: break
        elif token != 4: raise ValueError('unsupported FDT token')
    if removed != 1: raise ValueError('expected exactly one USB-C extcon property')
    return bytes(value)


def make_esp(path, files, serial):
    from pyfatfs.PyFat import PyFat
    from pyfatfs.PyFatFS import PyFatFS
    with Path(path).open('xb') as dst: dst.truncate(64*1024**2)
    fat = PyFat()
    fat.mkfs(str(path), fat_type=PyFat.FAT_TYPE_FAT16, size=64*1024**2,
             label='PERCEPT-EFI', volume_id=int(serial.replace('-', ''), 16))
    fat.close()
    with PyFatFS(str(path)) as fs:
        for name, value in sorted(files.items()):
            parent = str(Path(name).parent).replace('\\', '/')
            if parent != '.': fs.makedirs(parent, recreate=True)
            with fs.openbin(name, 'w') as stream: stream.write(value)
        for name, value in files.items():
            with fs.openbin(name) as stream:
                if stream.read() != value: raise ValueError('ESP verification failed: '+name)


def prepare(repo, cfg, bundle=None, release=None, trust_local=False, recovery=None,
            output=None, report=None, cancel=None):
    report = report or Reporter(); repo = Path(repo); cfg = copy.deepcopy(cfg)
    def check_cancel():
        if cancel and cancel.is_set(): raise InterruptedError('preparation cancelled')
    if bool(bundle) == bool(release): raise ValueError('choose exactly one bundle or release')
    if bundle and not trust_local:
        raise ValueError('local bundles are unsigned: explicitly select --trust-local if you trust this build')
    check_cancel()
    if release: bundle = release_bundle(repo, release, cfg, report, cancel)
    report.emit('verify', 'Inspecting bundle capabilities and package inventory')
    manifest = bundles.read_manifest(bundle); bundles.compatible(cfg, manifest)
    report.emit('verify', 'Kernel %s; VPU %s; CPU %s; hardware tested: %s' % (
        manifest['kernel_release'], manifest['features']['vpu'], manifest['cpu_profile'], manifest['hardware_tested']))
    name = cfg['board']['name']
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', name): raise ValueError('invalid board name')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination = Path(output) if output else repo/'out'/name/stamp
    destination.parent.mkdir(parents=True, exist_ok=True)
    expanded = sum(r['bytes'] for r in manifest['artifacts'].values())
    if shutil.disk_usage(destination.parent).free < expanded*2+3*1024**3:
        raise ValueError('insufficient disk space for expanded bundle, vendor files and personal image')
    destination.mkdir(exist_ok=False)
    if __import__('os').name == 'nt':
        import os
        import subprocess
        user = os.environ.get('USERNAME')
        if not user: raise ValueError('cannot determine current Windows user for private output permissions')
        subprocess.run(['icacls', str(destination), '/inheritance:r', '/grant:r', user+':(OI)(CI)F'],
                       capture_output=True, check=True)
    else:
        destination.chmod(0o700)
    work = destination/'work'; work.mkdir()
    report.emit('unpack', 'Verifying and expanding generic bundle')
    bundles.unpack(bundle, work/'bundle'); check_cancel()
    base = work/'bundle'; pinned = inputs(repo)['ms-recovery-zip']
    source = Path(recovery) if recovery else fetch_file(pinned['url'], repo/'cache/downloads/recovery.zip', pinned['sha256'], report, cancel)
    report.emit('vendor', 'Verifying Microsoft recovery files; large ZIPs may take several minutes')
    vendor = vendor_recipe.extract(source, json.loads((base/'vendor-recipe.json').read_text()), work/'vendor', pinned)
    check_cancel()
    generated = overlay.credentials(cfg)
    cfg['rescue'].pop('password_mode', None)
    if generated:
        config.write_private(str(destination/'credentials.txt'), ''.join(user+': '+password+'\n' for user,password in generated))
    prof = tomlmini.load_file(str(base/'profile.toml'))
    selected = copy.deepcopy(cfg); selected['os']['kernel'].update(source='files', release=manifest['kernel_release'])
    resolved = profiles.resolve(selected, prof, manifest['root_uuid'])
    if resolved['problems']: raise ValueError('bundle kernel/profile contract is incompatible')
    files = {'EFI/BOOT/'+n: (vendor/n).read_bytes() for n in ('bootaa64.efi', 'grubaa64.efi')}
    files.update({'pe100.dtb':(vendor/'pe100.dtb').read_bytes(),
        'percept/stock-Image':(vendor/'Image').read_bytes(),
        'percept/launcher.cpio.gz':(base/'launcher.cpio.gz').read_bytes(),
        'percept/launcher.conf':launcher_conf.render(resolved,cfg,'v2').encode(),
        'percept/firstboot.json':json.dumps({'schema':1,'config':cfg}).encode(),
        'percept/failcount':launcher_conf.failcount(),
        'boot/grub2/grubenv':launcher_conf.grubenv(cfg['rescue']['grub_tries'])})
    for filename, value in launcher_conf.rescue_esp_files(cfg).items(): files['percept/'+filename] = value
    grub = (base/'grub.cfg').read_text()
    if 'usbc-extcon' in resolved['fixups']['esp-dtb']:
        files['pe100-usbc.dtb'] = remove_extcon(files['pe100.dtb'])
    else: grub = grub.replace('pe100-usbc.dtb','pe100.dtb')
    files['boot/grub2/grub.cfg'] = grub.encode()
    report.emit('compose', 'Creating EFI filesystem and personal disk image')
    esp = work/'esp.img'; make_esp(esp,files,manifest['esp_uuid']); check_cancel()
    disk = destination/(name+'-PERSONAL.raw')
    layout = gpt.compose(disk,esp,vendor/'secondary-esp.img',base/'rootfs.img',vendor/'platform-prefix.bin')
    firmware = destination/'fast-hab-fw.raw'; shutil.copy2(vendor/'fast-hab-fw.raw',firmware)
    script = destination/(name+'-PERSONAL.uuu')
    text = (vendor/'emmc_full.txt').read_text().replace('_flash.bin',firmware.name).replace('_image.raw',disk.name)
    if disk.name not in text or firmware.name not in text: raise ValueError('unsupported vendor flash script template')
    script.write_text(text, encoding='utf-8')
    report.emit('verify', 'Hashing completed artifacts; do not flash until this finishes')
    records = {p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in (disk,firmware,script)}
    check_cancel()
    personal = dict(manifest, kind='percept-personal', personal=True, artifacts=records, layout=layout,
                    base_bundle_sha256=sha(bundle), hardware_tested=False)
    # Remove redundant secret-bearing staging before publishing the completion marker.
    shutil.rmtree(work)
    path = destination/(name+'-PERSONAL.manifest.json')
    config.write_private(str(path.with_suffix('.json.part')), json.dumps(personal,indent=2)+'\n')
    path.with_suffix('.json.part').replace(path)
    config.write_private(str(destination/'SHA256SUMS'), ''.join(sha(p)+'  '+p.name+'\n' for p in (disk,firmware,script,path)))
    report.emit('complete','Personal installer ready: '+str(path))
    return path
