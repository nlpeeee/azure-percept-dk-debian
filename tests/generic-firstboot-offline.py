# SPDX-License-Identifier: MIT
"""Destructive integration test ONLY on a disposable copy of a generic root.

Run inside the build's private mapped-user/mount namespaces. Never use a live
root or a personal root. Mount private /dev and /proc in the copy first.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from percept import provision, sha512crypt, validate
from percept.build.overlay import apply

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--disposable-root',type=Path,required=True)
a=p.parse_args();root=a.disposable_root.resolve()
if root==Path('/') or not (root/'etc/percept/bundle.json').is_file():p.error('need a disposable generic root copy')
if (root/'var/lib/percept/provision').exists():p.error('root is already provisioned or partially provisioned')
accounts=(root/'etc/passwd').read_text().splitlines()
if any(int(line.split(':')[2])>=1000 and int(line.split(':')[2])<65534 for line in accounts):p.error('root contains personal users')
cfg=validate.validate({'schema':1,'board':{'name':'offline-check','hostname':'offline-check'},
    'user':[{'name':'smokeuser','password_hash':sha512crypt.crypt('synthetic-test-password')}],
    'ssh':{'password_auth':True},'rescue':{'username':'rescueadmin','password_auth':True},
    'network':{'ethernet':{'mode':'dhcp'},'wifi':{'enabled':True,'ssid':'synthetic-network',
        'psk':'synthetic-network-password','country':'GB'}}})
assert cfg.ok,cfg.errors
payload=root/'boot/efi/percept/firstboot.json';payload.parent.mkdir(parents=True,exist_ok=True)
payload.write_text(json.dumps({'schema':1,'config':cfg.config}))
machine='0123456789abcdef0123456789abcdef\n';(root/'etc/machine-id').write_text(machine)
identity=root/'etc/ssh/ssh_host_synthetic';identity.write_text('synthetic retry identity')
def interrupted(*args,**kwargs):
    apply(*args,**kwargs)
    raise RuntimeError('simulated interruption before completion marker')
try:provision.provision(root,interrupted)
except RuntimeError:pass
else:raise AssertionError('interruption was not exercised')
assert not (root/'var/lib/percept/provision/complete').exists()
provision.provision(root)
assert not payload.exists()
assert (root/'etc/hostname').read_text()=='offline-check\n'
assert (root/'etc/machine-id').read_text()==machine
assert identity.read_text()=='synthetic retry identity'
assert sum(line.startswith('smokeuser:') for line in (root/'etc/passwd').read_text().splitlines())==1
assert (root/'home/smokeuser/.ssh').stat().st_mode&0o777==0o700
assert (root/'home/smokeuser/.ssh/authorized_keys').stat().st_mode&0o777==0o600
assert 'PasswordAuthentication yes' in (root/'etc/ssh/sshd_config.d/10-percept.conf').read_text()
assert 'DHCP=yes' in (root/'etc/systemd/network/20-wired.network').read_text()
assert 'synthetic-network-password' not in (root/'etc/wpa_supplicant/wpa_supplicant-wlan0.conf').read_text()
provision.provision(root,lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('must not reapply')))
print('Real ARM64 root: interrupted provisioning, existing-user retry, network/password settings and identity preservation passed')
