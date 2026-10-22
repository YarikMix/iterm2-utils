from tests.test_lifecycle import LifecycleFixture
from iterm2_utils import lifecycle, migration

class MigrationTests(LifecycleFixture):
    def test_legacy_status_reused_without_duplicate_hooks(self):
        self.context.paths.codex_home.mkdir()
        config=self.context.paths.codex_home/'config.toml'
        config.write_text('[plugins."iterm2-status@local"]\nenabled = true\n')
        self.context.installed={'codex-status':{'enabled':True}}
        before=config.read_bytes()
        result=self.install('status')
        self.assertSuccess(result)
        self.assertEqual(config.read_bytes(),before)
        self.assertFalse((self.context.paths.codex_home/'hooks.json').exists())
        self.assertFalse(self.context.paths.zshrc.exists())
        self.assertEqual(result.receipt.selection.features,{'status'})

    def test_adopt_legacy_is_required_for_transfer(self):
        self.context.paths.codex_home.mkdir()
        config=self.context.paths.codex_home/'config.toml'
        config.write_text('[plugins."iterm2-status@local"]\nenabled = true\n')
        self.context.installed={'codex-status':{'enabled':True}}
        self.assertEqual(migration.build(self.context,self.selection('status')).edits,[])
        selection=self.selection('status');selection.adopt_legacy=True
        result=lifecycle.install(self.context,selection,self.runner)
        self.assertSuccess(result)
        self.assertIn('enabled = false',config.read_text())
        lifecycle.uninstall(self.context,frozenset({'status'}),self.runner)
        self.assertIn('enabled = true',config.read_text())

    def test_exact_legacy_wrapper_migrates_and_restores_reversibly(self):
        p=self.context.paths.zshrc
        original='# foreign\n# >>> codex-iterm2-status >>>\n'+migration.STATUS_BODY+'\n# <<< codex-iterm2-status <<<\n'
        p.write_text(original)
        selection=self.selection('status');selection.adopt_legacy=True
        result=lifecycle.install(self.context,selection,self.runner)
        self.assertSuccess(result);self.assertNotIn('function codex {',p.read_text())
        self.assertSuccess(lifecycle.update(self.context,self.runner))
        self.assertSuccess(lifecycle.uninstall(self.context,frozenset({'status'}),self.runner))
        self.assertEqual(p.read_text(),original)

    def test_unknown_legacy_block_is_not_adopted(self):
        p=self.context.paths.zshrc
        p.write_text('# >>> codex-iterm2-status >>>\nfunction codex { arbitrary; }\n# <<< codex-iterm2-status <<<\n')
        before=p.read_bytes();selection=self.selection('status');selection.adopt_legacy=True
        result=lifecycle.install(self.context,selection,self.runner)
        self.assertTrue(any(f.state=='conflict' for f in result.findings));self.assertEqual(p.read_bytes(),before)
        self.assertNotIn('status',result.receipt.selection.features)

    def test_restore_source_requires_exact_content_not_matching_basename(self):
        import shlex
        p=self.context.paths.zshrc;source=self.context.paths.home/'foreign/codex-resume.zsh';source.parent.mkdir();source.write_text('arbitrary')
        p.write_text('# >>> codex-resume >>>\nsource '+shlex.quote(str(source))+'\n# <<< codex-resume <<<\n')
        before=p.read_bytes();selection=self.selection('restore');selection.adopt_legacy=True
        result=lifecycle.install(self.context,selection,self.runner)
        self.assertTrue(any(f.state=='conflict' for f in result.findings));self.assertEqual(p.read_bytes(),before)
        source.write_bytes((self.context.paths.repo/'runtime/codex_restore/codex-resume.zsh').read_bytes())
        self.assertSuccess(lifecycle.install(self.context,selection,self.runner))
        self.assertSuccess(lifecycle.uninstall(self.context,frozenset({'restore'}),self.runner))
        self.assertEqual(p.read_bytes(),before);self.assertTrue(source.exists())

    def test_two_legacy_blocks_are_adopted_as_one_dispatcher_checkpoint(self):
        import shlex
        source=self.context.paths.home/'legacy source/codex-resume.zsh';source.parent.mkdir()
        source.write_bytes((self.context.paths.repo/'runtime/codex_restore/codex-resume.zsh').read_bytes())
        old='# >>> codex-iterm2-status >>>\n'+migration.STATUS_BODY+'\n# <<< codex-iterm2-status <<<\n'
        old+='# >>> codex-resume >>>\nsource '+shlex.quote(str(source))+'\n# <<< codex-resume <<<\n'
        self.context.paths.zshrc.write_text(old)
        selection=self.selection('status','restore');selection.adopt_legacy=True
        result=lifecycle.install(self.context,selection,self.runner)
        self.assertSuccess(result);self.assertEqual(result.receipt.selection.features,{'status','restore'})
        self.assertEqual(self.context.paths.zshrc.read_text().count('source '),2)
        self.assertSuccess(lifecycle.uninstall(self.context,frozenset({'status','restore'}),self.runner))
        self.assertEqual(self.context.paths.zshrc.read_text(),old)

    def test_legacy_order_and_placement_preserved_across_foreign_lines(self):
        import shlex
        source=self.context.paths.home/'legacy/codex-resume.zsh';source.parent.mkdir()
        source.write_bytes((self.context.paths.repo/'runtime/codex_restore/codex-resume.zsh').read_bytes())
        status='# >>> codex-iterm2-status >>>\n'+migration.STATUS_BODY+'\n# <<< codex-iterm2-status <<<\n'
        restore='# >>> codex-resume >>>\nsource '+shlex.quote(str(source))+'\n# <<< codex-resume <<<\n'
        for middle in ('','export BETWEEN=1\n'):
            with self.subTest(middle=bool(middle)):
                old='export BEFORE=1\n'+restore+middle+status+'export AFTER=1\n'
                self.context.paths.zshrc.write_text(old)
                selection=self.selection('status','restore');selection.adopt_legacy=True
                self.assertSuccess(lifecycle.install(self.context,selection,self.runner))
                self.assertSuccess(lifecycle.update(self.context,self.runner))
                self.assertSuccess(lifecycle.uninstall(self.context,frozenset({'status','restore'}),self.runner))
                self.assertEqual(self.context.paths.zshrc.read_text(),old)

    def test_changed_or_ambiguous_legacy_anchor_fails_closed(self):
        p=self.context.paths.zshrc
        p.write_text('export BEFORE=1\n# >>> codex-iterm2-status >>>\n'+migration.STATUS_BODY+'\n# <<< codex-iterm2-status <<<\nexport AFTER=1\n')
        selection=self.selection('status');selection.adopt_legacy=True
        self.assertSuccess(lifecycle.install(self.context,selection,self.runner))
        p.write_text(p.read_text().replace('export AFTER=1','export INSERTED=1\nexport AFTER=1'))
        before=p.read_bytes()
        result=lifecycle.uninstall(self.context,frozenset({'status'}),self.runner)
        self.assertTrue(any(f.state=='conflict' for f in result.findings))
        self.assertEqual(p.read_bytes(),before)
        self.assertTrue(any(f.code=='legacy_placement_conflict' for f in result.findings))
        self.assertEqual(result.receipt.selection.features,{'status'})
        self.assertTrue((self.context.paths.data/'current/hook.py').exists())

    def test_legacy_receipt_contains_only_anchor_hashes(self):
        from iterm2_utils import state
        p=self.context.paths.zshrc
        p.write_text('export FOREIGN_TOKEN=DO_NOT_PERSIST\n# >>> codex-iterm2-status >>>\n'+migration.STATUS_BODY+'\n# <<< codex-iterm2-status <<<\n')
        selection=self.selection('status');selection.adopt_legacy=True
        self.assertSuccess(lifecycle.install(self.context,selection,self.runner))
        self.assertNotIn('DO_NOT_PERSIST',(self.context.paths.data/'receipt.json').read_text())
        receipt=state.load(self.context.paths.data/'receipt.json')
        resource=next(r for r in receipt.resources if r['kind']=='zsh' and r['locator']['name']=='legacy-status')
        self.assertEqual(len(resource['locator']['placement']['before']),64)
        resource['locator']['placement']['raw_line']='DO_NOT_PERSIST'
        with self.assertRaises(ValueError):state.validate(receipt)

    def restore_hooks_fixture(self):
        import json, shlex
        p=self.context.paths
        source=p.home/'legacy source/codex-resume.zsh';source.parent.mkdir()
        source.write_bytes((p.repo/'runtime/codex_restore/codex-resume.zsh').read_bytes())
        p.zshrc.write_text('# >>> codex-resume >>>\nsource '+shlex.quote(str(source))+'\n# <<< codex-resume <<<\n')
        exact={'hooks':[{'type':'command','command':shlex.quote(str(source.parent/'codex-sessions'))+' hook','timeout':3}]}
        foreign={'hooks':[{'type':'command','command':'/foreign/codex-sessions hook','timeout':3}]}
        p.codex_home.mkdir();path=p.codex_home/'hooks.json'
        document={'foreign':'keep','hooks':{event:[foreign,exact] for event in ('SessionStart','UserPromptSubmit','Stop')}}
        path.write_text(json.dumps(document))
        return path,exact,foreign

    def test_legacy_restore_hooks_transfer_exactly_and_restore_after_update(self):
        import json
        path,exact,foreign=self.restore_hooks_fixture()
        selection=self.selection('restore');selection.adopt_legacy=True
        result=lifecycle.install(self.context,selection,self.runner);self.assertSuccess(result)
        current=json.loads(path.read_text())
        for event in ('SessionStart','UserPromptSubmit','Stop'):
            self.assertNotIn(exact,current['hooks'][event]);self.assertIn(foreign,current['hooks'][event])
            self.assertEqual(len(current['hooks'][event]),2)
        self.assertSuccess(lifecycle.update(self.context,self.runner))
        added={'hooks':[{'type':'command','command':'foreign-later'}]}
        current=json.loads(path.read_text());current['hooks']['Stop'].insert(0,added);path.write_text(json.dumps(current))
        self.assertSuccess(lifecycle.uninstall(self.context,frozenset({'restore'}),self.runner))
        current=json.loads(path.read_text())
        self.assertEqual(current['hooks']['Stop'],[added,foreign,exact])
        for event in ('SessionStart','UserPromptSubmit'):
            self.assertEqual(current['hooks'][event],[foreign,exact])
        self.assertEqual(current['foreign'],'keep')

    def test_changed_known_restore_hook_requires_manual_resolution(self):
        import json
        path,exact,foreign=self.restore_hooks_fixture()
        current=json.loads(path.read_text());current['hooks']['Stop'][1]['hooks'][0]['timeout']=99;path.write_text(json.dumps(current))
        before=self.snapshot()
        selection=self.selection('restore');selection.adopt_legacy=True
        result=lifecycle.install(self.context,selection,self.runner)
        self.assertTrue(any(f.code=='legacy_restore_hook_conflict' for f in result.findings))
        self.assertNotIn('restore',result.receipt.selection.features)
        self.assertEqual(self.snapshot(),before)

    def test_legacy_restore_hooks_are_untouched_without_adoption(self):
        self.restore_hooks_fixture()
        before=self.snapshot()
        result=self.install('restore')
        self.assertTrue(any(f.state=='conflict' for f in result.findings))
        self.assertEqual(self.snapshot(),before)

    def test_mixed_legacy_hook_group_is_preserved_as_a_conflict(self):
        import json
        path,exact,foreign=self.restore_hooks_fixture()
        current=json.loads(path.read_text())
        current['hooks']['Stop'][1]['hooks'].append({'type':'command','command':'foreign-inside-group'})
        path.write_text(json.dumps(current));before=self.snapshot()
        selection=self.selection('restore');selection.adopt_legacy=True
        result=lifecycle.install(self.context,selection,self.runner)
        self.assertTrue(any(f.code=='legacy_restore_hook_conflict' for f in result.findings))
        self.assertEqual(self.snapshot(),before)

    def test_failed_restore_migration_restores_old_hooks_and_shell(self):
        import json
        from unittest.mock import patch
        from iterm2_utils import engine
        path,exact,foreign=self.restore_hooks_fixture()
        shell_before=self.context.paths.zshrc.read_bytes()
        hooks_before=json.loads(path.read_text())
        original=engine._write_file
        def fail_runtime_settings(target,*args,**kwargs):
            if target==(self.context.paths.config/'runtime.json').resolve():
                raise OSError('simulated write failure')
            return original(target,*args,**kwargs)
        selection=self.selection('restore');selection.adopt_legacy=True
        with patch.object(engine,'_write_file',side_effect=fail_runtime_settings):
            result=lifecycle.install(self.context,selection,self.runner)
        self.assertNotIn('restore',result.receipt.selection.features)
        current=json.loads(path.read_text())
        for event in ('SessionStart','UserPromptSubmit','Stop'):
            self.assertEqual(current['hooks'][event],hooks_before['hooks'][event])
        self.assertEqual(self.context.paths.zshrc.read_bytes(),shell_before)
