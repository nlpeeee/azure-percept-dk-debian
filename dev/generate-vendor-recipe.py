# SPDX-License-Identifier: MIT
"""Verify portable extraction against existing Linux vendor outputs; emit metadata only."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from percept.vendor_recipe import generate
from percept.build.pipeline import inputs
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--recovery',type=Path,required=True)
p.add_argument('--reference',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
if a.output.exists():p.error('output exists')
data=generate(a.recovery,a.reference,inputs(ROOT)['ms-recovery-zip'])
a.output.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
print('Portable extraction matches Linux for all required vendor files')
