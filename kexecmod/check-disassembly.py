#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reject canaries/randomized task accesses; verify fixed thread_info preemption accesses."""
import json
from pathlib import Path
import re
import sys

def check(arch, core, offsets):
    if '__stack_chk' in arch+core or 'sp_el0' in arch:
        raise ValueError('unexpected stack canary or architecture task access')
    if not re.search(r'^#define TSK_TI_PREEMPT 24 ',offsets,re.M):
        raise ValueError('unexpected architecture preemption offset')
    function=''
    instructions=[]
    observed=[]
    for line in core.splitlines():
        label=re.match(r'^[0-9a-f]+ <([^>]+)>:',line)
        if label:function=label[1]
        ins=re.match(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(.+)',line)
        if ins:instructions.append((function,ins[1].strip()))
    for i,(function,ins) in enumerate(instructions):
        if 'sp_el0' not in ins:continue
        if function!='kernel_kexec' or not re.fullmatch(r'mrs\s+x1, sp_el0',ins):
            raise ValueError('unexpected task-pointer access: '+function+' '+ins)
        follow=[x[1].split('//')[0].strip() for x in instructions[i+1:i+4]]
        patterns=[(r'ldr\s+w0, \[x1, #24\]',r'add\s+w0, w0, #0x1',r'str\s+w0, \[x1, #24\]'),
                  (r'ldr\s+x0, \[x1, #24\]',r'sub\s+x0, x0, #0x1',r'str\s+w0, \[x1, #24\]')]
        if not any(all(re.fullmatch(pattern,text) for pattern,text in zip(group,follow)) for group in patterns):
            raise ValueError('unreviewed task-field sequence: '+repr(follow))
        observed.append({'function':function,'field':'thread_info.preempt_count','offset':24})
    if len(observed)!=2:raise ValueError('expected exactly the preempt_disable/enable pair')
    return {'nonrandomized_thread_info_accesses':observed,'randomized_task_field_accesses':0,'stack_canary_accesses':0}

if __name__=='__main__':
    print(json.dumps(check(*(Path(x).read_text() for x in sys.argv[1:])),indent=2))
