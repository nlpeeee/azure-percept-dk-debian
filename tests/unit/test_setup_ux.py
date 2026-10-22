# SPDX-License-Identifier: MIT
import contextlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import helpers
from percept import cli, configure, flash, setup, validate
from percept.build.pipeline import progress
from test_cli_end_to_end import Scripted, wizard_answers, run_cli, CANARY_PW, CANARY_PSK


class SetupUX(unittest.TestCase):
    def test_explicit_name_is_not_prompted_or_overridden(self):
        with tempfile.TemporaryDirectory() as home:
            answers = Scripted(wizard_answers()[1:])
            cfg = configure.run_wizard(configure.Prompter(answers, answers, lambda *_: None),
                                       home=home, defaults_name='chosen')
            self.assertEqual(cfg['board']['name'], 'chosen')
            self.assertEqual(cfg['board']['hostname'], 'chosen')
            self.assertEqual(answers.answers, [])

    def test_invalid_explicit_name_fails_before_prompt(self):
        pr = configure.Prompter(lambda _: self.fail('unexpected prompt'))
        with self.assertRaises(configure.cfgmod.ConfigError):
            configure.run_wizard(pr, defaults_name='../bad')

    def test_reuse_keeps_files_and_hides_secrets(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = helpers.minimal_cfg()
            folder = Path(configure.write_board(root, cfg))
            original = {p.name: p.read_bytes() for p in folder.iterdir()}
            answers = Scripted(['continue'])
            log = []
            rc = setup.run(SimpleNamespace(board=cfg['board']['name']), root,
                           configure.Prompter(answers, answers, log.append))
            self.assertEqual(rc, 0)
            self.assertEqual(original, {p.name: p.read_bytes() for p in folder.iterdir()})
            self.assertNotIn(cfg['user'][0]['authorized_keys'][0], '\n'.join(log))

    def test_summary_does_not_print_password_or_wifi_key(self):
        with tempfile.TemporaryDirectory() as home:
            ans=Scripted(wizard_answers())
            cfg=configure.run_wizard(configure.Prompter(ans, ans, lambda *_: None), home=home)
            res=validate.validate(cfg)
            log=[]
            setup.summary(res.config, log.append)
            text='\n'.join(log)
            for secret in (CANARY_PW, CANARY_PSK, cfg['user'][0]['password_hash']):
                self.assertNotIn(secret, text)

    def test_progress_failure_is_not_reported_complete(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaisesRegex(RuntimeError, 'failed'):
            with progress('test'):
                raise RuntimeError('failed')
        self.assertIn('interrupted or failed', out.getvalue())
        self.assertNotIn(': complete', out.getvalue())

    def test_flash_requires_detection_then_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool=Path(tmp)/'uuu.exe';tool.touch()
            script=Path(tmp)/'unit-PERSONAL.uuu'
            for count in (0, 2):
                output='\n'.join(['1:2 SDP: 0x1fc9 0x012b']*count)
                with patch.object(flash, 'verify_manifest', return_value=({},script)), \
                     patch.object(flash.subprocess, 'run', return_value=SimpleNamespace(stdout=output)) as run:
                    with self.assertRaisesRegex(ValueError, 'Nothing was flashed'):
                        flash.flash(tmp, 'unused', 'unit', str(tool), lambda _: self.fail('confirmation before detection'))
                    self.assertEqual(run.call_count, 1)

    def test_flash_cancel_never_runs_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool=Path(tmp)/'uuu.exe';tool.touch()
            script=Path(tmp)/'unit-PERSONAL.uuu'
            with patch.object(flash, 'verify_manifest', return_value=({},script)), \
                 patch.object(flash.subprocess, 'run', return_value=SimpleNamespace(stdout='1:2 SDP: 0x1fc9 0x012b')) as run:
                with self.assertRaisesRegex(ValueError, 'cancelled'):
                    flash.flash(tmp, 'unused', 'unit', str(tool), lambda _: 'no')
                self.assertEqual(run.call_count, 1)

    def test_completed_selection_never_falls_back_to_old_image(self):
        from percept.build.commands import new_completed_build
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            old=base/'old'/'unit-PERSONAL.manifest.json'
            old.parent.mkdir();old.touch()
            before={old}
            with self.assertRaisesRegex(ValueError, 'found 0'):
                new_completed_build(base, before)
            new=base/'new'/'unit-PERSONAL.manifest.json'
            new.parent.mkdir();new.touch()
            self.assertEqual(new_completed_build(base, before), new.parent)
            extra=base/'extra'/'unit-PERSONAL.manifest.json'
            extra.parent.mkdir();extra.touch()
            with self.assertRaisesRegex(ValueError, 'found 2'):
                new_completed_build(base, before)

    def test_edit_reloads_saved_config(self):
        with tempfile.TemporaryDirectory() as root:
            cfg=helpers.minimal_cfg()
            folder=Path(configure.write_board(root,cfg))
            choices=iter(['edit', '', 'continue'])
            def answer(prompt):
                value=next(choices)
                if value == '':
                    cfg['board']['hostname']='changed-host'
                    configure.write_board(root,cfg,force=True)
                return value
            log=[]
            self.assertEqual(setup.run(SimpleNamespace(board=cfg['board']['name']), root,
                                      configure.Prompter(answer, answer, log.append)), 0)
            self.assertIn('hostname: changed-host', '\n'.join(log))

    def test_import_explicit_name_sets_folder(self):
        from percept import tomlmini
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'input.toml'
            source.write_text(tomlmini.dumps(helpers.minimal_cfg()), encoding='utf-8')
            rc, text=run_cli(root,'configure','--from',str(source),'--name','chosen')
            self.assertEqual(rc,0,text)
            self.assertTrue((Path(root)/'boards/chosen/board.toml').is_file())
