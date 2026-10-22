# SPDX-License-Identifier: MIT
"""Tk desktop front end over the same configuration, preparation and flash code."""
import io
from pathlib import Path
import queue
import threading
import time


def main(repo, smoke=False):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, simpledialog
    from . import config, configure, setup, validate
    from .events import Reporter
    from .prepare import prepare
    from .flash import flash
    root = tk.Tk(); root.title('Percept Debian installer'); root.geometry('850x700')
    if smoke: root.withdraw()
    frame = ttk.Frame(root, padding=16); frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Install Debian on your Percept DK', font=('', 17, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Choose a release or your own build, review settings, then prepare and flash.').pack(anchor='w', pady=(4,12))
    board = tk.StringVar(value='my-percept'); source = tk.StringVar(value='local')
    bundle = tk.StringVar(); version = tk.StringVar(); recovery = tk.StringVar(); trust = tk.BooleanVar()
    saved = sorted(p.parent.name for p in (Path(repo)/'boards').glob('*/board.toml'))
    line = ttk.Frame(frame); line.pack(fill='x', pady=4)
    ttk.Label(line,text='Board configuration',width=22).pack(side='left')
    ttk.Combobox(line,textvariable=board,values=saved).pack(side='left',fill='x',expand=True)
    import_button=ttk.Button(line,text='Import settings',command=lambda: import_settings())
    import_button.pack(side='left',padx=(6,0))
    def file_row(label, variable, select):
        row=ttk.Frame(frame);row.pack(fill='x',pady=4)
        ttk.Label(row,text=label,width=22).pack(side='left')
        ttk.Entry(row,textvariable=variable).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='Browse',command=lambda: variable.set(filedialog.askopenfilename() or variable.get())).pack(side='left',padx=(5,0))
    row=ttk.Frame(frame);row.pack(fill='x',pady=4)
    ttk.Radiobutton(row,text='Use my own build',variable=source,value='local').pack(side='left')
    ttk.Radiobutton(row,text='Download a signed release',variable=source,value='release').pack(side='left',padx=16)
    file_row('Local bundle',bundle,True)
    row=ttk.Frame(frame);row.pack(fill='x',pady=4)
    ttk.Label(row,text='Release version',width=22).pack(side='left')
    ttk.Entry(row,textvariable=version).pack(side='left',fill='x',expand=True)
    ttk.Checkbutton(frame,text='I trust the source of this unsigned local bundle',variable=trust).pack(anchor='w',pady=4)
    file_row('Microsoft recovery ZIP',recovery,True)
    ttk.Label(frame,text='Leave the ZIP blank to download it from Microsoft. Personal files stay on this PC.').pack(anchor='w',pady=4)
    log=tk.Text(frame,height=16,wrap='word',state='disabled');log.pack(fill='both',expand=True,pady=12)
    status=tk.StringVar(value='1. Configure or review your saved board settings.')
    ttk.Label(frame,textvariable=status,wraplength=790).pack(anchor='w')
    progress=ttk.Progressbar(frame,mode='determinate',maximum=100)
    progress.pack(fill='x',pady=(8,0))
    actions=ttk.Frame(frame);actions.pack(fill='x',pady=(12,0))
    state={'busy':False,'cfg':None,'manifest':None,'name':None}; mailbox=queue.Queue(); cancel=threading.Event()
    def append(text):
        log.configure(state='normal');log.insert('end',text+'\n');log.see('end');log.configure(state='disabled')
    def prompt(question):
        value=simpledialog.askstring('Percept settings',question,parent=root)
        if value is None: raise InterruptedError('configuration cancelled')
        return value
    def secret(question):
        value=simpledialog.askstring('Percept password',question,parent=root,show='*')
        if value is None: raise InterruptedError('configuration cancelled')
        return value
    def generate_key(path):
        from . import sshkeys
        if Path(path).exists() or Path(path+'.pub').exists():
            raise ValueError('This key file already exists. Select the existing public key instead.')
        password=secret('Passphrase for the new PC SSH key (leave empty only if intended): ')
        if password and password!=secret('Repeat SSH key passphrase: '):
            raise ValueError('SSH key passphrases differ; no key was written.')
        sshkeys.generate_key(path,password)
    def load_settings():
        if state['busy']: return None
        name=board.get().strip()
        if not validate.NAME_RE.fullmatch(name): raise ValueError('Use lowercase letters, digits, - and _ for the board name.')
        directory=Path(config.board_path(repo,name))
        if (directory/'board.toml').is_file():
            cfg=config.load_board(str(directory))
        else:
            prompter=configure.Prompter(prompt,secret,append)
            prompter.generate_key=generate_key
            cfg=configure.run_wizard(prompter,defaults_name=name)
            result=validate.validate(cfg,repo)
            if not result.ok: raise ValueError('Settings need correction: '+'; '.join(result.errors))
            configure.write_board(repo,cfg)
        result=validate.validate(cfg,str(directory))
        if not result.ok: raise ValueError('Settings need correction: '+'; '.join(result.errors))
        if result.config['board']['name']!=name: raise ValueError('Saved board name must match its folder.')
        state.update(cfg=result.config, name=name, manifest=None)
        setup.summary(result.config,append)
        status.set('Settings reviewed. Prepare an image next; hardware qualification is shown separately.')
        return result.config
    def configure_click():
        try: load_settings()
        except (ValueError,config.ConfigError,OSError,InterruptedError) as exc: messagebox.showerror('Settings',str(exc),parent=root)
    def import_settings():
        if state['busy']:return
        chosen=filedialog.askopenfilename(title='Select board.toml from an existing saved board',filetypes=[('Board settings','board.toml')])
        if not chosen:return
        try:
            if Path(chosen).name!='board.toml':raise ValueError('Select the saved board.toml file.')
            name=configure.import_board(repo,Path(chosen).parent)
            board.set(name);load_settings()
            append('Imported a copy. The original settings were preserved.')
        except (OSError,ValueError,config.ConfigError) as exc:messagebox.showerror('Import settings',str(exc),parent=root)
    def edit_settings():
        if state['busy']: return
        try:
            name=board.get().strip()
            if not validate.NAME_RE.fullmatch(name): raise ValueError('Invalid board name')
            directory=Path(config.board_path(repo,name))
            if not (directory/'board.toml').is_file():
                configure_click(); return
            editor=tk.Toplevel(root);editor.title('Edit saved settings — '+name);editor.geometry('750x550')
            editor.transient(root);editor.grab_set()
            tabs=ttk.Notebook(editor);tabs.pack(fill='both',expand=True,padx=10,pady=10);texts={}
            for filename in ('board.toml','secrets.toml'):
                tab=ttk.Frame(tabs);tabs.add(tab,text=filename)
                if filename=='secrets.toml': ttk.Label(tab,text='Private settings. Keep these on your PC.').pack(anchor='w')
                text=tk.Text(tab,wrap='none');text.pack(fill='both',expand=True)
                path=directory/filename
                if path.exists(): text.insert('1.0',path.read_text(encoding='utf-8'))
                texts[filename]=text
            def save():
                from . import tomlmini
                try:
                    public=tomlmini.loads(texts['board.toml'].get('1.0','end'))
                    private=tomlmini.loads(texts['secrets.toml'].get('1.0','end'))
                    merged=config.merge(public,private)
                    result=validate.validate(merged,str(directory))
                    if not result.ok: raise ValueError('; '.join(result.errors))
                    if merged['board']['name']!=name: raise ValueError('Keep board.name equal to '+name)
                    configure.write_board(repo,merged,force=True);editor.destroy();load_settings()
                except Exception: messagebox.showerror('Settings','Settings could not be validated. Check field names and values; no changes were saved.',parent=editor)
            ttk.Button(editor,text='Validate and save',command=save).pack(pady=(0,10))
        except Exception as exc: messagebox.showerror('Settings',str(exc),parent=root)
    def worker(fn):
        state['busy']=True;state['last_message']='Working';cancel.clear()
        report.started=time.monotonic()
        progress.configure(mode='indeterminate');progress.start(15);toggle()
        def run():
            try: mailbox.put(('done',fn()))
            except Exception as exc:
                from .redact import Redactor, collect_secrets
                red = Redactor(collect_secrets(state['cfg']) if state['cfg'] else set())
                mailbox.put(('error',red(str(exc))+' Incomplete output must not be flashed.'))
        threading.Thread(target=run,daemon=True).start()
    report=Reporter(lambda event:mailbox.put(('event',event)))
    def prepare_click():
        if state['busy']: return
        try:
            cfg=load_settings()
            local=bundle.get().strip() if source.get()=='local' else None
            release=version.get().strip() if source.get()=='release' else None
            trusted=trust.get();zip_path=recovery.get().strip() or None
            if local and not trusted: raise ValueError('Confirm that you trust this local build before preparing it.')
            worker(lambda:prepare(repo,cfg,bundle=local,release=release,trust_local=trusted,
                                  recovery=zip_path,report=report,cancel=cancel))
        except Exception as exc: messagebox.showerror('Prepare',str(exc),parent=root)
    def confirm_in_ui(question):
        ready=threading.Event();answer=[]
        mailbox.put(('confirm',(question,answer,ready)));ready.wait()
        return answer[0]
    def flash_click():
        if state['busy'] or not state['manifest']: return
        messagebox.showinfo('Enter USB recovery',
            'Power OFF before moving switches. Using the official photo orientation, change internal DIP 1001 (up-down-down-up) to 0101 (down-up-down-up). Connect USB-C to this PC, then power ON.\n\nClick OK when the board is ready for USB detection. The next confirmation authorizes erasing eMMC.',parent=root)
        manifest,name=state['manifest'],state['name']
        worker(lambda:flash(repo,str(manifest),name,confirm=confirm_in_ui,report=report))
    buttons=[]
    for label,command in [('1. Configure / review',configure_click),('Edit saved settings',edit_settings),
                          ('2. Prepare',prepare_click),('3. Flash',flash_click)]:
        button=ttk.Button(actions,text=label,command=command);button.pack(side='left',padx=(0,6));buttons.append(button)
    cancel_button=ttk.Button(actions,text='Cancel preparation',command=cancel.set);cancel_button.pack(side='right')
    def photo():
        import webbrowser
        webbrowser.open('https://github.com/MicrosoftDocs/azure-docs/blob/30ca9855dea6dbafd43ac456e9c1965633e3676d/articles/azure-percept/media/how-to-usb-update/dip-switch-03.jpg')
    ttk.Button(frame,text='Official DIP-switch photo',command=photo).pack(anchor='w',pady=(8,0))
    def toggle():
        def inputs(widget):
            for child in widget.winfo_children():
                if isinstance(child,(ttk.Entry,ttk.Combobox,ttk.Radiobutton,ttk.Checkbutton)):
                    child.configure(state='disabled' if state['busy'] else 'normal')
                inputs(child)
        inputs(frame)
        import_button.configure(state='disabled' if state['busy'] else 'normal')
        for button in buttons: button.configure(state='disabled' if state['busy'] else 'normal')
        buttons[-1].configure(state='normal' if not state['busy'] and state['manifest'] else 'disabled')
        cancel_button.configure(state='normal' if state['busy'] and state.get('phase')=='prepare' else 'disabled')
    def invalidate(*args):
        if not state['busy']:
            state['manifest']=None;toggle()
    for variable in (board,source,bundle,version,recovery,trust):variable.trace_add('write',invalidate)
    # Phase tracking prevents presenting flash cancellation as safe.
    original_prepare=prepare_click;original_flash=flash_click
    def prepare_phase(): state['phase']='prepare';original_prepare()
    def flash_phase(): state['phase']='flash';original_flash()
    buttons[2].configure(command=prepare_phase);buttons[3].configure(command=flash_phase)
    def pump():
        try:
            while True:
                kind,value=mailbox.get_nowait()
                if kind=='event':
                    message=value['message']
                    if value.get('total'):
                        progress.stop();progress.configure(mode='determinate',maximum=value['total'],value=value['current'])
                        message+=' (%.1f / %.1f MiB)' % (value['current']/1024**2,value['total']/1024**2)
                    elif str(progress.cget('mode'))!='indeterminate':
                        progress.configure(mode='indeterminate');progress.start(15)
                    state['last_message']=message
                    append(message);status.set(message)
                elif kind=='confirm':
                    question,answer,ready=value
                    answer.append(simpledialog.askstring('Erase confirmation',question,parent=root) or '');ready.set()
                elif kind=='done':
                    state['busy']=False
                    progress.stop();progress.configure(mode='determinate',maximum=100,value=100 if isinstance(value,Path) or value==0 else 0)
                    if isinstance(value,Path):
                        state['manifest']=value;append('Prepared manifest: '+str(value))
                    elif value==0: status.set('Flash completed. Power off, restore DIP 1001, then power on. Allow several minutes before login.')
                    else: status.set('Flashing failed. Retain diagnostics; use the Microsoft restoration fallback if necessary.')
                    toggle()
                elif kind=='error':
                    state['busy']=False;progress.stop();progress.configure(mode='determinate',maximum=100,value=0)
                    toggle();append(value);status.set(value)
        except queue.Empty: pass
        if state['busy']:
            status.set(state['last_message']+' (%ds elapsed)' % (time.monotonic()-report.started))
        root.after(100,pump)
    def close():
        if state['busy']:
            messagebox.showinfo('Operation active','Wait for the operation to finish. Preparation can be cancelled; keep USB and power connected during flashing.',parent=root)
        else: root.destroy()
    root.protocol('WM_DELETE_WINDOW',close);toggle();pump()
    if smoke: root.after(100, root.destroy)
    root.mainloop()
    return 0
