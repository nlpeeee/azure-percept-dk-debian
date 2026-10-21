# SPDX-License-Identifier: MIT
"""Disk-format, password recovery and DT contracts; no board access."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
import helpers
from percept import launcher_conf, sha512crypt, validate
from percept.build import gpt, overlay

class PasswordRecovery(unittest.TestCase):
    def test_password_only_custom_recovery_username(self):
        c=helpers.minimal_cfg()
        c['user'][0].update(authorized_keys=[],password_mode='generate')
        c['ssh']={'password_auth':True}
        c['rescue']={'username':'rescueadmin','password_auth':True}
        res=validate.validate(c)
        self.assertTrue(res.ok,res.errors)
        generated=overlay.credentials(res.config)
        self.assertEqual(len(generated),2)
        self.assertTrue(sha512crypt.verify(generated[0][1],res.config['user'][0]['password_hash']))
        files=launcher_conf.rescue_esp_files(res.config)
        self.assertEqual(files['rescue_username'],b'rescueadmin\n')
        self.assertEqual(files['rescue_password_hash'].decode().strip(),res.config['user'][0]['password_hash'])
        self.assertNotIn('authorized_keys',files)
    def test_invalid_recovery_username_rejected(self):
        c=helpers.minimal_cfg();c['rescue']={'username':'bad:name'}
        self.assertFalse(validate.validate(c).ok)

class DiskImage(unittest.TestCase):
    def test_gpt_headers_crc_backup_and_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,size,mark in [('esp',64*1024*1024,b'ESP'),('secondary',22528*512,b'SECOND'),('rootfs',1024*1024,b'ROOT')]:
                with (root/name).open('wb') as f:f.write(mark);f.truncate(size)
            spec=gpt.compose(root/'disk.img',root/'esp',root/'secondary',root/'rootfs',None)
            with (root/'disk.img').open('rb') as f:
                self.assertEqual(f.read(512)[510:],b'\x55\xaa')
                primary=f.read(512)
                f.seek(-512,2);backup=f.read(512)
                for data in (primary,backup):
                    self.assertEqual(data[:8],b'EFI PART')
                    head=bytearray(data[:92]);expected=struct.unpack_from('<I',head,16)[0];head[16:20]=bytes(4)
                    self.assertEqual(zlib.crc32(head),expected)
                self.assertEqual(struct.unpack_from('<Q',primary,32)[0],spec['sectors']-1)
                f.seek(1024);entries=f.read(128*128)
                self.assertEqual(zlib.crc32(entries),struct.unpack_from('<I',primary,88)[0])
                f.seek(-33*512,2);self.assertEqual(f.read(128*128),entries)
                for part,mark in zip(spec['partitions'],(b'ESP',b'SECOND',b'ROOT')):
                    f.seek(part['start']*512);self.assertEqual(f.read(len(mark)),mark)
            if shutil.which('sfdisk'):
                parsed=json.loads(subprocess.check_output(['sfdisk','-J',str(root/'disk.img')]))['partitiontable']['partitions']
                self.assertEqual(len(parsed),3)
                self.assertEqual(parsed[0]['size'],64*2048)
                self.assertEqual(parsed[2]['start'],spec['partitions'][2]['start'])
    def test_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'existing';p.write_text('keep')
            with self.assertRaises(ValueError):gpt.compose(p,p,p,p,None)
            self.assertEqual(p.read_text(),'keep')

class UsbDtb(unittest.TestCase):
    def test_relocated_property_tool_is_self_contained(self):
        spec=importlib.util.spec_from_file_location('strip',Path(helpers.ROOT)/'src/percept/build/strip_dtb_property.py')
        tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
        def node(name):return struct.pack('>I',1)+(name.encode()+b'\0').ljust((len(name)+4)//4*4,b'\0')
        def prop(offset,value):return struct.pack('>III',3,len(value),offset)+value
        end=struct.pack('>I',2)
        body=node('')+node('soc@0')+node('usb@38100000')+prop(0,struct.pack('>I',73))+prop(7,struct.pack('>I',9))+end*3+struct.pack('>I',9)
        strings=b'extcon\0other\0';start=56
        blob=struct.pack('>10I',0xd00dfeed,start+len(body)+len(strings),start,start+len(body),40,17,16,0,len(strings),len(body))+bytes(16)+body+strings
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'in.dtb';output=Path(tmp)/'out.dtb';source.write_bytes(blob)
            result=subprocess.run([os.sys.executable,str(Path(helpers.ROOT)/'src/percept/build/strip_dtb_property.py'),str(source),str(output),'--remove','/soc@0/usb@38100000:extcon'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            _,nodes=tool.PREP.walk_properties(output.read_bytes())
            self.assertNotIn('extcon',nodes['/soc@0/usb@38100000'])
            self.assertEqual(nodes['/soc@0/usb@38100000']['other'][0],struct.pack('>I',9))
            self.assertEqual(len(blob),output.stat().st_size)
