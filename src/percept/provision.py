# SPDX-License-Identifier: MIT
"""Early target-side provisioning. No network activity or package installation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from . import validate
from .build.overlay import apply, write

GATED = ('ssh.service', 'systemd-networkd.service', 'systemd-resolved.service',
         'systemd-timesyncd.service', 'bluetooth.service', 'percept-hostkeys.service',
         'percept-boot-ok.service', 'percept-firstboot-grow.service',
         'getty@.service', 'serial-getty@.service', 'wpa_supplicant@.service',
         'wpa_supplicant.service')


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as stream:
        stream.write(value); stream.flush(); os.fsync(stream.fileno())
    tmp.replace(path)
    if os.name != 'nt':
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)


def install_generic(root, cfg, root_uuid, esp_uuid, repo):
    """Build-time staging; never creates personal users or network settings."""
    import shutil
    root, repo = Path(root), Path(repo)
    write(root, 'etc/hostname', 'percept-unconfigured\n')
    write(root, 'etc/fstab', 'UUID='+root_uuid+' / ext4 errors=remount-ro,noatime 0 1\nUUID='+esp_uuid+' /boot/efi vfat umask=0077,nofail 0 2\n')
    (root/'boot/efi').mkdir(parents=True, exist_ok=True)
    write(root, 'etc/percept/bundle.json', json.dumps({'root_uuid': root_uuid, 'esp_uuid': esp_uuid}))
    destination = root/'usr/lib/percept/python/percept'
    shutil.copytree(repo/'src/percept', destination, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    assets = root/'usr/lib/percept/assets/target'
    assets.mkdir(parents=True, exist_ok=True)
    for name in ('percept-boot-ok', 'percept-wait-ssh', 'percept-firstboot-grow',
                 'percept-boot-ok.service', 'percept-hostkeys.service', 'percept-firstboot-grow.service'):
        shutil.copy2(repo/'target'/name, assets/name)
        if name.endswith('.service'):
            write(root, 'etc/systemd/system/'+name, (repo/'target'/name).read_text())
        else:
            write(root, 'usr/local/sbin/'+name, (repo/'target'/name).read_text(), 0o755)
    write(root, 'etc/systemd/system/ssh.service.d/10-hostkeys.conf',
          '[Unit]\nRequires=percept-hostkeys.service\nAfter=percept-hostkeys.service\n')
    write(root, 'usr/local/sbin/percept-provision',
          '#!/bin/sh\nexport PYTHONPATH=/usr/lib/percept/python\nexec /usr/bin/python3 -m percept.provision\n', 0o755)
    write(root, 'etc/systemd/system/percept-provision.service', (repo/'target/percept-provision.service').read_text())
    for unit in GATED:
        write(root, 'etc/systemd/system/'+unit+'.d/05-provision.conf',
              '[Unit]\nRequires=percept-provision.service\nAfter=percept-provision.service\n')
    for unit in ('percept-provision.service', 'ssh.service', 'systemd-networkd.service',
                 'systemd-resolved.service', 'serial-getty@ttymxc0.service',
                 'percept-hostkeys.service', 'percept-boot-ok.service', 'percept-firstboot-grow.service'):
        subprocess.run(['chroot', str(root), 'systemctl', 'enable', unit], check=True)
    subprocess.run(['chroot', str(root), 'usermod', '-L', 'root'], check=True)
    for key in (root/'etc/ssh').glob('ssh_host_*'): key.unlink()
    write(root, 'etc/machine-id', '')
    dbus = root/'var/lib/dbus/machine-id'
    if dbus.exists() or dbus.is_symlink(): dbus.unlink()


def provision(root=Path('/'), runner=apply):
    root = Path(root)
    state = root/'var/lib/percept/provision'
    payload = root/'boot/efi/percept/firstboot.json'
    if (state/'complete').is_file():
        payload.unlink(missing_ok=True)
        return
    if not payload.is_file() or payload.stat().st_size > 1024**2:
        raise ValueError('missing or oversized configuration; prepare the image again')
    raw = payload.read_bytes()
    data = json.loads(raw)
    if data.get('schema') != 1:
        raise ValueError('unsupported first-boot configuration')
    result = validate.validate(data['config'])
    if not result.ok:
        raise ValueError('invalid first-boot settings; validate the board configuration on your PC')
    cfg = result.config
    # All credentials must have been resolved on the PC, never generated again on retry.
    if any(u['password_mode'] == 'generate' for u in cfg['user']):
        raise ValueError('unresolved generated password')
    identity = json.loads((root/'etc/percept/bundle.json').read_text())
    digest = hashlib.sha256(raw).hexdigest()
    if (state/'started').exists() and (state/'started').read_text() != digest:
        raise ValueError('configuration changed during provisioning; prepare a fresh image')
    atomic(state/'started', digest)
    runner(root, cfg, identity['root_uuid'], identity['esp_uuid'],
           root/'usr/lib/percept/assets', firstboot=True)
    if root == Path('/'):
        subprocess.run(['hostname', cfg['board']['hostname']], check=True)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
    atomic(state/'complete', digest)
    payload.unlink()
    if root == Path('/') and cfg['network']['wifi']['enabled']:
        subprocess.run(['systemctl', '--no-block', 'start', 'wpa_supplicant@wlan0.service'], check=True)


if __name__ == '__main__':
    try:
        provision()
    except Exception:
        # Exceptions from subprocesses or payload parsers may contain credentials.
        print('Percept setup failed. Login/network services remain gated; use recovery and inspect local settings.', file=sys.stderr)
        sys.exit(1)
