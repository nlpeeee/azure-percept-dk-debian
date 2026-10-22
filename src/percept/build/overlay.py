# SPDX-License-Identifier: MIT
"""Personalize a fresh target root within the build's mapped-user namespace."""
import hashlib
from pathlib import Path
import secrets
import subprocess
from .. import sha512crypt
def write(root,name,text,mode=0o644):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(text,encoding='utf-8');p.chmod(mode)
def credentials(cfg):
    plain=[]
    for user in cfg['user']:
        if user['password_mode']=='generate':
            password=secrets.token_urlsafe(18)
            user['password_hash']=sha512crypt.crypt(password);user['password_mode']='hash'
            plain.append((user['name'],password))
    rescue=cfg['rescue']
    if rescue['password_auth'] and not rescue.get('password_hash'):
        rescue['password_hash']=cfg['user'][0]['password_hash']
        first=next((pw for user,pw in plain if user==cfg['user'][0]['name']),None)
        if first:plain.append(('rescue:'+rescue.get('username','root'),first))
    return plain
def apply(root,cfg,root_uuid,esp_uuid,repo,firstboot=False):
    root,repo=Path(root),Path(repo)
    def ch(*args):subprocess.run(['chroot',str(root),*args],check=True,stdout=subprocess.DEVNULL)
    b=cfg['board'];ssh=cfg['ssh']
    write(root,'etc/hostname',b['hostname']+'\n')
    write(root,'etc/hosts','127.0.0.1 localhost\n127.0.1.1 '+b['hostname']+'\n::1 localhost ip6-localhost ip6-loopback\n')
    write(root,'etc/timezone',b['timezone']+'\n')
    if not (root/'usr/share/zoneinfo'/b['timezone']).is_file():raise ValueError('timezone unavailable in target')
    localtime=root/'etc/localtime'
    if localtime.exists() or localtime.is_symlink():localtime.unlink()
    localtime.symlink_to('../usr/share/zoneinfo/'+b['timezone'])
    write(root,'etc/default/locale','LANG='+b['locale']+'\n')
    write(root,'etc/locale.gen',b['locale']+' UTF-8\n' if b['locale']!='C.UTF-8' else '');ch('locale-gen')
    for u in cfg['user']:
        exists = subprocess.run(['chroot',str(root),'getent','passwd',u['name']], stdout=subprocess.DEVNULL).returncode == 0
        if not exists:
            ch('useradd','-m','-s','/bin/bash','-G',','.join(u['groups']),u['name'])
        elif firstboot:
            ch('usermod','-s','/bin/bash','-G',','.join(u['groups']),u['name'])
        else:
            raise ValueError('user already exists in fresh build')
        if u.get('password_hash'):
            subprocess.run(['chroot',str(root),'chpasswd','-e'],input=u['name']+':'+u['password_hash']+'\n',text=True,check=True)
        else:ch('usermod','-L',u['name'])
        home='home/'+u['name']
        write(root,home+'/.ssh/authorized_keys','\n'.join(u['authorized_keys'])+'\n',0o600)
        (root/home/'.ssh').chmod(0o700)
        ch('chown','-R',u['name']+':'+u['name'],'/'+home+'/.ssh')
        if u['sudo']!='none':
            auth='NOPASSWD: ' if u['sudo']=='nopasswd' else ''
            write(root,'etc/sudoers.d/percept-'+u['name'],u['name']+' ALL=(ALL:ALL) '+auth+'ALL\n',0o440)
    ch('usermod','-L','root')
    if ssh['root_login']=='key-only':
        write(root,'root/.ssh/authorized_keys','\n'.join(cfg['user'][0]['authorized_keys'])+'\n',0o600)
        (root/'root/.ssh').chmod(0o700)
    write(root,'etc/ssh/sshd_config.d/10-percept.conf',
        'Port %d\nPasswordAuthentication %s\nKbdInteractiveAuthentication no\nPermitRootLogin %s\n' %
        (ssh['port'],'yes' if ssh['password_auth'] else 'no','prohibit-password' if ssh['root_login']=='key-only' else 'no'))
    write(root,'etc/fstab','UUID='+root_uuid+' / ext4 errors=remount-ro,noatime 0 1\nUUID='+esp_uuid+' /boot/efi vfat umask=0077,nofail 0 2\n')
    (root/'boot/efi').mkdir(parents=True,exist_ok=True)
    e=cfg['network']['ethernet'];net='[Match]\nName=eth* en*\n\n[Network]\n'
    if e['mode']=='dhcp':net+='DHCP=yes\n'
    else:
        net+='Address=%s/%s\nGateway=%s\n'%(e['address'],e['prefix'],e['gateway'])
        net+=''.join('DNS='+x+'\n' for x in e['dns'])
        if e.get('domain'):net+='Domains='+e['domain']+'\n'
    if e['ipv6']=='off':net+='IPv6AcceptRA=no\nLinkLocalAddressing=ipv4\n'
    write(root,'etc/systemd/network/20-wired.network',net)
    wifi=cfg['network']['wifi']
    if wifi['enabled']:
        q=lambda s:'"'+s.replace('\\','\\\\').replace('"','\\"')+'"'
        text='country='+wifi['country']+'\nctrl_interface=DIR=/run/wpa_supplicant GROUP=netdev\nnetwork={\n    ssid='+q(wifi['ssid'])+'\n'
        if wifi['security']=='open':text+='    key_mgmt=NONE\n'
        elif wifi['security']=='wpa3':text+='    key_mgmt=SAE\n    ieee80211w=2\n    sae_password='+q(wifi['psk'])+'\n'
        else:
            psk=wifi['psk'] if len(wifi['psk'])==64 else hashlib.pbkdf2_hmac('sha1',wifi['psk'].encode(),wifi['ssid'].encode(),4096,32).hex()
            text+='    key_mgmt=WPA-PSK\n    psk='+psk+'\n'
        if wifi['hidden']:text+='    scan_ssid=1\n'
        write(root,'etc/wpa_supplicant/wpa_supplicant-wlan0.conf',text+'}\n',0o600)
        write(root,'etc/systemd/network/30-wireless.network','[Match]\nName=wlan0\n[Network]\nDHCP=yes\n')
        ch('systemctl','enable','wpa_supplicant@wlan0.service')
    write(root,'etc/systemd/system.conf.d/10-percept-watchdog.conf','[Manager]\nRuntimeWatchdogSec=60\n')
    write(root,'etc/systemd/journald.conf.d/10-percept.conf','[Journal]\nSystemMaxUse=50M\n')
    write(root,'etc/percept/ssh-port',str(ssh['port'])+'\n')
    for src,dst in [('percept-boot-ok','usr/local/sbin/percept-boot-ok'),('percept-wait-ssh','usr/local/sbin/percept-wait-ssh'),('percept-firstboot-grow','usr/local/sbin/percept-firstboot-grow')]:
        write(root,dst,(repo/'target'/src).read_text(),0o755)
    for service in ['percept-boot-ok.service','percept-hostkeys.service','percept-firstboot-grow.service']:
        write(root,'etc/systemd/system/'+service,(repo/'target'/service).read_text())
    write(root,'etc/systemd/system/ssh.service.d/10-hostkeys.conf','[Unit]\nRequires=percept-hostkeys.service\nAfter=percept-hostkeys.service\n')
    for service in ['ssh','systemd-networkd','systemd-resolved','systemd-timesyncd','bluetooth','serial-getty@ttymxc0','percept-hostkeys','percept-boot-ok']:
        ch('systemctl','enable',service)
    ch('systemctl','mask','systemd-networkd-wait-online.service')
    if cfg['storage']['root_size']=='fill':ch('systemctl','enable','percept-firstboot-grow.service')
    resolver=root/'etc/resolv.conf'
    if resolver.exists() or resolver.is_symlink():resolver.unlink()
    resolver.symlink_to('/run/systemd/resolve/stub-resolv.conf')
    if firstboot:
        return  # Preserve the identity established during this boot and on retries.
    for p in (root/'etc/ssh').glob('ssh_host_*'):p.unlink()
    write(root,'etc/machine-id','')
    dbus=root/'var/lib/dbus/machine-id'
    if dbus.exists() or dbus.is_symlink():dbus.unlink()
    ch('visudo','-cf','/etc/sudoers')
