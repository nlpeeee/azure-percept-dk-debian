# SPDX-License-Identifier: MIT
"""Execute inside the mapped-user build namespace; target root is an argument."""
import json
from pathlib import Path
import sys
from .overlay import apply
if __name__=='__main__':
    c=json.loads(Path(sys.argv[1]).read_text())
    if c.get('generic'):
        from percept.provision import install_generic
        install_generic(sys.argv[2],c['config'],c['root_uuid'],c['esp_uuid'],sys.argv[3],audio=c.get('features',{}).get('audio'))
    else:
        apply(sys.argv[2],c['config'],c['root_uuid'],c['esp_uuid'],sys.argv[3],audio=c.get('features',{}).get('audio'))
