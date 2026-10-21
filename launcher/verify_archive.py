#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check launcher archive members, permissions, ELF interpreters and generic identity."""
import argparse
import gzip
import json
from pathlib import Path
import stat
from mkinitramfs import elf_machine
from replace_initramfs_member import parse

def verify(blob,no_modules=False,allow_keys=False):
    entries=parse(gzip.decompress(blob))
    members={name:(fields,data) for name,fields,data in entries if name!='TRAILER!!!'}
    if len(members)!=len(entries)-1:raise ValueError('duplicate archive member')
    required={'init':0o755,'bin/busybox':0o755,'sbin/kexec':0o755,
        'usr/sbin/dropbear':0o755,'usr/bin/dropbearkey':0o755,'usr/sbin/mke2fs':0o755,
        'usr/bin/tar':0o755,'usr/bin/gzip':0o755,'usr/bin/zstd':0o755,
        'lib/percept/capture.so':0o755,'lib/percept/percept-config.sh':0o644,
        'lib/percept/udhcpc.script':0o755,'bin/udp_log_sender':0o755}
    for kind in ('upper','thermal','media','cpu','pmic'):required['bin/percept-fdt-'+kind]=0o755
    if not no_modules:required.update({'lib/percept/arch.ko':0o444,'lib/percept/core.ko':0o444})
    for name,mode in required.items():
        if name not in members:raise ValueError('missing '+name)
        fields,data=members[name]
        if not stat.S_ISREG(fields[1]) or stat.S_IMODE(fields[1])!=mode:raise ValueError('wrong mode '+name)
    for name,(fields,data) in members.items():
        if fields[2:4]!=[0,0]:raise ValueError('non-root archive owner: '+name)
        if 'ssh_host_' in name or ('dropbear_' in name and name.endswith('_host_key')):raise ValueError('embedded host identity')
        if name.endswith('/authorized_keys') and not allow_keys:raise ValueError('embedded generic rescue keys')
        if data.startswith(b'\x7fELF'):
            if elf_machine(data)!=183:raise ValueError('non-arm64 ELF: '+name)
            import struct
            offset=struct.unpack_from('<Q',data,32)[0]
            size,count=struct.unpack_from('<HH',data,54)
            for n in range(count):
                p=offset+n*size
                if struct.unpack_from('<I',data,p)[0]==3:
                    start=struct.unpack_from('<Q',data,p+8)[0]
                    length=struct.unpack_from('<Q',data,p+32)[0]
                    interp=data[start:start+length].rstrip(b'\0').decode().lstrip('/')
                    if interp not in members:raise ValueError('missing ELF interpreter '+interp)
    if 'bin/sh' not in members or members['bin/sh'][1]!=b'busybox':raise ValueError('invalid shell link')
    console=members.get('dev/console')
    if not console or not stat.S_ISCHR(console[0][1]) or console[0][9:11]!=[5,1]:raise ValueError('invalid console node')
    return {'result':'passed','members':len(members),'module_pair_present':not no_modules,'generic':not allow_keys,'checked_permissions':len(required)}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    p.add_argument('--no-modules',action='store_true')
    p.add_argument('--allow-authorized-keys',action='store_true')
    a=p.parse_args()
    print(json.dumps(verify(a.archive.read_bytes(),a.no_modules,a.allow_authorized_keys),indent=2))
