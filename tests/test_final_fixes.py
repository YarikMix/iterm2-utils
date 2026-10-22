"""Regressions for the final integration review; only synthetic HOME/commands."""
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch
from iterm2_utils import lifecycle, state
from tests.test_agent_workflow import WorkflowFixture


class FinalFixTests(WorkflowFixture):
    def setUp(self):
        super().setUp()
        self.context.versions['python3'] = '3.11.9'
        self.context.executables['osascript'] = self.context.paths.home/'bin/osascript'

    def test_i1_independent_pairs_and_partial_remove(self):
        self.assertSuccess(self.install('clipboard', 'status'))
        result = self.setup_cli(['install','--agent','claude','--features','notifications,mcp'])
        self.assertNotEqual(result['exit_code'], 2, result)
        chosen = state.load(self.context.paths.data/'receipt.json').selection
        self.assertEqual(chosen.features_for('codex'), {'clipboard','status'})
        self.assertEqual(chosen.features_for('claude'), {'notifications','mcp'})
        self.assertEqual(set(self.registrations), {('claude','iterm2-observe')})
        result = self.setup_cli(['uninstall','--agent','claude','--features','notifications'])
        self.assertNotEqual(result['exit_code'], 2, result)
        self.assertTrue((self.context.paths.codex_home/'hooks.json').exists())
        self.assertTrue((self.context.paths.data/'current/hook.py').exists())
        self.assertEqual(json.loads(self.context.paths.claude_settings.read_text())['hooks']['Stop'], [])

    def test_i2_interpreter_change_replaces_owned_hooks(self):
        self.assertSuccess(self.install('status','notifications',agents=('codex','claude')))
        foreign = {'hooks':[{'type':'command','command':'foreign-hook'}]}
        for path in (self.context.paths.codex_home/'hooks.json', self.context.paths.claude_settings):
            doc = json.loads(path.read_text()); doc['hooks']['Stop'].insert(0, foreign)
            path.write_text(json.dumps(doc))
        self.context.executables['python3'] = self.context.paths.home/'new python/python3'
        self.assertSuccess(lifecycle.update(self.context,self.runner))
        for path in (self.context.paths.codex_home/'hooks.json', self.context.paths.claude_settings):
            entries = json.loads(path.read_text())['hooks']['Stop']
            self.assertEqual(len(entries), 2, entries)
            self.assertIn(foreign, entries)
            self.assertIn('new python',entries[1]['hooks'][0]['command'])
        self.assertSuccess(lifecycle.uninstall(self.context, frozenset({'status','notifications'}), self.runner))
        for path in (self.context.paths.codex_home/'hooks.json', self.context.paths.claude_settings):
            self.assertEqual(json.loads(path.read_text())['hooks']['Stop'], [foreign])

    def test_i3_doctor_checks_missing_resources_and_dependencies_readonly(self):
        self.assertSuccess(self.install('status'))
        (self.context.paths.codex_home/'hooks.json').unlink()
        self.context.executables.pop('python3')
        before = self.snapshot()
        result = self.setup_cli(['doctor'])
        self.assertEqual(result['exit_code'], 2, result)
        self.assertIn('owned_resource_missing', {f['code'] for f in result['report']['findings']})
        self.assertIn('missing_binary', {f['code'] for f in result['report']['findings']})
        self.assertEqual(before, self.snapshot())

    def test_i4_live_codex_does_not_require_claude(self):
        self.assertSuccess(self.install('status'))
        self.runner.responses['it2'] = '{"status":"idle"}'
        with patch.dict(os.environ, {'ITERM_SESSION_ID':'11111111-2222-3333-4444-555555555555'}):
            result = self.setup_cli(['doctor','--live'])
        self.assertFalse([f for f in result['report']['findings'] if f['agent']=='claude'], result)
        self.assertEqual(result['exit_code'], 0, result)

    def test_i5_old_python_blocks_only_runtime(self):
        self.context.versions['python3'] = '3.9.6'
        result = self.install('shell','clipboard','status','notifications','restore')
        self.assertEqual(result.receipt.selection.features, {'shell','clipboard'})
        self.assertTrue(any(f.code=='python_version' for f in result.findings))

    def test_i6_all_notification_transports_required(self):
        for binary in ('it2','osascript','terminal-notifier'):
            with self.subTest(binary=binary):
                value = self.context.executables.pop(binary)
                result = self.install('notifications')
                self.assertNotIn('notifications', result.receipt.selection.features)
                self.assertTrue(any(f.state=='missing_dependency' and binary in f.message for f in result.findings))
                self.context.executables[binary] = value

    def test_i7_foreign_notifications_need_explicit_coexistence(self):
        path = self.context.paths.claude_settings; path.parent.mkdir()
        foreign = {'hooks':[{'type':'command','command':'/fixture/terminal-notifier -message existing'}]}
        path.write_text(json.dumps({'hooks':{'Stop':[foreign]}})); before = path.read_bytes()
        result = self.install('notifications', agents=('claude',))
        self.assertTrue(any(f.code=='foreign_notifications' for f in result.findings), result)
        self.assertEqual(path.read_bytes(), before)
        result = self.setup_cli(['install','--agent','claude','--features','notifications','--coexist-notifications'])
        self.assertEqual(result['exit_code'], 0, result)
        self.assertSuccess(lifecycle.update(self.context,self.runner))
        self.assertSuccess(lifecycle.uninstall(self.context,frozenset({'notifications'}),self.runner))
        self.assertEqual(json.loads(path.read_text())['hooks']['Stop'], [foreign])

    def test_i8_standalone_global_option_service_passthrough(self):
        folder = self.context.paths.home/'bin'; folder.mkdir()
        binary = folder/'codex'; binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n'); binary.chmod(0o700)
        for args in (['--config','x=y','app-server'], ['-m','model','agents'], ['--profile=work','remote-control']):
            result = subprocess.run(['/bin/zsh','-f','-c','source "$1"; shift; codex "$@"','fixture',
                str(self.context.paths.repo/'runtime/codex.zsh'),*args],env={'HOME':str(self.context.paths.home),
                'PATH':str(folder)+':/usr/bin:/bin','ITERM2_UTILS_CODEX_NO_DAEMON':'1'},text=True,capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(),args)

    def test_m1_materializes_foreign_state_and_versions(self):
        from tests.test_agent_workflow import materialize_case
        materialize_case(self, {'agents':['codex','claude'],'versions':{'codex':'0.1.0','claude':'2.1.308'},
            'features_initial':[], 'peekaboo':'available','foreign_mcp':'iterm2-observe',
            'foreign_command':'different-observer','foreign_marker':'SYNTHETIC_FOREIGN_VALUE'})
        self.assertEqual(self.context.versions['codex'], '0.1.0')
        self.assertNotIn('codex:approval-notifications', self.context.capabilities)
        paths = [self.context.paths.codex_home/'config.toml', self.context.paths.home/'.claude.json']
        before = {p:p.read_bytes() for p in paths}
        self.assertTrue(all(b'SYNTHETIC_FOREIGN_VALUE' in raw and b'different-observer' in raw for raw in before.values()))
        result = self.setup_cli(['install','--agent','both','--features','shell'])
        self.assertEqual(result['exit_code'], 0)
        self.assertEqual(before,{p:p.read_bytes() for p in paths})
        result = self.setup_cli(['install','--agent','codex','--features','mcp'])
        self.assertEqual(result['exit_code'], 2)
        self.assertEqual(before,{p:p.read_bytes() for p in paths})

    def test_m2_provenance_rejects_stripped_metadata(self):
        import shutil
        from tools.check_export import EXPORT_FILES, check
        repo = self.context.paths.home/'export'
        for name in EXPORT_FILES:
            target = repo/name; target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(self.context.paths.repo/name,target)
        lock = repo/'sources.lock.json'; data = json.loads(lock.read_text())
        import hashlib
        for entry in data['sources']:
            entry['sha256'] = hashlib.sha256((repo/entry['path']).read_bytes()).hexdigest()
        lock.write_text(json.dumps(data))
        self.assertFalse(check(repo))
        import copy
        for kind,field in [('public','url'),('public','license'),('local','source'),('local','author'),('local','license'),('adaptation','upstream_sha256')]:
            with self.subTest(kind=kind,field=field):
                altered=copy.deepcopy(data)
                entry=next(e for e in altered['sources'] if ('url' in e if kind=='public' else 'source' in e if kind=='local' else e.get('transformation') not in (None,'none') and 'upstream_sha256' in e))
                entry.pop(field,None)
                lock.write_text(json.dumps(altered))
                self.assertTrue(check(repo), (kind,field))

    def test_i1_reverse_order_and_runtime_flags(self):
        self.assertSuccess(self.install('notifications','mcp',agents=('claude',)))
        self.assertSuccess(self.install('clipboard','status'))
        settings=json.loads((self.context.paths.config/'runtime.json').read_text())
        self.assertEqual(settings['notification_agents'], ['claude'])
        from runtime.events import normalize
        from runtime.hook import dispatch
        event=normalize({'hook_event_name':'Stop','session_id':'fixture'},'codex','11111111-2222-3333-4444-555555555555')
        with patch('runtime.notifier.handle') as delivery:
            dispatch(event,dict(settings,status=False),self.runner)
            delivery.assert_not_called()
        self.assertSuccess(lifecycle.uninstall(self.context,frozenset({'status','clipboard'}),self.runner,agents=frozenset({'codex'})))
        self.assertEqual(json.loads((self.context.paths.codex_home/'hooks.json').read_text())['hooks']['Stop'], [])
        self.assertTrue(json.loads(self.context.paths.claude_settings.read_text())['hooks']['Stop'])
        self.assertTrue((self.context.paths.data/'current/hook.py').exists())
        self.assertNotIn('codex.zsh', self.context.paths.zshrc.read_text())

    def test_i1_pairwise_shortcuts_and_same_feature_removal(self):
        self.assertSuccess(self.install('shortcuts','notifications',shortcuts=('resume',)))
        self.assertSuccess(self.install('shortcuts','notifications',agents=('claude',),shortcuts=('ctrl-q',)))
        profiles=json.loads((self.context.paths.profiles/'iterm2-utils.json').read_text())['Profiles']
        self.assertEqual(set(profiles[0]['Keyboard Map']), {'foreign','0x71-0x40000-0xc-0x1'})
        self.assertEqual(set(profiles[1]['Keyboard Map']), {'foreign','0x52-0x120000-0xf-0x1'})
        self.assertSuccess(lifecycle.uninstall(self.context,frozenset({'notifications','shortcuts'}),self.runner,agents=frozenset({'claude'})))
        self.assertSuccess(lifecycle.update(self.context,self.runner))
        chosen=state.load(self.context.paths.data/'receipt.json').selection
        self.assertEqual(chosen.features_for('claude'),set())
        self.assertEqual(chosen.features_for('codex'),{'shortcuts','notifications'})
        self.assertEqual(json.loads((self.context.paths.config/'runtime.json').read_text())['notification_agents'],['codex'])
        self.assertEqual(len(json.loads((self.context.paths.profiles/'iterm2-utils.json').read_text())['Profiles']),1)

    def test_i1_legacy_flat_receipt_preserves_original_crossproduct(self):
        self.assertSuccess(self.install('shortcuts','notifications',agents=('codex','claude'),shortcuts=('resume',)))
        path=self.context.paths.data/'receipt.json'; raw=json.loads(path.read_text())
        raw['selection'].pop('agent_features');raw['selection'].pop('agent_shortcuts');raw['selection'].pop('coexist_notifications')
        for resource in raw['resources']:
            resource['owners']=list(dict.fromkeys('shared:hooks' if o=='shared:codex-hooks' else o.split(':',1)[1] if o.startswith(('codex:','claude:')) else o for o in resource['owners']))
        path.write_text(json.dumps(raw))
        updated=lifecycle.update(self.context,self.runner)
        self.assertSuccess(updated)
        self.assertTrue(all(':' in owner for r in updated.receipt.resources for owner in r['owners']))
        self.assertSuccess(self.install('mcp',agents=('claude',)))
        chosen=state.load(path).selection
        self.assertEqual(chosen.features_for('codex'), {'shortcuts','notifications'})
        self.assertEqual(chosen.features_for('claude'), {'shortcuts','notifications','mcp'})
        self.assertSuccess(lifecycle.uninstall(self.context,frozenset({'notifications'}),self.runner,agents=frozenset({'claude'})))
        self.assertTrue(json.loads((self.context.paths.codex_home/'hooks.json').read_text())['hooks']['Stop'])
        self.assertFalse(json.loads(self.context.paths.claude_settings.read_text())['hooks']['Stop'])

    def test_i3_changed_pointer_setting_registration_are_reported(self):
        self.assertSuccess(self.install('status','mcp'))
        settings=self.context.paths.config/'runtime.json';doc=json.loads(settings.read_text());doc['status']=False;settings.write_text(json.dumps(doc))
        current=self.context.paths.data/'current';current.unlink();current.symlink_to(self.context.paths.home/'missing-release')
        self.registrations['codex','iterm2-observe']={'command':'foreign'}
        before=self.snapshot(); result=self.setup_cli(['doctor'])
        self.assertEqual(result['exit_code'],2,result)
        self.assertIn('owned_resource_changed',{f['code'] for f in result['report']['findings']})
        self.assertIn('registration_changed',{f['code'] for f in result['report']['findings']})
        self.assertEqual(before,self.snapshot())

    def test_i4_mcp_live_independent_of_status_capability(self):
        self.assertSuccess(self.install('mcp',agents=('claude',)))
        self.context.capabilities -= {'iterm2:session-status'}
        from iterm2_utils.models import Finding
        with patch('iterm2_utils.config.mcp.probe',return_value=Finding('mcp','claude','runtime','ready','Verified fixture')) as probe:
            result=self.setup_cli(['doctor','--live'])
        probe.assert_called_once_with(self.context,self.runner,'claude')
        self.assertFalse([f for f in result['report']['findings'] if f['feature']=='status'],result)

    def test_i5_restore_uses_selected_interpreter_with_spaces(self):
        folder=self.context.paths.home/'selected python';folder.mkdir()
        python=folder/'python3';python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n');python.chmod(0o700)
        result=subprocess.run(['/bin/zsh','-f','-c','source "$1"; ITERM2_UTILS_PYTHON="$2"; _codex_restore_sessions --help','fixture',
            str(self.context.paths.repo/'runtime/codex_restore/codex-resume.zsh'),str(python)],
            env={'HOME':str(self.context.paths.home),'PATH':'/usr/bin:/bin'},text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.splitlines(),[str(self.context.paths.repo/'runtime/codex_restore/codex-sessions'),'--help'])

    def test_i7_external_status_plugin_conflict_is_preserved(self):
        path=self.context.paths.codex_home/'config.toml';path.parent.mkdir()
        path.write_text('[plugins."iterm2-status@community"]\nenabled = true\n')
        before=path.read_bytes(); result=self.install('notifications')
        self.assertTrue(any(f.code=='foreign_notifications' for f in result.findings),result)
        self.assertEqual(path.read_bytes(),before)

    def test_i7_coexist_choice_does_not_expand_to_another_agent(self):
        from dataclasses import replace
        self.assertSuccess(lifecycle.install(self.context,replace(self.selection('notifications',agents=('claude',)),coexist_notifications=True),self.runner))
        path=self.context.paths.codex_home/'hooks.json';path.parent.mkdir()
        path.write_text(json.dumps({'hooks':{'Stop':[{'hooks':[{'type':'command','command':'terminal-notifier -message foreign'}]}]}}))
        result=self.install('notifications')
        self.assertTrue(any(f.code=='foreign_notifications' for f in result.findings),result)
        self.assertNotIn('notifications',result.receipt.selection.features_for('codex'))

    def test_i1_additive_cli_discovers_previous_agents_without_selecting_new_pairs(self):
        import contextlib,io
        from iterm2_utils import cli
        self.assertSuccess(self.install('clipboard'))
        with patch.object(cli,'resolve_paths',return_value=self.context.paths), patch.object(cli,'Runner',return_value=self.runner), \
             patch.object(cli,'discover',return_value=self.context) as discovery, contextlib.redirect_stdout(io.StringIO()) as output:
            code=cli.main(['plan','--agent','claude','--features','mcp','--json'])
        discovery.assert_called_once_with(self.context.paths,self.runner,agents=frozenset({'codex','claude'}))
        self.assertNotEqual(code,2,output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['selection']['agent_features'],{'codex':['clipboard'],'claude':['mcp']})

    def test_i5_discovery_validates_actual_selected_python(self):
        from tests.support import Fixture
        from iterm2_utils.discovery import discover,resolve_paths
        from iterm2_utils.planner import validate
        with Fixture() as f:
            f.runner.responses['python3']='Python 3.9.6'
            context=discover(resolve_paths(),f.runner)
            self.assertTrue(any(x.code=='python_version' for x in validate(self.selection('status'),context)))
            custom=f.home/'new python/python3';custom.parent.mkdir();custom.write_text('#!/bin/sh\n');custom.chmod(0o700)
            f.runner.responses['python3']='Python 3.12.8'
            with patch.dict(os.environ,{'ITERM2_UTILS_PYTHON':str(custom)}):
                context=discover(resolve_paths(),f.runner)
            self.assertEqual(context.executables['python3'],custom)
            self.assertFalse([x for x in validate(self.selection('status'),context) if x.code=='python_version'])

    def test_i1_invalid_pairwise_receipt_is_not_ownership(self):
        self.assertSuccess(self.install('shell'))
        path=self.context.paths.data/'receipt.json';raw=json.loads(path.read_text());raw['selection']['agent_features']={'codex':['mcp']};path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):state.load(path)
        result=self.setup_cli(['doctor']);self.assertEqual(result['exit_code'],2)

    def test_i3_disappeared_reused_native_status_is_pending(self):
        path=self.context.paths.claude_settings;path.parent.mkdir()
        path.write_text(json.dumps({'hooks':{'Stop':[{'hooks':[{'type':'command','command':str(self.context.paths.home/'.config/iterm2/cc-status')+' stop'}]}]}}))
        self.context.installed['claude-status']={'enabled':True}
        self.assertSuccess(self.install('status',agents=('claude',)))
        path.unlink();self.context.installed.pop('claude-status')
        result=self.setup_cli(['doctor'])
        self.assertEqual(result['exit_code'],3,result)
        self.assertTrue(any(f['code']=='native_status' for f in result['report']['findings']))

    def test_i1_claude_notifications_ignore_unselected_codex_hooks(self):
        path=self.context.paths.codex_home/'hooks.json';path.parent.mkdir();path.write_text('{broken')
        result=self.install('notifications',agents=('claude',))
        self.assertSuccess(result)
        settings=self.context.paths.config/'runtime.json'
        self.assertTrue(settings.exists())
        self.assertEqual(json.loads(settings.read_text())['notification_agents'],['claude'])
        self.assertEqual(path.read_text(),'{broken')

    def test_i1_new_agent_notification_keeps_existing_status_intent_if_capability_disappears(self):
        self.assertSuccess(self.install('status'))
        self.context.capabilities -= {'codex:no-daemon','iterm2:session-status'}
        result=self.install('notifications',agents=('claude',))
        self.assertSuccess(result)
        settings=json.loads((self.context.paths.config/'runtime.json').read_text())
        self.assertTrue(settings['status'])
        self.assertEqual(settings['notification_agents'],['claude'])

    def test_i1_independent_agent_conflict_does_not_hide_missing_hooks(self):
        self.assertSuccess(self.install('notifications'))
        path=self.context.paths.codex_home/'hooks.json';doc=json.loads(path.read_text())
        doc['hooks']['Stop'].append({'hooks':[{'type':'command','command':'terminal-notifier -message foreign'}]})
        path.write_text(json.dumps(doc))
        self.assertSuccess(self.install('notifications',agents=('claude',)))
        self.assertTrue(self.context.paths.claude_settings.exists())
        self.assertEqual(len(json.loads(self.context.paths.claude_settings.read_text())['hooks']['Stop']),1)

    def test_i5_pinned_legacy_restore_remains_recognizable(self):
        import hashlib
        from iterm2_utils import migration
        bundled=(self.context.paths.repo/'runtime/codex_restore/codex-resume.zsh').read_text()
        start=bundled.index('# Package installs pass')
        end=bundled.index('function _codex_restore_previous_call',start)
        original=(bundled[:start]+bundled[end:]).replace('_codex_restore_sessions','"$_codex_restore_root/codex-sessions"')
        lock=json.loads((self.context.paths.repo/'sources.lock.json').read_text())
        expected=next(e['upstream_sha256'] for e in lock['sources'] if e['path']=='runtime/codex_restore/codex-resume.zsh')
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),expected)
        legacy=self.context.paths.home/'legacy.zsh';legacy.write_text(original)
        import shlex
        self.assertTrue(migration._recognized('legacy-restore','source '+shlex.quote(str(legacy)),self.context))

    def test_n1_additive_shortcuts_preserve_retained_profile_checkpoint(self):
        self.assertSuccess(self.install('shortcuts',shortcuts=('alt-enter',)))
        profile=self.context.paths.profiles/'iterm2-utils.json'
        before_bytes=profile.read_bytes()
        before_receipt=state.load(self.context.paths.data/'receipt.json')
        self.context.capabilities -= {'codex:alt-enter'}
        result=self.setup_cli(['install','--agent','claude','--features','shortcuts','--shortcuts','resume'])
        self.assertEqual(result['exit_code'],2,result)
        self.assertTrue(any(f['code']=='shortcut_capability' and f['agent']=='codex' for f in result['report']['findings']))
        self.assertEqual(profile.read_bytes(),before_bytes)
        self.assertEqual(state.load(self.context.paths.data/'receipt.json'),before_receipt)

    def test_n1_update_preserves_whole_shared_profile_checkpoint(self):
        self.assertSuccess(self.install('shortcuts',shortcuts=('alt-enter',)))
        self.assertSuccess(self.install('shortcuts',agents=('claude',),shortcuts=('resume',)))
        profile=self.context.paths.profiles/'iterm2-utils.json'
        before_bytes=profile.read_bytes()
        before_receipt=state.load(self.context.paths.data/'receipt.json')
        self.context.capabilities -= {'codex:alt-enter'}
        result=lifecycle.update(self.context,self.runner)
        self.assertTrue(any(f.code=='shortcut_capability' and f.agent=='codex' for f in result.findings),result.findings)
        self.assertFalse(any(f.code=='feature_checkpoint' for f in result.findings),result.findings)
        self.assertEqual(profile.read_bytes(),before_bytes)
        self.assertEqual(result.receipt,before_receipt)
        self.assertEqual(state.load(self.context.paths.data/'receipt.json'),before_receipt)

    def test_n1_blocked_shared_profile_keeps_independent_shell_install(self):
        self.assertSuccess(self.install('shortcuts',shortcuts=('alt-enter',)))
        profile=self.context.paths.profiles/'iterm2-utils.json'
        before_bytes=profile.read_bytes()
        before=state.load(self.context.paths.data/'receipt.json')
        resources=[r for r in before.resources if r['target']==str(profile.resolve())]
        self.context.capabilities -= {'codex:alt-enter'}
        result=self.install('shell','shortcuts',agents=('claude',),shortcuts=('resume',))
        self.assertTrue(any(f.code=='shortcut_capability' and f.agent=='codex' for f in result.findings),result.findings)
        self.assertEqual(result.receipt.selection.features_for('claude'),{'shell'})
        self.assertEqual(result.receipt.selection.shortcuts_for('codex'),{'alt-enter'})
        self.assertEqual(profile.read_bytes(),before_bytes)
        self.assertEqual([r for r in result.receipt.resources if r['target']==str(profile.resolve())],resources)
        self.assertIn('iterm2_shell_integration.zsh',self.context.paths.zshrc.read_text())

    def test_n1_early_profile_builder_failure_preserves_checkpoint(self):
        self.assertSuccess(self.install('shortcuts',shortcuts=('alt-enter',)))
        profile=self.context.paths.profiles/'iterm2-utils.json'
        before_bytes=profile.read_bytes()
        before_receipt=state.load(self.context.paths.data/'receipt.json')
        self.context.profiles['Default']['Keyboard Map']['0xd-0x20000-0x24-0x1']={'Action':1,'Text':'foreign'}
        result=self.install('shortcuts',agents=('claude',),shortcuts=('resume',))
        self.assertTrue(any(f.code=='binding_conflict' and f.agent=='codex' for f in result.findings),result.findings)
        self.assertEqual(profile.read_bytes(),before_bytes)
        self.assertEqual(result.receipt,before_receipt)
        self.assertEqual(state.load(self.context.paths.data/'receipt.json'),before_receipt)
