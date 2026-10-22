# SPDX-License-Identifier: MIT
"""Drive the hidden desktop through real offline preparation; never invoke flash."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import helpers
from test_portable_installer import fixture, EXTRAS
from percept import configure, tomlmini


@unittest.skipUnless(EXTRAS,'installer dependencies required')
class DesktopWorkflow(unittest.TestCase):
    def test_prepare_progress_and_stale_selection_invalidation(self):
        try:
            import tkinter as tk
            from tkinter import ttk
            probe=tk.Tk();probe.withdraw();probe.destroy()
        except Exception:
            self.skipTest('Tk desktop/display unavailable')
        from percept import gui
        original=tk.Tk
        failures=[];finished=[]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg,bundle,recovery,pinned=fixture(root)
            configure.write_board(root,cfg)
            (root/'vendor').mkdir()
            (root/'vendor/vendor-manifest.toml').write_text(tomlmini.dumps({
                'schema':1,'input':[dict(pinned,id='ms-recovery-zip')]}))
            def widgets(parent):
                result=[]
                for child in parent.winfo_children():result+=[child]+widgets(child)
                return result
            class HiddenRoot(original):
                def __init__(self):
                    super().__init__();self.withdraw();self.after(50,self.drive)
                def drive(self):
                    try:
                        all_widgets=widgets(self)
                        next(w for w in all_widgets if isinstance(w,ttk.Combobox)).set(cfg['board']['name'])
                        for label,value in (('Local bundle',str(bundle)),('Microsoft recovery ZIP',str(recovery))):
                            caption=next(w for w in all_widgets if isinstance(w,ttk.Label) and w.cget('text')==label)
                            entry=next(w for w in caption.master.winfo_children() if isinstance(w,ttk.Entry))
                            entry.delete(0,'end');entry.insert(0,value)
                        next(w for w in all_widgets if isinstance(w,ttk.Checkbutton)).invoke()
                        next(w for w in all_widgets if isinstance(w,ttk.Button) and w.cget('text')=='2. Prepare').invoke()
                        self.deadline=time.monotonic()+30;self.after(100,self.check)
                    except BaseException as exc:failures.append(exc);self.destroy()
                def check(self):
                    try:
                        all_widgets=widgets(self)
                        flash=next(w for w in all_widgets if isinstance(w,ttk.Button) and w.cget('text')=='3. Flash')
                        if str(flash.cget('state'))!='normal':
                            if time.monotonic()>self.deadline:
                                text=next(w for w in all_widgets if isinstance(w,tk.Text)).get('1.0','end')
                                raise AssertionError('GUI preparation did not complete: '+text)
                            self.after(100,self.check);return
                        bar=next(w for w in all_widgets if isinstance(w,ttk.Progressbar))
                        assert float(bar.cget('value'))==100
                        caption=next(w for w in all_widgets if isinstance(w,ttk.Label) and w.cget('text')=='Local bundle')
                        entry=next(w for w in caption.master.winfo_children() if isinstance(w,ttk.Entry))
                        entry.insert('end','.changed')
                        assert str(flash.cget('state'))=='disabled'
                        finished.append(True);self.destroy()
                    except BaseException as exc:failures.append(exc);self.destroy()
            with patch.object(tk,'Tk',HiddenRoot), \
                 patch('tkinter.simpledialog.askstring',side_effect=AssertionError('unexpected settings prompt')), \
                 patch('percept.flash.flash',side_effect=AssertionError('must never access USB')):
                gui.main(str(root))
            if failures:raise failures[0]
            self.assertEqual(finished,[True])
