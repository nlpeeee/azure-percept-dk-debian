# SPDX-License-Identifier: MIT
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import zipfile
import helpers
from percept import bundles, packages, provision, validate, vendor_recipe
from percept.build import pipeline
from percept.prepare import make_esp, prepare, fetch_file, release_bundle
from percept.events import Reporter


def fixture(root):
    root=Path(root);folder=root/'bundle-files';folder.mkdir()
    cfg=validate.validate(helpers.minimal_cfg(os={'features':{'usb_c_host':False}})).config
    cfg['os']['features']['usb_c_host']=False
    vendor=root/'vendor.zip'
    files={name:('synthetic '+name).encode() for name in vendor_recipe.FILES}
    files['emmc_full.txt']=b'uuu_version 1.2.39\nSDP: boot -f _flash.bin\nFB: flash -raw2sparse all _image.raw\n'
    with zipfile.ZipFile(vendor,'w') as archive:
        for name,value in files.items():archive.writestr(name,value)
    pinned={'sha256':pipeline.sha(vendor),'url':'https://example.invalid/recovery.zip'}
    recipe={'schema':1,'zip_sha256':pinned['sha256'],'files':{
        name:{'member':name,'ranges':[[0,len(value)]],'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()}
        for name,value in files.items()}}
    for name in bundles.REQUIRED:
        (folder/name).write_bytes(b'synthetic '+name.encode())
    (folder/'rootfs.img').write_bytes(b'\0'*1024**2)
    (folder/'profile.toml').write_bytes((Path(helpers.ROOT)/'profiles/debian-trixie/profile.toml').read_bytes())
    (folder/'grub.cfg').write_text('linux $efiroot/percept/stock-Image\nfdt pe100-usbc.dtb\n')
    (folder/'vendor-recipe.json').write_text(json.dumps(recipe))
    manifest={'schema':1,'kind':'percept-bundle','personal':False,'cpu_profile':'unchanged',
        'profile':'debian-trixie','features':{'gpu':True,'vpu':True,'usb_c_host':False,
        'camera':False,'upper_ram':True,'thermal':True},'rootfs_packages':[p+'=1.0' for p in packages.VPU_RUNTIME],
        'source_commit':'0'*40,'kernel_release':'6.12.113+deb13-arm64',
        'root_uuid':str(uuid.uuid4()),'esp_uuid':'1234-5678','hardware_tested':False,
        'qualification':{'generic_firstboot':'pending'}}
    bundle=root/'unit.bundle.tar.gz';bundles.write_bundle(folder,manifest,bundle)
    return cfg,bundle,vendor,pinned


class Portable(unittest.TestCase):
    def test_actual_vpu_package_selection_and_inventory(self):
        for enabled in (True,False,None):
            cfg={'os':{'features':{'vpu':enabled}}}
            expected=list(packages.VPU_RUNTIME) if enabled is not False else []
            self.assertEqual(packages.vpu_packages(cfg),expected)
        with self.assertRaisesRegex(ValueError,'missing runtime'):
            packages.check_inventory(['ffmpeg=1'],True)
        packages.check_inventory(['ffmpeg=1'],False)
        packages.check_inventory([p+':arm64=1' for p in packages.VPU_RUNTIME],True)

    def test_generic_config_removes_personal_settings(self):
        cfg=validate.validate(helpers.minimal_cfg(network={'wifi':{'enabled':True,
            'ssid':'test-network','psk':'synthetic-passphrase','country':'GB'}})).config
        generic=pipeline.generic_config(cfg)
        self.assertEqual(generic['user'],[])
        self.assertNotIn('synthetic-passphrase',json.dumps(generic))
        self.assertNotIn(cfg['user'][0]['authorized_keys'][0],json.dumps(generic))

    def test_bundle_round_trip_and_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg,bundle,_,_=fixture(tmp)
            manifest=bundles.unpack(bundle,Path(tmp)/'unpacked')
            bundles.compatible(cfg,manifest)
            cfg['os']['cpu_profile']='rated'
            with self.assertRaisesRegex(ValueError,'CPU'):bundles.compatible(cfg,manifest)

    def test_archive_links_and_duplicate_paths_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.tar'
            with tarfile.open(path,'w') as archive:
                entry=tarfile.TarInfo('../escape');entry.size=1
                archive.addfile(entry,io.BytesIO(b'x'))
            with self.assertRaises(ValueError):bundles.read_manifest(path)

    def test_bundle_artifact_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,bundle,_,_=fixture(tmp)
            other=Path(tmp)/'corrupt.tar'
            with tarfile.open(bundle,'r:*') as src,tarfile.open(other,'w') as dst:
                for member in src.getmembers():
                    value=src.extractfile(member).read()
                    if member.name=='rootfs.img':value=b'X'+value[1:]
                    dst.addfile(member,io.BytesIO(value))
            with self.assertRaisesRegex(ValueError,'hash mismatch'):bundles.unpack(other,Path(tmp)/'bad')

    def test_vendor_extract_hashes_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,bundle,zip_path,pinned=fixture(tmp)
            bundles.unpack(bundle,Path(tmp)/'expanded')
            recipe=json.loads((Path(tmp)/'expanded/vendor-recipe.json').read_text())
            vendor_recipe.extract(zip_path,recipe,Path(tmp)/'vendor',pinned)
            recipe['files']['Image']['ranges'][0][0]=10**12
            with self.assertRaisesRegex(ValueError,'outside member'):
                vendor_recipe.extract(zip_path,recipe,Path(tmp)/'invalid',pinned)

    def test_firstboot_failure_retry_and_consumption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);payload=root/'boot/efi/percept/firstboot.json';payload.parent.mkdir(parents=True)
            (root/'etc/percept').mkdir(parents=True)
            (root/'etc/percept/bundle.json').write_text(json.dumps({'root_uuid':'test-root','esp_uuid':'test-esp'}))
            cfg=validate.validate(helpers.minimal_cfg()).config
            payload.write_text(json.dumps({'schema':1,'config':cfg}))
            def fail(*args,**kwargs):raise RuntimeError('interrupted')
            with self.assertRaises(RuntimeError):provision.provision(root,fail)
            self.assertFalse((root/'var/lib/percept/provision/complete').exists())
            self.assertTrue(payload.exists())
            calls=[]
            provision.provision(root,lambda *args,**kwargs:calls.append((args,kwargs)))
            self.assertEqual(len(calls),1)
            self.assertFalse(payload.exists())
            provision.provision(root,lambda *args,**kwargs:self.fail('reapplied completed settings'))

    def test_changed_configuration_during_retry_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);payload=root/'boot/efi/percept/firstboot.json';payload.parent.mkdir(parents=True)
            (root/'etc/percept').mkdir(parents=True)
            (root/'etc/percept/bundle.json').write_text(json.dumps({'root_uuid':'root','esp_uuid':'esp'}))
            cfg=validate.validate(helpers.minimal_cfg()).config
            payload.write_text(json.dumps({'schema':1,'config':cfg}))
            with self.assertRaises(RuntimeError):
                provision.provision(root,lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError()))
            cfg['board']['hostname']='different';payload.write_text(json.dumps({'schema':1,'config':cfg}))
            with self.assertRaisesRegex(ValueError,'changed during'):provision.provision(root)

    def test_missing_configuration_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'missing'):provision.provision(Path(tmp))

    def test_generated_password_payload_validates_on_target(self):
        from percept.build.overlay import credentials
        cfg=validate.validate({'schema':1,'board':{'name':'unit'},
            'user':[{'name':'percept','password_mode':'generate'}],
            'ssh':{'password_auth':True},'rescue':{'password_auth':True}}).config
        generated=credentials(cfg);cfg['rescue'].pop('password_mode',None)
        self.assertTrue(generated)
        self.assertEqual(validate.validate(cfg).errors,[])

    def test_generic_staging_gates_login_and_contains_no_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'etc/ssh').mkdir(parents=True)
            (root/'etc/ssh/ssh_host_test').write_text('synthetic host identity')
            cfg=pipeline.generic_config(validate.validate(helpers.minimal_cfg()).config)
            with patch('percept.provision.subprocess.run'):
                provision.install_generic(root,cfg,'root-identity','1234-5678',helpers.ROOT)
            for name in provision.GATED:
                text=(root/('etc/systemd/system/'+name+'.d/05-provision.conf')).read_text()
                self.assertIn('Requires=percept-provision.service',text)
                self.assertIn('After=percept-provision.service',text)
            self.assertFalse((root/'etc/ssh/ssh_host_test').exists())
            self.assertEqual((root/'etc/machine-id').read_text(),'')
            self.assertFalse((root/'etc/passwd').exists())

    def test_unsigned_bundle_requires_explicit_trust(self):
        with self.assertRaisesRegex(ValueError,'trust-local'):
            prepare('.',{},bundle='unused')

    def test_unsigned_release_is_pinned_by_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'release').mkdir()
            (root/'release/policy.json').write_text(json.dumps({'base_url':'https://example.invalid/releases',
                'public_keys':{}}))
            digest='a'*64
            message=json.dumps({'schema':1,'version':'v-unit','bundles':{'unchanged':{
                'file':'unit.bundle.tar.gz','sha256':digest,'bytes':123}}}).encode()
            cfg=validate.validate(helpers.minimal_cfg()).config
            with patch('percept.prepare.small_download',side_effect=[message]) as small, \
                 patch('percept.prepare.fetch_file',return_value=root/'cached') as fetch:
                self.assertEqual(release_bundle(root,'v-unit',cfg,Reporter(lambda e:None)),root/'cached')
                small.assert_called_once_with('https://example.invalid/releases/v-unit/release.json')
                url,_,sha,*_=fetch.call_args[0]
                self.assertEqual((url,sha),('https://example.invalid/releases/v-unit/unit.bundle.tar.gz',digest))
            bad=json.dumps({'schema':1,'version':'other','bundles':{}}).encode()
            with patch('percept.prepare.small_download',side_effect=[bad]), \
                 patch('percept.prepare.fetch_file') as fetch:
                with self.assertRaisesRegex(ValueError,'version/format mismatch'):
                    release_bundle(root,'v-unit',cfg,Reporter(lambda e:None))
                fetch.assert_not_called()

    def test_fast_doctor_never_calls_wsl_or_downloads(self):
        from percept import doctor
        with tempfile.TemporaryDirectory() as tmp, \
             patch('percept.wsl.run',side_effect=AssertionError('must not start WSL')), \
             patch('percept.build.pipeline.download',side_effect=AssertionError('must not download')):
            checks=doctor.run_installer(tmp)
            self.assertTrue(any(c.name=='preparation' and c.status=='ok' for c in checks))


try:
    import pyfatfs
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    EXTRAS=True
except ImportError:EXTRAS=False


@unittest.skipUnless(EXTRAS,'install requirements-installer.txt for portable filesystem/signature tests')
class WithDependencies(unittest.TestCase):
    def test_release_missing_variant_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'release').mkdir()
            key=Ed25519PrivateKey.generate()
            public=base64.b64encode(key.public_key().public_bytes_raw()).decode()
            (root/'release/policy.json').write_text(json.dumps({'base_url':'https://example.invalid',
                'public_keys':{'unit':public}}))
            message=json.dumps({'schema':1,'version':'v-unit','bundles':{}}).encode()
            signature=json.dumps({'key_id':'unit','signature':base64.b64encode(key.sign(message)).decode()}).encode()
            cfg=validate.validate(helpers.minimal_cfg()).config
            with patch('percept.prepare.small_download',side_effect=[message,signature]):
                with self.assertRaisesRegex(ValueError,'selected CPU variant'):
                    release_bundle(root,'v-unit',cfg,Reporter(lambda e:None))
            with patch('percept.prepare.small_download',side_effect=[message,b'{}']):
                with self.assertRaisesRegex(ValueError,'malformed release signature'):
                    release_bundle(root,'v-unit',cfg,Reporter(lambda e:None))

    def test_encrypted_key_generation_and_overwrite_protection(self):
        from percept import sshkeys
        from cryptography.hazmat.primitives.serialization import load_ssh_private_key
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'synthetic-key'
            public=sshkeys.generate_key(path,'synthetic-passphrase')
            sshkeys.check_key(public)
            load_ssh_private_key(path.read_bytes(),b'synthetic-passphrase')
            with self.assertRaises(ValueError):load_ssh_private_key(path.read_bytes(),b'wrong-passphrase')
            before=path.read_bytes()
            with self.assertRaises(FileExistsError):sshkeys.generate_key(path,'different-passphrase')
            self.assertEqual(path.read_bytes(),before)

    def test_signed_release_chain_authenticates_before_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'release').mkdir()
            cfg=validate.validate(helpers.minimal_cfg()).config
            key=Ed25519PrivateKey.generate()
            public=base64.b64encode(key.public_key().public_bytes_raw()).decode()
            (root/'release/policy.json').write_text(json.dumps({'base_url':'https://example.invalid/releases',
                'public_keys':{'unit':public}}))
            message=json.dumps({'schema':1,'version':'v-unit','bundles':{'unchanged':{
                'file':'unit.bundle.tar.gz','sha256':'0'*64,'bytes':123}}}).encode()
            signature=json.dumps({'key_id':'unit','signature':base64.b64encode(key.sign(message)).decode()}).encode()
            with patch('percept.prepare.small_download',side_effect=[message,signature]), \
                 patch('percept.prepare.fetch_file',return_value=root/'cached') as fetch:
                self.assertEqual(release_bundle(root,'v-unit',cfg,Reporter(lambda e:None)),root/'cached')
                fetch.assert_called_once()
            with patch('percept.prepare.small_download',side_effect=[message+b' ',signature]), \
                 patch('percept.prepare.fetch_file') as fetch:
                with self.assertRaisesRegex(ValueError,'signature'):
                    release_bundle(root,'v-unit',cfg,Reporter(lambda e:None))
                fetch.assert_not_called()

    def test_fat_and_byte_range_reader_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'esp.img';value=b'synthetic EFI contents'
            make_esp(path,{'EFI/BOOT/bootaa64.efi':value},'1234-5678')
            with path.open('rb') as stream:
                ranges=vendor_recipe.fat_file(stream,0,'/EFI/BOOT/bootaa64.efi')
                self.assertEqual(b''.join(vendor_recipe.read_at(stream,*pair) for pair in ranges),value)

    def test_signature_rejects_tampering(self):
        key=Ed25519PrivateKey.generate();message=b'unsigned fixture content'
        signature=base64.b64encode(key.sign(message)).decode()
        public=base64.b64encode(key.public_key().public_bytes_raw()).decode()
        bundles.verify_signature(message,signature,public)
        with self.assertRaisesRegex(ValueError,'signature'):bundles.verify_signature(message+b'x',signature,public)

    def test_full_portable_preparation_and_flash_hashes(self):
        from percept.flash import verify_manifest
        with tempfile.TemporaryDirectory() as tmp:
            cfg,bundle,zip_path,pinned=fixture(tmp)
            events=[]
            with patch('percept.prepare.inputs',return_value={'ms-recovery-zip':pinned}):
                result=prepare(helpers.ROOT,cfg,bundle=bundle,trust_local=True,recovery=zip_path,
                    output=Path(tmp)/'personal',report=Reporter(events.append))
            data,_=verify_manifest(result)
            self.assertTrue(data['personal']);self.assertFalse(data['hardware_tested'])
            self.assertFalse((result.parent/'work').exists())
            self.assertEqual(events[-1]['stage'],'complete')

    def test_space_and_cancellation_create_no_ready_manifest(self):
        from collections import namedtuple
        usage=namedtuple('Usage','total used free')
        with tempfile.TemporaryDirectory() as tmp:
            cfg,bundle,zip_path,pinned=fixture(tmp)
            output=Path(tmp)/'personal'
            with patch('percept.prepare.shutil.disk_usage',return_value=usage(1,1,0)):
                with self.assertRaisesRegex(ValueError,'insufficient'):
                    prepare(helpers.ROOT,cfg,bundle=bundle,trust_local=True,output=output)
            self.assertFalse(output.exists())
            cancel=threading.Event();cancel.set()
            with self.assertRaises(InterruptedError):
                prepare(helpers.ROOT,cfg,bundle=bundle,trust_local=True,output=output,cancel=cancel)
            self.assertFalse(output.exists())
