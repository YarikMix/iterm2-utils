import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from iterm2_utils import lifecycle, state
from iterm2_utils.models import Context, Paths, Selection
from tests.support import FakeRunner


class LifecycleFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        p = Path(self.tmp.name)
        paths = Paths(p, p/'.zshrc', p/'codex', p/'claude/settings.json', p/'config', p/'cache', p/'data', p/'profiles', Path(__file__).resolve().parents[1])
        self.context = Context(paths, {n:p/'bin'/n for n in ('iterm2','it2','zsh','python3','codex','claude','terminal-notifier','fzf','uvx','osascript')}, {'fzf':'0.60.0','python3':'3.11.9','iterm2':'3.7.6'}, frozenset({'macos','codex:no-daemon','iterm2:session-status','iterm2:cc-status-codex','codex:approval-notifications','codex:alt-enter','claude:alt-enter'}), {'Default':{'Name':'Default','Keyboard Map':{'foreign':{'Action':1}}}}, {})
        self.runner = FakeRunner(); self.preferences = {}; self.registrations = {}
        def pref_read(runner, domain, key):
            return {'exists':key in self.preferences,'value':self.preferences.get(key)}
        def pref_write(runner, domain, key, value):
            if value['exists']: self.preferences[key] = value['value']
            else: self.preferences.pop(key,None)
        def reg_inspect(agent,name,context,runner): return self.registrations.get((agent,name))
        def reg_apply(edit,context,runner):
            if edit.after is None: self.registrations.pop((edit.agent,edit.name),None)
            else: self.registrations[edit.agent,edit.name] = edit.after
        for name, side in [('preferences.read',pref_read),('preferences.write',pref_write),('registration_adapter.inspect',reg_inspect),('registration_adapter.apply',reg_apply)]:
            mock = patch('iterm2_utils.engine.'+name,side_effect=side);mock.start();self.addCleanup(mock.stop)

    def external_native(self):
        """Materialize real discovery inputs, including the selected fake bundle."""
        import shlex
        from runtime.events import CODEX_EVENTS
        binary=self.context.executables['iterm2']/'Contents/Resources/utilities/cc-status'
        binary.parent.mkdir(parents=True,exist_ok=True)
        binary.write_text('#!/bin/sh\nexit 0\n');binary.chmod(0o700)
        path=self.context.paths.codex_home/'hooks.json'
        path.parent.mkdir(exist_ok=True)
        document=json.loads(path.read_bytes()) if path.exists() else {'hooks':{}}
        native={event:[{'hooks':[{'type':'command','command':shlex.join([str(binary),'--agent','codex']),'timeout':3}]}]
                for event in CODEX_EVENTS if event not in {'PreCompact','PostCompact'}}
        for event,entries in native.items():
            document['hooks'].setdefault(event,[]).extend(entries)
        path.write_text(json.dumps(document))
        return native

    def selection(self, *features, agents=('codex',), shortcuts=()):
        return Selection(frozenset(agents),frozenset(features),frozenset(shortcuts),'Default')

    def snapshot(self):
        return {str(p.relative_to(self.context.paths.home)):p.read_bytes() for p in self.context.paths.home.rglob('*') if p.is_file()}

    def install(self,*features,**kwargs): return lifecycle.install(self.context,self.selection(*features,**kwargs),self.runner)

    def assertSuccess(self,outcome):
        self.assertFalse([f for f in outcome.findings if f.state in {'conflict','unavailable','missing_dependency'}],outcome.findings)


class LifecycleTests(LifecycleFixture):
    def test_failed_feature_does_not_rollback_independent_completed_feature(self):
        self.context.capabilities -= {'iterm2:cc-status-codex'}
        result = self.install('status','notifications')
        self.assertNotIn('status',result.receipt.selection.features)
        self.assertIn('notifications',result.receipt.selection.features)
        self.assertTrue((self.context.paths.codex_home/'hooks.json').exists())

    def test_partial_uninstall_retains_shared_runtime(self):
        self.assertSuccess(self.install('status','shell'))
        result = lifecycle.uninstall(self.context,frozenset({'shell'}),self.runner)
        self.assertSuccess(result)
        self.assertEqual(result.receipt.selection.features,{'status'})
        text=self.context.paths.zshrc.read_text()
        self.assertIn('codex.zsh',text); self.assertNotIn('iterm2_shell_integration.zsh',text)
        self.assertTrue((self.context.paths.data/'current/hook.py').exists())

    def test_partial_clipboard_removal_recomposes_profile(self):
        self.assertSuccess(self.install('clipboard','shortcuts',shortcuts=('resume',)))
        result=lifecycle.uninstall(self.context,frozenset({'clipboard'}),self.runner)
        self.assertSuccess(result)
        profile=json.loads((self.context.paths.profiles/'iterm2-utils.json').read_text())['Profiles'][0]
        self.assertEqual(set(profile['Keyboard Map']),{'foreign','0x52-0x120000-0xf-0x1'})
        lifecycle.uninstall(self.context,frozenset({'shortcuts'}),self.runner)
        self.assertFalse((self.context.paths.profiles/'iterm2-utils.json').exists())

    def test_readonly_plan_and_dryrun_do_not_create_backups(self):
        from iterm2_utils.planner import plan
        before=self.snapshot()
        plan(self.context,self.selection('status','shell'))
        lifecycle.install(self.context,self.selection('status','shell'),self.runner,dry_run=True)
        self.assertEqual(self.snapshot(),before)

    def test_update_with_no_receipt_has_no_implicit_full_selection(self):
        before=self.snapshot()
        result=lifecycle.update(self.context,self.runner)
        self.assertEqual(result.receipt.selection.features,frozenset())
        self.assertEqual(self.snapshot(),before)
        self.assertTrue(any(f.code=='ownership_unavailable' for f in result.findings))

    def test_user_modified_mcp_is_not_removed(self):
        self.assertSuccess(self.install('mcp'))
        key=next(iter(self.registrations));self.registrations[key]={'command':'user'}
        result=lifecycle.uninstall(self.context,frozenset({'mcp'}),self.runner)
        self.assertEqual(self.registrations[key],{'command':'user'})
        self.assertTrue(any(f.code=='uninstall_changed' for f in result.findings))

    def test_all_features_repeat_update_partial_full_uninstall_preserves_foreign(self):
        p=self.context.paths
        p.codex_home.mkdir();(p.codex_home/'hooks.json').write_text(json.dumps({'foreign':'keep','hooks':{'Stop':[{'hooks':[{'type':'command','command':'foreign-hook'}]}]}}))
        p.cache.mkdir();(p.cache/'keep').write_text('cache');(p.codex_home/'conversation.jsonl').write_text('conversation')
        features=('clipboard','shortcuts','shell','status','notifications','restore','mcp')
        self.assertSuccess(self.install(*features,shortcuts=('resume',)))
        profile=p.profiles/'iterm2-utils.json';mtime=profile.stat().st_mtime_ns
        self.assertSuccess(self.install(*features,shortcuts=('resume',)))
        self.assertSuccess(lifecycle.update(self.context,self.runner))
        self.assertEqual(profile.stat().st_mtime_ns,mtime)
        self.assertSuccess(lifecycle.uninstall(self.context,frozenset({'clipboard','shell','status'}),self.runner))
        settings=json.loads((p.config/'runtime.json').read_text());self.assertFalse(settings['status']);self.assertTrue(settings['notifications'])
        self.assertSuccess(lifecycle.uninstall(self.context,frozenset(features),self.runner))
        self.assertEqual(json.loads((p.codex_home/'hooks.json').read_text())['hooks']['Stop'],[{'hooks':[{'type':'command','command':'foreign-hook'}]}])
        self.assertTrue((p.cache/'keep').exists());self.assertTrue((p.codex_home/'conversation.jsonl').exists());self.assertTrue((p.data/'backups').exists())
        self.assertFalse(profile.exists())

    def test_foreign_hook_insertions_and_reordering_survive_uninstall(self):
        self.assertSuccess(self.install('status'))
        path=self.context.paths.codex_home/'hooks.json'
        document=json.loads(path.read_text())
        foreign={'hooks':[{'type':'command','command':'foreign-changed'}]}
        document['hooks']['Stop'].insert(0,foreign)
        document['extra']={'keep':True}
        path.write_text(json.dumps(document))
        self.assertSuccess(lifecycle.update(self.context,self.runner))
        self.assertSuccess(lifecycle.uninstall(self.context,frozenset({'status'}),self.runner))
        document=json.loads(path.read_text())
        self.assertEqual(document['hooks']['Stop'],[foreign]);self.assertEqual(document['extra'],{'keep':True})

    def test_duplicate_exact_owned_hook_is_preserved_as_conflict(self):
        self.install('status')
        path=self.context.paths.codex_home/'hooks.json';document=json.loads(path.read_text())
        document['hooks']['Stop'] *= 2;path.write_text(json.dumps(document));before=path.read_bytes()
        result=lifecycle.uninstall(self.context,frozenset({'status'}),self.runner)
        self.assertTrue(any(f.state=='conflict' for f in result.findings))
        self.assertEqual(path.read_bytes(),before)
        self.assertIn('status',result.receipt.selection.features)

    def test_unknown_alias_blocks_dispatcher_but_shell_marks_succeed(self):
        self.context.paths.zshrc.write_text('alias -g codex=custom\n')
        result=self.install('shell','status')
        self.assertEqual(result.receipt.selection.features,{'shell'})
        self.assertIn('alias -g codex=custom',self.context.paths.zshrc.read_text())
        self.assertNotIn('codex.zsh',self.context.paths.zshrc.read_text())

    def test_unavailable_shortcut_does_not_hide_independent_clipboard(self):
        self.context.capabilities -= {'codex:alt-enter'}
        result=self.install('clipboard','shortcuts',shortcuts=('alt-enter',))
        self.assertEqual(result.receipt.selection.features,{'clipboard'})
        self.assertEqual(result.receipt.selection.shortcuts,frozenset())

    def test_user_modified_profile_and_shell_are_preserved(self):
        self.install('clipboard','shell')
        profile=self.context.paths.profiles/'iterm2-utils.json'
        document=json.loads(profile.read_text());document['Profiles'][0]['UserSetting']='mine'
        profile.write_text(json.dumps(document));profile_before=profile.read_bytes()
        shell=self.context.paths.zshrc;shell.write_text(shell.read_text().replace('source ','# custom\n  source '));shell_before=shell.read_bytes()
        result=lifecycle.uninstall(self.context,frozenset({'clipboard','shell'}),self.runner)
        self.assertEqual(profile.read_bytes(),profile_before);self.assertEqual(shell.read_bytes(),shell_before)
        self.assertTrue(any(f.code=='uninstall_changed' for f in result.findings))

    def test_failure_rolls_back_only_current_feature_checkpoint(self):
        from iterm2_utils import engine
        original=engine._write_file
        def fail(path,*args,**kwargs):
            if path==(self.context.paths.codex_home/'hooks.json').resolve(): raise OSError('PRIVATE_ERROR')
            return original(path,*args,**kwargs)
        with patch.object(engine,'_write_file',side_effect=fail):
            result=self.install('shell','status')
        self.assertEqual(result.receipt.selection.features,{'shell'})
        self.assertNotIn('codex.zsh',self.context.paths.zshrc.read_text())
        self.assertNotIn('PRIVATE_ERROR',str(result))
        self.assertFalse((self.context.paths.codex_home/'hooks.json').exists())

    def test_update_preserves_exact_chosen_features_and_shortcuts(self):
        self.install('shortcuts',shortcuts=('resume',))
        result=lifecycle.update(self.context,self.runner)
        self.assertEqual(result.receipt.selection.features,{'shortcuts'})
        self.assertEqual(result.receipt.selection.shortcuts,{'resume'})
        self.assertFalse((self.context.paths.codex_home/'hooks.json').exists())

    def test_claude_all_applicable_features_have_no_codex_side_effects(self):
        self.assertSuccess(self.install('shell','shortcuts','status','notifications','mcp',agents=('claude',),shortcuts=('resume',)))
        self.assertFalse(self.context.paths.codex_home.exists())
        self.assertNotIn('codex.zsh',self.context.paths.zshrc.read_text())
        self.assertSuccess(lifecycle.uninstall(self.context,frozenset({'status','shell'}),self.runner))
        self.assertTrue((self.context.paths.data/'current/hook.py').exists())
        self.assertSuccess(lifecycle.uninstall(self.context,frozenset({'shortcuts','notifications','mcp'}),self.runner))
        self.assertFalse(self.context.paths.codex_home.exists())

    def test_unavailable_existing_feature_does_not_block_independent_update(self):
        self.assertSuccess(self.install('shell','mcp'))
        self.context.executables.pop('uvx')
        result=lifecycle.update(self.context,self.runner)
        checkpoints=[f.feature for f in result.findings if f.code=='feature_checkpoint']
        self.assertIn('shell',checkpoints)
        self.assertTrue(any(f.code=='uvx_missing' for f in result.findings))
        self.assertEqual(result.receipt.selection.features,{'shell','mcp'})

    def test_partial_uninstall_ignores_unrelated_modified_mcp(self):
        self.assertSuccess(self.install('shell','mcp'))
        key=next(iter(self.registrations));self.registrations[key]={'command':'user'}
        result=lifecycle.uninstall(self.context,frozenset({'shell'}),self.runner)
        self.assertSuccess(result)
        self.assertEqual(self.registrations[key],{'command':'user'})
        self.assertEqual(result.receipt.selection.features,{'mcp'})

    def test_existing_identical_profile_is_reused_without_claim_or_reformat(self):
        from iterm2_utils.features import profiles
        p=self.context.paths.profiles/'iterm2-utils.json';p.parent.mkdir()
        generated=profiles.build(self.context,self.selection('shortcuts',shortcuts=('resume',))).edits[0].after
        p.write_text(json.dumps(json.loads(generated),separators=(',',':')));before=p.read_bytes()
        result=self.install('shortcuts',shortcuts=('resume',))
        self.assertSuccess(result);self.assertEqual(p.read_bytes(),before)
        self.assertFalse(any(r['target']==str(p.resolve()) for r in result.receipt.resources))
        lifecycle.uninstall(self.context,frozenset({'shortcuts'}),self.runner)
        self.assertEqual(p.read_bytes(),before)

    def test_partial_uninstall_keeps_checkpoint_when_shell_recomposition_fails(self):
        initial=self.install('shell','status');self.assertSuccess(initial)
        before=self.snapshot();self.context.executables.pop('python3')
        result=lifecycle.uninstall(self.context,frozenset({'shell'}),self.runner)
        self.assertTrue(any(f.state in {'conflict','missing_dependency'} for f in result.findings))
        self.assertEqual(result.receipt,initial.receipt)
        self.assertEqual(self.snapshot(),before)

    def test_partial_uninstall_keeps_checkpoint_when_profile_recomposition_fails(self):
        initial=self.install('clipboard','shortcuts',shortcuts=('resume',));self.assertSuccess(initial)
        before=self.snapshot();self.context.profiles.clear()
        result=lifecycle.uninstall(self.context,frozenset({'clipboard'}),self.runner)
        self.assertTrue(any(f.code=='missing_parent' for f in result.findings))
        self.assertEqual(result.receipt,initial.receipt)
        self.assertEqual(self.snapshot(),before)

    def test_external_native_after_owned_status_blocks_without_mutation(self):
        self.assertSuccess(self.install('status'))
        settings=self.context.paths.config/'runtime.json'
        self.assertTrue(json.loads(settings.read_bytes())['status'])
        self.external_native()
        before=self.snapshot()
        result=lifecycle.update(self.context,self.runner)
        self.assertTrue(any(f.code=='native_hook_conflict' and f.state=='conflict' for f in result.findings))
        self.assertEqual(self.snapshot(),before)
        self.assertIn('status',result.receipt.selection.features)
        status_resource=next(r for r in result.receipt.resources if r['target']==str(settings.resolve()) and r['locator'].get('pointer')==['status'])
        self.assertEqual(status_resource['installed'],{'exists':True,'value':True})

    def test_native_dependency_does_not_block_notifications_or_restore(self):
        self.context.capabilities -= {'iterm2:cc-status-codex'}
        result=self.install('status','notifications','restore')
        self.assertEqual(result.receipt.selection.features,{'notifications','restore'})
        settings=json.loads((self.context.paths.config/'runtime.json').read_bytes())
        self.assertFalse(settings['status'])
        self.assertTrue(settings['notifications'])
        self.assertTrue(settings['restore'])

    def test_repeated_native_status_install_keeps_one_shared_hook(self):
        self.assertSuccess(self.install('status'))
        self.assertSuccess(self.install('status'))
        hooks=json.loads((self.context.paths.codex_home/'hooks.json').read_bytes())['hooks']
        self.assertEqual(len(hooks),12)
        self.assertTrue(all(len(v)==1 for v in hooks.values()))

    def test_install_agent_feature_matrix_keeps_flags_and_ownership_exact(self):
        cases=[({'codex':['status']},True,[],False),
               ({'codex':['notifications']},False,['codex'],False),
               ({'codex':['restore']},False,[],True),
               ({'claude':['notifications']},False,['claude'],False),
               ({'codex':['status'],'claude':['notifications']},True,['claude'],False),
               ({'codex':['notifications'],'claude':['status']},False,['codex'],False)]
        for agent_features,want_status,want_notifications,want_restore in cases:
            with self.subTest(agent_features=agent_features):
                fixture=LifecycleFixture();fixture.setUp();self.addCleanup(fixture.doCleanups)
                selection=Selection(frozenset(agent_features),frozenset(f for fs in agent_features.values() for f in fs),frozenset(),'Default',agent_features=agent_features)
                result=lifecycle.install(fixture.context,selection,fixture.runner)
                fixture.assertSuccess(result)
                settings=json.loads((fixture.context.paths.config/'runtime.json').read_bytes())
                self.assertEqual(settings['status'],want_status)
                self.assertEqual(settings['notification_agents'],want_notifications)
                self.assertEqual(settings['notifications'],bool(want_notifications))
                self.assertEqual(settings['restore'],want_restore)
                self.assertEqual(result.receipt.selection.pairs,selection.pairs)
                runtime_owners={o for resource in result.receipt.resources if 'shared:runtime' in resource['owners'] for o in resource['owners'] if not o.startswith('shared:')}
                expected={a+':'+f for a,fs in agent_features.items() for f in fs if a=='codex' or f=='notifications'}
                self.assertEqual(runtime_owners,expected)

    def test_native_reuse_keeps_external_hooks_outside_receipt(self):
        path=self.context.paths.codex_home/'hooks.json'
        native=self.external_native()
        self.assertSuccess(self.install('status','restore'))
        result=lifecycle.update(self.context,self.runner);self.assertSuccess(result)
        self.assertFalse(json.loads((self.context.paths.config/'runtime.json').read_bytes())['status'])
        self.assertIn('codex.zsh',self.context.paths.zshrc.read_text())
        resources=[r for r in result.receipt.resources if r['kind']=='hook']
        self.assertEqual(len(resources),12)
        self.assertTrue(all('current/hook.py' in r['locator']['entry']['hooks'][0]['command'] for r in resources))
        hooks=json.loads(path.read_bytes())['hooks']
        for event,entries in native.items():
            self.assertIn(entries[0],hooks[event])
            self.assertEqual(len(hooks[event]),2)

    def test_native_collision_blocks_retained_writer_shared_recomposition(self):
        for feature,agent in (('notifications','codex'),('restore','codex'),('notifications','claude')):
            with self.subTest(feature=feature,agent=agent):
                fixture=LifecycleFixture();fixture.setUp();self.addCleanup(fixture.doCleanups)
                fixture.assertSuccess(fixture.install('status'))
                fixture.external_native()
                before=fixture.snapshot()
                result=fixture.install(feature,agents=(agent,))
                self.assertTrue(any(f.state=='conflict' for f in result.findings))
                self.assertNotIn(feature,result.receipt.selection.features)
                self.assertEqual(fixture.snapshot(),before)

    def test_native_codex_collision_keeps_claude_status_ui_independent(self):
        for retained_notifications in (False,True):
            with self.subTest(retained_notifications=retained_notifications):
                fixture=LifecycleFixture();fixture.setUp();self.addCleanup(fixture.doCleanups)
                fixture.assertSuccess(fixture.install('status'))
                if retained_notifications:
                    fixture.assertSuccess(fixture.install('notifications',agents=('claude',)))
                fixture.external_native()
                paths=[fixture.context.paths.config/'runtime.json',fixture.context.paths.codex_home/'hooks.json',fixture.context.paths.claude_settings]
                before={path:path.read_bytes() if path.exists() else None for path in paths}
                result=fixture.install('status',agents=('claude',))
                fixture.assertSuccess(result)
                expected={'codex:status','claude:status'} | ({'claude:notifications'} if retained_notifications else set())
                self.assertEqual(result.receipt.selection.pairs,expected)
                self.assertEqual([(s.code,s.agent) for s in result.receipt.pending_ui],[('claude-native-status','claude')])
                self.assertIn('claude-native-status',result.receipt.ui_snapshots)
                self.assertEqual({path:path.read_bytes() if path.exists() else None for path in paths},before)
