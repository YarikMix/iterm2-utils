import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from iterm2_utils import lifecycle, state
from iterm2_utils.planner import plan
from tests.test_lifecycle import LifecycleFixture


class AppearanceTests(LifecycleFixture):
    def setUp(self):
        super().setUp()
        self.context.capabilities |= {'python:iterm2'}
        self.source = self.context.paths.home/'правила $(literal).json'
        self.png = self.context.paths.home/'иконка ; literal.png'
        self.png.write_bytes((self.context.paths.repo/'runtime/assets/appearance/ios.png').read_bytes())
        self.rules = {'projects':[{'root':str(self.context.paths.home/'unmounted/repo'), 'color':'#12ab34','icon':str(self.png)}]}
        self.source.write_text(json.dumps(self.rules))
        # Dynamic assignment also exercises old Context until the explicit field exists.
        self.context.appearance_config = self.source

    def installed_rule(self):
        return json.loads((self.context.paths.config/'appearance.json').read_text())['projects'][0]

    def test_explicit_install_owns_config_and_hash_icon_without_hooks(self):
        result=self.install('appearance');self.assertSuccess(result)
        self.assertEqual(result.receipt.selection.pairs,{'codex:appearance'})
        icon=self.context.paths.data/'appearance/icons'/(hashlib.sha256(self.png.read_bytes()).hexdigest()+'.png')
        self.assertEqual(self.installed_rule(),dict(self.rules['projects'][0],root=str(Path(self.rules['projects'][0]['root']).resolve()),color='#12AB34',icon=str(icon)))
        self.assertEqual(icon.read_bytes(),self.png.read_bytes())
        self.assertEqual([s.code for s in result.receipt.pending_ui],['appearance_api'])
        self.assertFalse(self.context.paths.codex_home.exists())
        self.assertFalse(self.context.paths.claude_settings.exists())
        self.assertIn('appearance.zsh',self.context.paths.zshrc.read_text())
        self.assertNotIn(str(self.source),repr(result.receipt))

    def test_update_survives_source_removal_and_other_feature_install(self):
        self.assertSuccess(self.install('appearance'))
        rule=self.installed_rule()
        self.source.unlink();self.png.unlink();self.context.appearance_config=None
        self.assertSuccess(lifecycle.update(self.context,self.runner))
        self.assertSuccess(self.install('shell',agents=('claude',)))
        self.assertSuccess(self.install('appearance'))
        self.assertEqual(self.installed_rule(),rule)

    def test_missing_first_config_and_bad_inputs_never_commit_appearance(self):
        for document in (None,'{private',{'projects':[]},dict(projects=[dict(self.rules['projects'][0],color='red')]),dict(projects=[dict(self.rules['projects'][0],icon='unknown')])):
            with self.subTest(document=document):
                self.context.appearance_config=self.source if document is not None else None
                if document is not None:self.source.write_text(document if isinstance(document,str) else json.dumps(document))
                before=self.snapshot();result=self.install('appearance')
                self.assertTrue(any(f.state=='conflict' for f in result.findings))
                self.assertEqual(self.snapshot(),before)
                self.assertNotIn('appearance',result.receipt.selection.features)

    def test_plan_dryrun_fingerprint_and_unmounted_root(self):
        before=self.snapshot();first=plan(self.context,self.selection('appearance'))
        self.assertFalse([f for f in first.changes.findings if f.state in lifecycle.BLOCKING])
        self.assertSuccess(lifecycle.install(self.context,self.selection('appearance'),self.runner,dry_run=True))
        self.assertEqual(self.snapshot(),before);self.assertEqual(self.runner.calls,[])
        self.rules['projects'][0]['color']='#FF0000';self.source.write_text(json.dumps(self.rules))
        self.assertNotEqual(first.fingerprint,plan(self.context,self.selection('appearance')).fingerprint)
        self.assertFalse((self.context.paths.home/'unmounted').exists())

    def test_changed_config_preserved_on_update_and_uninstall(self):
        self.assertSuccess(self.install('appearance'))
        self.context.appearance_config=None
        path=self.context.paths.config/'appearance.json';document=json.loads(path.read_text())
        document['projects'][0]['color']='#FFFFFF';path.write_text(json.dumps(document));before=path.read_bytes()
        result=lifecycle.update(self.context,self.runner)
        self.assertTrue(any(f.state=='conflict' for f in result.findings));self.assertEqual(path.read_bytes(),before)
        result=lifecycle.uninstall(self.context,{'appearance'},self.runner)
        self.assertTrue(any(f.code=='uninstall_changed' for f in result.findings));self.assertEqual(path.read_bytes(),before)

    def test_missing_sdk_blocks_without_write(self):
        self.context.capabilities-={'python:iterm2'};before=self.snapshot();result=self.install('appearance')
        self.assertTrue(any(f.state=='missing_dependency' for f in result.findings));self.assertEqual(self.snapshot(),before)

    def test_explicit_replacement_and_partial_uninstall_keep_other_consumers(self):
        self.assertSuccess(self.install('appearance','restore','status'))
        self.context.appearance_config=None
        self.assertSuccess(self.install('shell',agents=('claude',)))
        self.context.appearance_config=self.source
        self.rules['projects'][0]['color']='#FF0000';self.source.write_text(json.dumps(self.rules))
        self.assertSuccess(self.install('appearance'));self.assertEqual(self.installed_rule()['color'],'#FF0000')
        self.context.appearance_config=None
        self.assertSuccess(lifecycle.uninstall(self.context,{'appearance'},self.runner))
        text=self.context.paths.zshrc.read_text()
        self.assertNotIn('appearance.zsh',text);self.assertIn('codex.zsh',text);self.assertIn('iterm2_shell_integration.zsh',text)
        self.assertTrue((self.context.paths.data/'current/hook.py').exists())
        self.assertFalse(list((self.context.paths.data/'appearance/icons').glob('*.png')))

    def test_claude_only_is_unsupported_and_untouched(self):
        before=self.snapshot();result=self.install('appearance',agents=('claude',))
        self.assertTrue(any(f.code=='codex_only' for f in result.findings));self.assertEqual(self.snapshot(),before)

    def test_write_failure_rolls_back_checkpoint(self):
        from iterm2_utils import engine
        original=engine._write_file
        def fail(path,*args,**kwargs):
            if path==(self.context.paths.config/'appearance.json').resolve():raise OSError('PRIVATE')
            return original(path,*args,**kwargs)
        with patch.object(engine,'_write_file',side_effect=fail):result=self.install('appearance')
        self.assertNotIn('appearance',result.receipt.selection.features)
        self.assertFalse(list((self.context.paths.data/'appearance/icons').glob('*.png')))
        self.assertNotIn('codex.zsh',self.context.paths.zshrc.read_text() if self.context.paths.zshrc.exists() else '')
        self.assertNotIn('PRIVATE',repr(result))

    def test_invalid_png_structure_and_pixel_data_reject_without_writes(self):
        import struct, zlib
        def chunk(kind,data):
            return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
        header=chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))
        make=lambda pixels:b'\x89PNG\r\n\x1a\n'+header+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')
        for data in (b'not png',make(b'invalid pixels'),make(b'\x05abcd'),make(b'\x00abcd')[:-1],make(b'\x00abcd')+b'extra'):
            with self.subTest(data=data):
                self.png.write_bytes(data);before=self.snapshot();result=self.install('appearance')
                self.assertTrue(any(f.state=='conflict' for f in result.findings));self.assertEqual(self.snapshot(),before)

    def test_custom_png_bytes_change_fingerprint(self):
        first=plan(self.context,self.selection('appearance')).fingerprint
        self.png.write_bytes((self.context.paths.repo/'runtime/assets/appearance/android.png').read_bytes())
        self.assertNotEqual(first,plan(self.context,self.selection('appearance')).fingerprint)

    def test_corrupted_installed_json_and_changed_png_are_preserved(self):
        self.assertSuccess(self.install('appearance'));self.context.appearance_config=None
        icon=Path(self.installed_rule()['icon']);icon.write_bytes(b'private-broken-png')
        config=self.context.paths.config/'appearance.json';config.write_bytes(b'{private')
        before=self.snapshot();result=lifecycle.update(self.context,self.runner)
        self.assertTrue(any(f.state=='conflict' for f in result.findings));self.assertEqual(self.snapshot(),before)
        findings=lifecycle.doctor(self.context,result.receipt,self.runner)
        self.assertNotIn(str(self.context.paths.home),repr(findings));self.assertNotIn('private',repr(findings))

    def test_bad_replacement_keeps_previous_checkpoint_and_shared_shell(self):
        self.assertSuccess(self.install('appearance'))
        self.source.write_text('{private');before=self.snapshot();result=self.install('appearance')
        self.assertTrue(any(f.state=='conflict' for f in result.findings));self.assertEqual(self.snapshot(),before)
        self.assertIn('appearance',result.receipt.selection.features)

    def test_alias_blocks_appearance_without_partial_checkpoint(self):
        self.context.paths.zshrc.write_text('alias codex=other\n');before=self.snapshot()
        result=self.install('appearance')
        self.assertTrue(any(f.code=='shell_conflict' for f in result.findings));self.assertEqual(self.snapshot(),before)

    def test_pending_api_probe_is_distinct_and_failure_is_private(self):
        import subprocess
        self.assertSuccess(self.install('appearance'));self.context.appearance_config=None
        for response in ('unavailable','timeout','PRIVATE'):
            with self.subTest(response=response), patch.object(self.runner,'run',return_value=subprocess.CompletedProcess([],0,response,'')), patch('iterm2_utils.config.mcp.probe',side_effect=AssertionError('Wrong verifier')):
                result=lifecycle.reconcile_ui(self.context,'appearance_api',self.runner)
                self.assertTrue(result.receipt.pending_ui);self.assertNotIn('PRIVATE',repr(result.findings))
        with patch.object(self.runner,'run',return_value=subprocess.CompletedProcess([],0,'ready\n','')):
            result=lifecycle.reconcile_ui(self.context,'appearance_api',self.runner)
        self.assertFalse(result.receipt.pending_ui)
        self.assertFalse(lifecycle.update(self.context,self.runner).receipt.pending_ui)

    def test_uninstall_other_feature_keeps_appearance_shell_and_ownership(self):
        self.assertSuccess(self.install('appearance','shell'))
        self.context.appearance_config=None
        result=lifecycle.uninstall(self.context,{'shell'},self.runner);self.assertSuccess(result)
        self.assertEqual(result.receipt.selection.pairs,{'codex:appearance'})
        self.assertIn('appearance.zsh',self.context.paths.zshrc.read_text())
        self.assertNotIn('iterm2_shell_integration.zsh',self.context.paths.zshrc.read_text())
        self.assertTrue(any('codex:appearance' in r['owners'] and 'shared:runtime' in r['owners'] for r in result.receipt.resources))

    def test_reinstall_after_uninstall_accepts_empty_json_residue(self):
        self.assertSuccess(self.install('appearance'))
        icon = Path(self.installed_rule()['icon'])
        self.context.appearance_config = None
        removed = lifecycle.uninstall(self.context, {'appearance'}, self.runner)
        self.assertSuccess(removed)
        config = self.context.paths.config/'appearance.json'
        self.assertEqual(json.loads(config.read_text()), {})
        self.assertFalse(any(r['target'] == str(config.resolve()) for r in removed.receipt.resources))
        self.context.appearance_config = self.source
        installed = self.install('appearance')
        self.assertSuccess(installed)
        self.assertEqual(installed.receipt.selection.pairs, {'codex:appearance'})
        self.assertEqual(self.installed_rule()['icon'], str(icon))
        self.assertTrue(icon.exists())
        self.assertIn('appearance.zsh', self.context.paths.zshrc.read_text())

    def test_explicit_replacement_preserves_foreign_json_addresses(self):
        installed = self.install('appearance')
        self.assertSuccess(installed)
        config = self.context.paths.config/'appearance.json'
        document = json.loads(config.read_text())
        document['user_setting'] = {'private': 'keep'}
        config.write_text(json.dumps(document))
        self.rules['projects'][0]['color'] = '#FF0000'
        self.source.write_text(json.dumps(self.rules))
        before = self.snapshot()
        result = self.install('appearance')
        self.assertTrue(any(f.state == 'conflict' for f in result.findings))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(result.receipt, installed.receipt)

    def test_explicit_install_preserves_nonempty_unowned_config(self):
        config = self.context.paths.config/'appearance.json'
        config.parent.mkdir()
        config.write_text(json.dumps({'user_setting': 'keep'}))
        before = self.snapshot()
        result = self.install('appearance')
        self.assertTrue(any(f.state == 'conflict' for f in result.findings))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(result.receipt.selection.features)
