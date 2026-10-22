import os
import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from iterm2_utils import engine
from iterm2_utils.models import *


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        p = self.root
        self.context = Context(Paths(p, p/'zshrc', p/'codex', p/'claude.json', p/'config', p/'cache', p/'data', p/'profiles', p), {}, {}, frozenset(), {}, {})
        self.selection = Selection(frozenset({'codex'}), frozenset({'clipboard'}), frozenset(), 'Default')

    def plan(self, edits):
        return Plan(self.selection, ChangeSet(edits, [], []), 'fixture')

    def test_cas_refuses_concurrent_edit(self):
        p = self.root/'settings.json'
        p.write_bytes(b'{"ours":2}')
        result = engine.apply(self.plan([FileEdit(p, b'{"ours":0}', b'{"ours":1}', 0o600, 'clipboard')]), self.context, None)
        self.assertEqual(p.read_bytes(), b'{"ours":2}')
        self.assertTrue(any(f.state == 'conflict' for f in result.findings))

    def test_symlink_target_mode_preserved(self):
        p, target = self.root/'settings.json', self.root/'real.json'
        target.write_bytes(b'{"ours":0}')
        target.chmod(0o640)
        p.symlink_to(target)
        result = engine.apply(self.plan([FileEdit(p, target.read_bytes(), b'{"ours":1}', 0o600, 'clipboard')]), self.context, None)
        self.assertTrue(p.is_symlink())
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)
        self.assertEqual(len(result.receipt.resources), 1)
        backups = list((self.context.paths.data/'backups').iterdir())
        self.assertTrue(backups)
        for backup in backups:
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.context.paths.data.stat().st_mode), 0o700)

    def test_second_write_failure_rolls_back_only_own_first_write(self):
        first, second = self.root/'one', self.root/'two'
        first.write_bytes(b'old'); second.write_bytes(b'old')
        original = engine._write_file
        def fail(path, *args, **kwargs):
            if path == second.resolve():
                first.write_bytes(b'concurrent user bytes')
                raise OSError('PRIVATE_FAILURE_MARKER')
            return original(path, *args, **kwargs)
        with patch.object(engine, '_write_file', side_effect=fail):
            result = engine.apply(self.plan([FileEdit(first,b'old',b'new',0o600,'clipboard'), FileEdit(second,b'old',b'new',0o600,'clipboard')]), self.context, None)
        concurrent_user_bytes = b'concurrent user bytes'
        destination = first
        assert destination.read_bytes() == concurrent_user_bytes
        self.assertTrue(any(f.code == 'rollback_unresolved' for f in result.findings))
        self.assertNotIn('PRIVATE_FAILURE_MARKER', str(result.findings))

    def test_uninstall_preserves_user_changed_value(self):
        p = self.root/'settings.json'
        p.write_bytes(b'{"ours":0,"other":0}')
        result = engine.apply(self.plan([FileEdit(p,p.read_bytes(),b'{"ours":1,"other":0}',0o600,'clipboard')]), self.context, None)
        p.write_bytes(b'{"ours":9,"other":7}')
        reverted = engine.revert(result.receipt,self.context,None,frozenset({'clipboard'}))
        self.assertEqual(p.read_bytes(), b'{"ours":9,"other":7}')
        self.assertTrue(reverted.findings)

    def test_uninstall_keeps_unrelated_json_additions(self):
        import json
        p = self.root/'settings.json'
        p.write_bytes(b'{"ours":0}')
        result = engine.apply(self.plan([FileEdit(p,p.read_bytes(),b'{"ours":1}',0o600,'clipboard')]), self.context, None)
        p.write_bytes(b'{"ours":1,"new":7}')
        result = engine.revert(result.receipt,self.context,None,frozenset({'clipboard'}))
        self.assertEqual(json.loads(p.read_bytes()), {'ours':0,'new':7})
        self.assertEqual(result.receipt.resources, [])

    def test_interrupted_transaction_recovers_before_next_mutation(self):
        p,q = self.root/'one',self.root/'two'
        p.write_bytes(b'old');q.write_bytes(b'old')
        original = engine._write_file
        def interrupt(path,*args,**kwargs):
            if path == q.resolve():
                raise KeyboardInterrupt()
            return original(path,*args,**kwargs)
        with patch.object(engine,'_write_file',side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                engine.apply(self.plan([FileEdit(p,b'old',b'new',0o600,'clipboard'),FileEdit(q,b'old',b'new',0o600,'clipboard')]),self.context,None)
        self.assertEqual(p.read_bytes(),b'new')
        result = engine.apply(self.plan([FileEdit(q,b'old',b'final',0o600,'clipboard')]),self.context,None)
        self.assertEqual(p.read_bytes(),b'old')
        self.assertEqual(q.read_bytes(),b'final')
        self.assertFalse(result.findings)
        self.assertFalse((self.context.paths.data/'journal').exists())

    def test_symlink_creation_switch_and_inverse(self):
        from iterm2_utils.models import SymlinkEdit
        p = self.root/'current'
        with patch.object(engine.os,'replace',wraps=os.replace) as replace:
            result = engine.apply(self.plan([SymlinkEdit(p,None,'releases/v1','clipboard')]),self.context,None)
        self.assertEqual(os.readlink(p),'releases/v1')
        self.assertTrue(any(Path(call.args[1]) == p.parent.resolve()/p.name for call in replace.call_args_list))
        result = engine.apply(self.plan([SymlinkEdit(p,'releases/v1','releases/v2','clipboard')]),self.context,None)
        self.assertEqual(os.readlink(p),'releases/v2')
        result = engine.revert(result.receipt,self.context,None,frozenset({'clipboard'}))
        self.assertFalse(p.is_symlink())
        self.assertFalse(result.findings)

    def test_concurrent_symlink_preserved_and_regular_file_refused(self):
        from iterm2_utils.models import SymlinkEdit
        p = self.root/'current'
        result = engine.apply(self.plan([SymlinkEdit(p,None,'releases/v1','clipboard')]),self.context,None)
        p.unlink();p.symlink_to('user/release')
        result = engine.revert(result.receipt,self.context,None,frozenset({'clipboard'}))
        self.assertEqual(os.readlink(p),'user/release')
        self.assertTrue(result.findings)
        q = self.root/'regular';q.write_bytes(b'user file')
        result = engine.apply(self.plan([SymlinkEdit(q,None,'release','clipboard')]),self.context,None)
        self.assertEqual(q.read_bytes(),b'user file')
        self.assertTrue(result.findings)

    def test_registration_without_backend_preflights_before_file_write(self):
        p = self.root/'one'
        result = engine.apply(self.plan([FileEdit(p,None,b'new',0o600,'clipboard'),RegistrationEdit('codex','iterm2',None,{'command':'fixture'},'mcp')]),self.context,None)
        self.assertFalse(p.exists())
        self.assertTrue(result.findings)

    def test_second_write_failure_restores_first_without_concurrency(self):
        p,q = self.root/'one',self.root/'two'
        p.write_bytes(b'old');q.write_bytes(b'old')
        original = engine._write_file
        def fail(path,*args,**kwargs):
            if path == q.resolve():
                raise OSError('private')
            return original(path,*args,**kwargs)
        with patch.object(engine,'_write_file',side_effect=fail):
            result = engine.apply(self.plan([FileEdit(p,b'old',b'new',0o600,'clipboard'),FileEdit(q,b'old',b'new',0o600,'clipboard')]),self.context,None)
        self.assertEqual(p.read_bytes(),b'old')
        self.assertEqual(q.read_bytes(),b'old')
        self.assertEqual(result.receipt.resources,[])
        self.assertFalse((self.context.paths.data/'journal').exists())

    def test_recovery_conflict_keeps_journal_and_blocks_next_write(self):
        p,q = self.root/'one',self.root/'two'
        p.write_bytes(b'old');q.write_bytes(b'old')
        original = engine._write_file
        def interrupt(path,*args,**kwargs):
            if path == q.resolve():
                raise KeyboardInterrupt()
            return original(path,*args,**kwargs)
        with patch.object(engine,'_write_file',side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                engine.apply(self.plan([FileEdit(p,b'old',b'new',0o600,'clipboard'),FileEdit(q,b'old',b'new',0o600,'clipboard')]),self.context,None)
        p.write_bytes(b'user modified')
        result = engine.apply(self.plan([FileEdit(q,b'old',b'final',0o600,'clipboard')]),self.context,None)
        self.assertEqual(p.read_bytes(),b'user modified')
        self.assertEqual(q.read_bytes(),b'old')
        self.assertTrue((self.context.paths.data/'journal').exists())
        self.assertTrue(any(f.code=='rollback_unresolved' for f in result.findings))

    def test_toml_uninstall_keeps_user_additions_and_receipt_excludes_foreign_values(self):
        import tomllib
        p = self.root/'config.toml'
        before = b'[tui]\ncopy_on_select="always"\n[other]\nsecret="FOREIGN_SECRET_MARKER"\n'
        p.write_bytes(before)
        result = engine.apply(self.plan([FileEdit(p,before,before.replace(b'always',b'never'),0o600,'clipboard')]),self.context,None)
        self.assertNotIn('FOREIGN_SECRET_MARKER',str(result.receipt.resources))
        p.write_bytes(p.read_bytes()+b'added=42\n')
        result = engine.revert(result.receipt,self.context,None,frozenset({'clipboard'}))
        self.assertEqual(tomllib.loads(p.read_text())['other']['added'],42)
        self.assertEqual(tomllib.loads(p.read_text())['tui']['copy_on_select'],'always')
        self.assertFalse(result.findings)

    def test_reapply_is_idempotent_and_retains_original_inverse(self):
        p=self.root/'settings.json';p.write_bytes(b'{"ours":0}')
        edit=FileEdit(p,p.read_bytes(),b'{"ours":1}',0o600,'clipboard')
        one=engine.apply(self.plan([edit]),self.context,None)
        two=engine.apply(self.plan([edit]),self.context,None)
        self.assertEqual(one.receipt,two.receipt)
        result=engine.revert(two.receipt,self.context,None,frozenset({'clipboard'}))
        self.assertEqual(__import__('json').loads(p.read_bytes()),{'ours':0})
        self.assertFalse(result.findings)

    def test_unsupported_toml_fails_before_any_target_write(self):
        first=self.root/'one'; first.write_bytes(b'old')
        p=self.root/'config.toml';p.write_bytes(b'tui = {copy_on_select="always"}\n')
        result=engine.apply(self.plan([FileEdit(first,b'old',b'new',0o600,'clipboard'),FileEdit(p,p.read_bytes(),b'[tui]\ncopy_on_select="never"\n',0o600,'clipboard')]),self.context,None)
        self.assertEqual(first.read_bytes(),b'old')
        self.assertTrue(result.findings)

    def test_shared_resource_only_explicit_consumers_retain_it(self):
        p=self.root/'shared'
        selected=Selection(frozenset({'codex'}),frozenset({'shell','status','clipboard'}),frozenset(),'Default')
        changes=ChangeSet([FileEdit(p,None,b'runtime',0o600,'shared:runtime')],[],[],{'shared:runtime':frozenset({'shell','status'})})
        result=engine.apply(Plan(selected,changes,'fixture'),self.context,None)
        self.assertEqual(set(result.receipt.resources[0]['owners']),{'shared:runtime','shell','status'})
        result=engine.revert(result.receipt,self.context,None,frozenset({'shell'}))
        self.assertTrue(p.exists())
        self.assertEqual(set(result.receipt.resources[0]['owners']),{'shared:runtime','status'})
        result=engine.revert(result.receipt,self.context,None,frozenset({'status'}))
        self.assertFalse(p.exists())
        self.assertEqual(result.receipt.resources,[])

    def test_shared_edit_requires_explicit_valid_consumers_before_writes(self):
        p=self.root/'shared'
        result=engine.apply(self.plan([FileEdit(p,None,b'runtime',0o600,'shared:runtime')]),self.context,None)
        self.assertFalse(p.exists())
        self.assertTrue(result.findings)

    def test_boolean_and_integer_are_distinct_cas_values(self):
        p=self.root/'settings.json';p.write_bytes(b'{"ours":true}')
        result=engine.apply(self.plan([FileEdit(p,b'{"ours":1}',b'{"ours":2}',0o600,'clipboard')]),self.context,None)
        self.assertEqual(p.read_bytes(),b'{"ours":true}')
        self.assertTrue(result.findings)

    def test_committed_journal_finishes_receipt_after_interruption(self):
        from iterm2_utils import state
        p=self.root/'one'
        save=state.save
        def interrupt(path,receipt):
            if path == self.context.paths.data/'receipt.json':
                raise KeyboardInterrupt()
            return save(path,receipt)
        with patch.object(state,'save',side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                engine.apply(self.plan([FileEdit(p,None,b'installed',0o600,'clipboard')]),self.context,None)
        self.assertEqual(p.read_bytes(),b'installed')
        result=engine.apply(self.plan([FileEdit(p,b'installed',b'installed',0o600,'clipboard')]),self.context,None)
        self.assertEqual(len(result.receipt.resources),1)
        self.assertFalse(result.findings)
        self.assertFalse((self.context.paths.data/'journal').exists())

    def test_change_during_staging_preserves_concurrent_bytes(self):
        from iterm2_utils import state
        p=self.root/'settings.json';p.write_bytes(b'{"ours":0}')
        durable=state.durable_write
        def concurrent(path,*args,**kwargs):
            if path == p.resolve():
                p.write_bytes(b'{"ours":9,"user":7}')
            return durable(path,*args,**kwargs)
        with patch.object(state,'durable_write',side_effect=concurrent):
            result=engine.apply(self.plan([FileEdit(p,b'{"ours":0}',b'{"ours":1}',0o600,'clipboard')]),self.context,None)
        self.assertEqual(p.read_bytes(),b'{"ours":9,"user":7}')
        self.assertTrue(result.findings)

    def test_symlink_shell_configuration_uses_logical_path_for_address_inverse(self):
        from iterm2_utils.config import zshrc
        target=self.root/'dotfiles';target.write_bytes(b'export USER_THING=yes\n')
        p=self.root/'.zshrc';p.symlink_to(target)
        result=engine.apply(self.plan([FileEdit(p,p.read_bytes(),zshrc.block(p.read_bytes(),'shell','source /fixture'),0o600,'clipboard')]),self.context,None)
        target.write_bytes(target.read_bytes()+b'export USER_ADDITION=yes\n')
        result=engine.revert(result.receipt,self.context,None,frozenset({'clipboard'}))
        self.assertEqual(target.read_bytes(),b'export USER_THING=yes\nexport USER_ADDITION=yes\n')
        self.assertTrue(p.is_symlink())
        self.assertFalse(result.findings)

    def test_mode_change_does_not_duplicate_address_ownership_on_update(self):
        import json
        p=self.root/'settings.json';p.write_bytes(b'{"ours":0}')
        result=engine.apply(self.plan([FileEdit(p,p.read_bytes(),b'{"ours":1}',0o600,'clipboard')]),self.context,None)
        p.chmod(0o640)
        result=engine.apply(self.plan([FileEdit(p,p.read_bytes(),b'{"ours":2}',0o600,'clipboard')]),self.context,None)
        self.assertEqual(len(result.receipt.resources),1)
        result=engine.revert(result.receipt,self.context,None,frozenset({'clipboard'}))
        self.assertEqual(json.loads(p.read_bytes()),{'ours':0})
        self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o640)
        self.assertFalse(result.findings)

    def test_owned_address_change_between_value_and_raw_read_is_preserved(self):
        p=self.root/'settings.json';p.write_bytes(b'{"ours":0}')
        read=engine._read
        raced=False
        def concurrent(resource,runner,context):
            nonlocal raced
            value=read(resource,runner,context)
            import inspect
            if inspect.currentframe().f_back.f_code.co_name == '_set' and not raced:
                raced=True
                p.write_bytes(b'{"ours":9,"user":7}')
            return value
        with patch.object(engine,'_read',new=concurrent):
            result=engine.apply(self.plan([FileEdit(p,b'{"ours":0}',b'{"ours":1}',0o600,'clipboard')]),self.context,None)
        self.assertTrue(raced)
        self.assertEqual(p.read_bytes(),b'{"ours":9,"user":7}')
        self.assertTrue(result.findings)

    def test_fresh_unchanged_json_and_toml_plans_retain_ownership_and_consumers(self):
        for suffix,old,new in (('json',b'{"ours":0}',b'{"ours":1}'),('toml',b'[tui]\nours=0\n',b'[tui]\nours=1\n')):
            with self.subTest(suffix=suffix):
                p=self.root/('fresh.'+suffix);p.write_bytes(old)
                selection=Selection(frozenset({'codex'}),frozenset({'shell'}),frozenset(),'Default')
                changes=ChangeSet([FileEdit(p,old,new,0o600,'shared:runtime')],[],[],{'shared:runtime':frozenset({'shell'})})
                one=engine.apply(Plan(selection,changes,'fixture'),self.context,None)
                self.assertFalse(one.findings)
                current=p.read_bytes()
                selection=Selection(frozenset({'codex'}),frozenset({'status','clipboard'}),frozenset(),'Default')
                changes=ChangeSet([FileEdit(p,current,current,0o600,'shared:runtime')],[],[],{'shared:runtime':frozenset({'status'})})
                two=engine.apply(Plan(selection,changes,'fixture'),self.context,None)
                self.assertFalse(two.findings)
                owned=next(r for r in two.receipt.resources if r['target']==str(p.resolve()))
                self.assertEqual(set(owned['owners']),{'shared:runtime','shell','status'})
                self.assertEqual(owned['before'],one.receipt.resources[-1]['before'])
                self.assertEqual(p.read_bytes(),current)

    def test_fresh_noop_does_not_adopt_another_features_address(self):
        p=self.root/'settings.json';p.write_bytes(b'{"ours":0,"foreign":7}')
        one=engine.apply(self.plan([FileEdit(p,p.read_bytes(),b'{"ours":1,"foreign":7}',0o600,'clipboard')]),self.context,None)
        selection=Selection(frozenset({'codex'}),frozenset({'status'}),frozenset(),'Default')
        current=p.read_bytes()
        two=engine.apply(Plan(selection,ChangeSet([FileEdit(p,current,current,0o600,'status')],[],[]),'fixture'),self.context,None)
        self.assertFalse(two.findings)
        self.assertEqual(two.receipt.resources,one.receipt.resources)
        self.assertEqual(two.receipt.resources[0]['owners'],['clipboard'])
