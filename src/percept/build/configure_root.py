# SPDX-License-Identifier: MIT
"""Execute inside the mapped-user build namespace; target root is an argument."""
import json
from pathlib import Path
import sys
from .overlay import apply
if __name__=='__main__':
    c=json.loads(Path(sys.argv[1]).read_text())
    apply(sys.argv[2],c['config'],c['root_uuid'],c['esp_uuid'],sys.argv[3])
