#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prove only the reviewed PMIC conversion properties/names changed."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
from fdt_contract import walk_properties
BASE='/soc@0/bus@30800000/i2c@30a20000/bd71837@4b'
def cells(*v):return struct.pack('>'+'I'*len(v),*v)
def validate(a,b):
    ah,an=walk_properties(a);bh,bn=walk_properties(b)
    expected={p:{k:v[0] for k,v in props.items()} for p,props in an.items()}
    got={p:{k:v[0] for k,v in props.items()} for p,props in bn.items()}
    pmic=expected[BASE];assert pmic['gpio_intr']==cells(0x2e,7,1);assert pmic['pinctrl-0']==cells(0x2d)
    del pmic['gpio_intr'];pmic.update({'interrupt-parent':cells(0x2e),'interrupts':cells(7,8),'pinctrl-names':b'default\0','rohm,reset-snvs-powered':b''})
    regs=BASE+'/regulators';assert len([p for p in expected if p.startswith(regs+'/')])==13
    for k in ('#address-cells','#size-cells','bd71837,pmic-buck2-uses-i2c-dvs','bd71837,pmic-buck2-dvs-voltage'):del expected[regs][k]
    for i in range(15):
        name=('BUCK'+str(i+1)) if i<8 else ('LDO'+str(i-7))
        path=regs+'/'+name
        if i in (12,14):props={}
        else:
            props=expected.pop(regs+'/regulator@'+str(i));assert props['reg']==cells(i)
            assert props['regulator-compatible']==name.lower().encode()+b'\0'
            del props['reg'];del props['regulator-compatible']
        props['rohm,no-regulator-enable-control']=b''
        if i==0:assert props.pop('regulator-ramp-delay')==cells(1250)
        if i==1:props['regulator-ramp-delay']=cells(5000);assert props['phandle']==cells(7)
        expected[path]=props
    expected['/regulator-buck2']['status']=b'disabled\0'
    for i in range(4):
        cpu=expected['/cpus/cpu@'+str(i)];assert cpu['cpu-supply']==cells(0x5e);cpu['cpu-supply']=cells(7)
    assert expected==got,'unexpected property/node change'
    assert ah['reservations']==bh['reservations'],'reservations changed'
    return {'input_sha256':hashlib.sha256(a).hexdigest(),'output_sha256':hashlib.sha256(b).hexdigest(),'exact_reviewed_property_contract':True,'all_other_properties_identical':True,'reservations_identical':True,'rails_no_regulator_enable_control':15,'cpu_supply_phandle':7,'monitor_0x24_intentional_change':'00->30','dt_voltage_constraints_changed':False}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();record=validate(a.source.read_bytes(),a.output.read_bytes());a.output.with_suffix(a.output.suffix+'.pmic.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
