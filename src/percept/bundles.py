# SPDX-License-Identifier: MIT
"""Versioned, bounded bundle loading, compatibility and release signatures."""
import base64
import hashlib
import json
from pathlib import Path
import tarfile
import re
import uuid

from .build.pipeline import sha
from .packages import check_inventory

SCHEMA = 1
REQUIRED = {'rootfs.img', 'launcher.cpio.gz', 'profile.toml', 'grub.cfg', 'vendor-recipe.json'}
MAX_EXPANDED = 32 * 1024**3


def validate_manifest(data):
    if not isinstance(data, dict): raise ValueError('invalid bundle manifest')
    if data.get('schema') != SCHEMA or data.get('kind') != 'percept-bundle':
        raise ValueError('unsupported Percept bundle format')
    if data.get('personal') is not False:
        raise ValueError('bundle must be generic, without personal configuration')
    artifacts = data.get('artifacts', {})
    if set(artifacts) != REQUIRED:
        raise ValueError('bundle artifact list is not the supported allowlist')
    total = 0
    for record in artifacts.values():
        size = record['bytes']
        digest = record['sha256']
        if not isinstance(size, int) or size <= 0 or len(digest) != 64:
            raise ValueError('invalid bundle artifact record')
        int(digest, 16)
        total += size
    if total > MAX_EXPANDED:
        raise ValueError('bundle exceeds maximum expanded size')
    if data.get('cpu_profile') not in ('unchanged', 'rated', 'oc1500'):
        raise ValueError('unsupported CPU variant')
    if data.get('profile') != 'debian-trixie' or not re.fullmatch(r'6\.12\.[A-Za-z0-9.+_-]+', data.get('kernel_release','')):
        raise ValueError('unsupported bundle kernel or OS profile')
    uuid.UUID(data['root_uuid'])
    if not re.fullmatch(r'[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}',data['esp_uuid']):
        raise ValueError('invalid ESP identity')
    if not isinstance(data.get('hardware_tested'), bool) or not isinstance(data.get('features'), dict):
        raise ValueError('invalid bundle capabilities or qualification status')
    if set(data['features']) != {'gpu','vpu','usb_c_host','camera','upper_ram','thermal'} or any(type(v) is not bool for v in data['features'].values()):
        raise ValueError('invalid bundle feature declarations')
    check_inventory(data['rootfs_packages'], data['features'].get('vpu', True))
    return data


def read_manifest(path):
    with tarfile.open(path, 'r:*') as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)) or set(names) != REQUIRED | {'bundle.json'}:
            raise ValueError('unexpected or duplicate bundle members')
        if any(not m.isfile() for m in members):
            raise ValueError('links and special files are forbidden in bundles')
        entry = archive.getmember('bundle.json')
        if entry.size > 2 * 1024**2:
            raise ValueError('oversized bundle manifest')
        data = validate_manifest(json.load(archive.extractfile(entry)))
        for name, record in data['artifacts'].items():
            if archive.getmember(name).size != record['bytes']:
                raise ValueError('bundle size mismatch: ' + name)
        return data


def unpack(path, destination):
    """Extract only regular allowlisted files; never use tar.extractall."""
    data = read_manifest(path)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(path, 'r:*') as archive:
        for name in sorted(REQUIRED):
            target = destination/name
            digest = hashlib.sha256()
            remaining = data['artifacts'][name]['bytes']
            with archive.extractfile(name) as src, target.open('xb') as dst:
                while remaining:
                    block = src.read(min(1024**2, remaining))
                    if not block:
                        raise ValueError('truncated bundle: ' + name)
                    dst.write(block); digest.update(block); remaining -= len(block)
            if digest.hexdigest() != data['artifacts'][name]['sha256']:
                raise ValueError('bundle hash mismatch: ' + name)
    return data


def compatible(cfg, manifest):
    os_cfg = cfg['os']
    if os_cfg['profile'] != manifest['profile'] or os_cfg['cpu_profile'] != manifest['cpu_profile']:
        raise ValueError('select a bundle matching the OS and CPU profile')
    if os_cfg['kernel']['source'] != 'distro' or os_cfg['kernel'].get('cmdline_extra'):
        raise ValueError('custom kernel settings require a source build')
    if os_cfg.get('mirror') or os_cfg['packages']['extra']:
        raise ValueError('mirror and extra package settings require a source build')
    for name, enabled in os_cfg['features'].items():
        if enabled is not None and enabled != manifest['features'].get(name, False):
            raise ValueError('bundle feature differs: ' + name + '; use a matching source build')
    if cfg['storage']['layout'] == 'factory' or cfg['storage']['root_size'] != 'fill' or cfg['storage'].get('esp_size_mib') not in (None, 64):
        raise ValueError('portable bundles require the v2 layout, 64 MiB ESP and root_size=fill')
    if cfg['install']['method'] != 'uuu':
        raise ValueError('portable preparation supports USB installation only')


def verify_signature(message, signature, key):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(key, validate=True)).verify(
            base64.b64decode(signature, validate=True), message)
    except Exception:
        raise ValueError('release signature verification failed') from None


def write_bundle(folder, manifest, output):
    folder, output = Path(folder), Path(output)
    manifest['artifacts'] = {name: {'bytes': (folder/name).stat().st_size,
                                  'sha256': sha(folder/name)} for name in sorted(REQUIRED)}
    validate_manifest(manifest)
    (folder/'bundle.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    partial = output.with_suffix(output.suffix+'.part')
    with tarfile.open(partial, 'w:gz', format=tarfile.PAX_FORMAT) as archive:
        for name in sorted(REQUIRED | {'bundle.json'}):
            info = archive.gettarinfo(str(folder/name), arcname=name)
            info.uid = info.gid = 0; info.uname = info.gname = ''; info.mode = 0o644; info.mtime = 0
            with (folder/name).open('rb') as src:
                archive.addfile(info, src)
    if output.exists():
        raise ValueError('bundle output already exists')
    partial.replace(output)
