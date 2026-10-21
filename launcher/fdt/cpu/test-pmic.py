#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute actual PMIC helper and prove positive/negative conversion contracts."""
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('pmic_validator',Path(__file__).absolute().with_name('validate-pmic.py'));v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
helper=Path(sys.argv[1]).absolute();source=Path(sys.argv[2]).read_bytes()
with tempfile.TemporaryDirectory(prefix='percept-pmic-test-') as tmp:
 d=Path(tmp);inp=d/'input.dtb';inp.write_bytes(source);out=d/'output.dtb'
 subprocess.run([str(helper),str(inp),str(out)],check=True);record=v.validate(source,out.read_bytes())
 _,nodes=v.walk_properties(source);base=v.BASE
 bads=[source[:100],out.read_bytes()]
 for path,prop in [(base,'gpio_intr'),(base+'/regulators/regulator@1','phandle'),(base+'/regulators/regulator@1','regulator-max-microvolt'),('/regulator-buck2','states'),('/cpus/cpu@0','cpu-supply'),('/soc@0/bus@30000000/gpio@30200000','phandle'),('/soc@0/bus@30000000/iomuxc@30330000/pmicirq','fsl,pins')]:
  bad=bytearray(source);_,off,_=nodes[path][prop];bad[off+12]^=1;bads.append(bytes(bad))
 for i,bad in enumerate(bads):
  inp.write_bytes(bad);badout=d/f'bad-{i}.dtb';r=subprocess.run([str(helper),str(inp),str(badout)])
  assert r.returncode!=0 and not badout.exists(),i
 print(json.dumps({'native_conversion':record,'negative_inputs_rejected':len(bads)},indent=2))
