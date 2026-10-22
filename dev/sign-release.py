# SPDX-License-Identifier: MIT
"""Sign an exact release.json with an external Ed25519 PEM key; never print keys."""
import argparse
import base64
import json
from pathlib import Path
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--manifest',type=Path,required=True)
p.add_argument('--key',type=Path,required=True)
p.add_argument('--key-id',required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
if a.output.exists(): p.error('output exists')
key=load_pem_private_key(a.key.read_bytes(),password=None)
if not isinstance(key,Ed25519PrivateKey): p.error('key must be Ed25519')
signature=key.sign(a.manifest.read_bytes())
a.output.write_text(json.dumps({'key_id':a.key_id,'signature':base64.b64encode(signature).decode()})+'\n',encoding='utf-8')
