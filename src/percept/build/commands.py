# SPDX-License-Identifier: MIT
"""Build/fetch CLI handlers, including Windows-to-WSL handoff."""
import json
import os
from pathlib import Path
import subprocess
import sys
from .. import wsl
from . import pipeline
def dispatch(args,root):
    from .. import cli
    if args.cmd=='build':
        if args.resolved_stdin:cfg=json.load(sys.stdin)
        else:
            result,_,_=cli._load_validated(root,args.board)
            if result is None:return 2
            cli._print_result(result)
            if not result.ok:return 1
            cfg=result.config
    if os.name=='nt':
        distros=wsl.list_distros()
        if not distros:raise ValueError('install a WSL distro first')
        distro=args.distro or distros[0]
        home=subprocess.check_output(['wsl.exe','-d',distro,'--','sh','-c','printf %s "$HOME"'],text=True).strip()
        repo=args.wsl_repo or home+'/'+Path(root).name
        local=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        remote=subprocess.check_output(['wsl.exe','-d',distro,'--cd',repo,'--','git','rev-parse','HEAD'],text=True).strip()
        if local!=remote:raise ValueError('WSL source differs; commit Windows changes, then git pull --ff-only origin main in WSL')
        argv=[args.cmd]
        body=None
        if args.cmd=='build':
            argv+=['--board',cfg['board']['name'],'--target','image','--resolved-stdin'];body=json.dumps(cfg)
        elif args.recovery:argv+=['--recovery',wsl.win_to_wsl_path(os.path.abspath(args.recovery))]
        return subprocess.run(wsl.reexec_argv(distro,repo,argv),input=body,text=True).returncode
    if args.cmd=='fetch':pipeline.fetch(root,args.recovery)
    else:pipeline.build(root,cfg)
    return 0
