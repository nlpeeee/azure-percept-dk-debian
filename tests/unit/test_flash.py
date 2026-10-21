# SPDX-License-Identifier: MIT
"""Flash input verification must fail before touching a device."""
import json
from pathlib import Path
import tempfile
import unittest
from percept import flash
from percept.build.pipeline import sha

class FlashVerification(unittest.TestCase):
    def test_manifest_hashes_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            raw=root/'unit-PERSONAL.raw';raw.write_bytes(b'image')
            fw=root/'fast-hab-fw.raw';fw.write_bytes(b'firmware')
            script=root/'unit-PERSONAL.uuu';script.write_text('uuu_version 1.2.39\n')
            manifest=root/'unit-PERSONAL.manifest.json'
            manifest.write_text(json.dumps({'personal':True,'artifacts':{x.name:{'sha256':sha(x)} for x in (raw,fw,script)}}))
            _,selected=flash.verify_manifest(manifest)
            self.assertEqual(selected,script)
            raw.write_bytes(b'bad image')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):flash.verify_manifest(manifest)
    def test_connected_device_count(self):
        self.assertEqual(flash.connected_devices('Connected Known USB Devices\n'),[])
        line='1:2 MX8MQ SDP: 0x1fc9 0x012b'
        self.assertEqual(len(flash.connected_devices(line)),1)
        self.assertEqual(len(flash.connected_devices(line+'\n2:3 FB: 0x0525 0xa4a5')),2)
