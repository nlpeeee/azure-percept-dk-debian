# SPDX-License-Identifier: MIT
"""Build/fetch CLI handlers, including Windows-to-WSL handoff."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
from .. import wsl
from . import pipeline
def new_completed_build(base, before, pattern='*/*-PERSONAL.manifest.json'):
    completed = set(base.glob(pattern)) - before
    if len(completed) != 1:
        raise ValueError('Expected exactly one new completed WSL build; found '+str(len(completed))+
                         '. Inspect WSL output; no previous image was selected.')
    return next(iter(completed)).parent

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
        if subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip():
            raise ValueError('commit Windows source changes before building')
        if local!=remote:raise ValueError('Windows and WSL source commits differ. Synchronize committed Windows source into '+repo+'; see docs/install.md. No build started.')
        print('WSL distro: '+distro+'; checkout: '+repo+'; source: '+local[:12], flush=True)
        print('Initial fetch/build can take tens of minutes or longer; cached runs are faster. No reliable ETA is available.', flush=True)
        argv=[args.cmd]
        body=None
        if args.cmd=='build':
            argv+=['--board',cfg['board']['name'],'--target',args.target,'--resolved-stdin'];body=json.dumps(cfg)
            if args.recovery: argv+=['--recovery',wsl.win_to_wsl_path(os.path.abspath(args.recovery))]
        elif args.recovery:argv+=['--recovery',wsl.win_to_wsl_path(os.path.abspath(args.recovery))]
        before = set()
        output_board = ('bundle-'+cfg['os']['cpu_profile']) if args.cmd == 'build' and args.target == 'bundle' else (cfg['board']['name'] if args.cmd == 'build' else '')
        pattern = '*/*.bundle.tar.gz' if args.cmd == 'build' and args.target == 'bundle' else '*/*-PERSONAL.manifest.json'
        if args.cmd == 'build':
            base=Path(wsl.wsl_to_win_path(repo,distro))/'out'/output_board
            before=set(base.glob(pattern))
        status=subprocess.run(wsl.reexec_argv(distro,repo,argv),input=body,text=True).returncode
        if status==0 and args.cmd=='build':
            base=Path(wsl.wsl_to_win_path(repo,distro))/'out'/output_board
            latest=new_completed_build(base, before, pattern)
            destination=Path(root)/'out'/output_board/latest.name
            destination.mkdir(parents=True,exist_ok=True)
            print('Copying completed personal installer to Windows; this may take several minutes.', flush=True)
            for file in latest.iterdir():
                if file.is_file():shutil.copy2(file,destination/file.name)
            print('Windows installer files: '+str(destination))
            if args.target == 'image':
                print('Next: python percept flash --board '+cfg['board']['name']+' --manifest "'+str(destination/(cfg['board']['name']+'-PERSONAL.manifest.json'))+'"')
            else:
                print('Import the .bundle.tar.gz into percept gui or percept prepare --bundle.')
        return status
    if args.cmd=='fetch':pipeline.fetch(root,args.recovery)
    else:pipeline.build(root,cfg,bundle=args.target=='bundle',recovery=args.recovery)
    return 0
