import json
import shlex
import unittest
from dataclasses import replace
from iterm2_utils.discovery import discover, resolve_paths
from iterm2_utils.models import Selection
from iterm2_utils.features import status
from tests.support import Fixture
from runtime import events
from iterm2_utils.planner import plan
from iterm2_utils.features import shell
class StatusFeatureTests(unittest.TestCase):
    def test_claude_status_is_pending_native_ui_without_workgroup(self):
        with Fixture() as f:
            context=discover(resolve_paths(),f.runner)
            result=status.build(context,Selection(frozenset({'claude'}),frozenset({'status'}),frozenset(),'Default'))
            self.assertEqual(result.edits,[])
            self.assertEqual(len(result.ui),1)
            self.assertIn('Install/Reinstall Claude Code Integration',result.ui[0].instruction)
            self.assertIn('Session Status',result.ui[0].instruction)
            planned=plan(context,Selection(frozenset({'claude'}),frozenset({'status'}),frozenset(),'Default'))
            self.assertEqual(planned.changes.edits,[])
    def test_existing_status_is_reused(self):
        with Fixture() as f:
            context=discover(resolve_paths(),f.runner)
            context=replace(context,installed={'codex-status':{'enabled':True}})
            result=status.build(context,Selection(frozenset({'codex'}),frozenset({'status'}),frozenset(),'Default'))
            self.assertEqual(result.edits,[])
            self.assertEqual(result.findings[0].code,'existing_status')
    def test_codex_has_exact_one_command_per_event(self):
        with Fixture() as f:
            context=discover(resolve_paths(),f.runner)
            result=status.build(context,Selection(frozenset({'codex'}),frozenset({'status'}),frozenset(),'Default'))
            edit=next(e for e in result.edits if e.path==context.paths.codex_home/'hooks.json')
            hooks=json.loads(edit.after)['hooks']
            self.assertEqual(set(hooks),set(events.CODEX_EVENTS))
            for entries in hooks.values():
                self.assertEqual(len(entries),1);self.assertEqual(entries[0]['hooks'][0]['timeout'],3)
    def test_discovery_reuses_exact_enabled_plugin_and_native_status_only(self):
        with Fixture() as f:
            paths=resolve_paths()
            paths.codex_home.mkdir();(paths.codex_home/'config.toml').write_text('[plugins."iterm2-status@community"]\nenabled = true\n')
            paths.claude_settings.parent.mkdir();paths.claude_settings.write_text(json.dumps({'env':{'SECRET':'PRIVATE'},'hooks':{'Stop':[{'hooks':[{'type':'command','command':str(paths.home/'.config/iterm2/cc-status')+' stop'}]}]}}))
            context=discover(paths,f.runner)
            self.assertEqual(context.installed,{'codex-status':{'enabled':True},'claude-status':{'enabled':True}})
            self.assertNotIn('PRIVATE',repr(context))
    def test_live_probe_is_explicit_bounded_and_does_not_expose_output(self):
        from unittest.mock import patch
        from iterm2_utils.discovery import live_status
        from tests.test_runtime_events import UUID
        with Fixture() as f:
            context=discover(resolve_paths(),f.runner)
            f.runner.calls.clear();f.runner.responses['it2']='{"status":"idle","secret":"PRIVATE"}'
            with patch.dict('os.environ',{'ITERM_SESSION_ID':'w0t0p0:'+UUID}):
                findings=live_status(context,f.runner,Selection(frozenset({'codex'}),frozenset({'status'}),frozenset(),'Default'))
            self.assertEqual(f.runner.calls[0][0][-2:],['--session',UUID])
            self.assertLessEqual(f.runner.calls[0][1],2)
            self.assertEqual(findings[0].state,'ready')
            self.assertNotIn('PRIVATE',repr(findings))

    def test_native_status_settings_and_allowed_hooks(self):
        with Fixture() as f:
            context=discover(resolve_paths(),f.runner)
            result=status.build(context,Selection(frozenset({'codex'}),frozenset({'status'}),frozenset(),'Default'))
            settings=json.loads(next(e.after for e in result.edits if e.path==context.paths.config/'runtime.json'))
            self.assertEqual(settings.get('status_backend'),'cc-status')
            self.assertEqual(settings.get('iterm2_app'),str(context.executables['iterm2']))
            self.assertEqual(settings.get('native_identity_cache'),str(context.paths.cache/'native-identity'))
            self.assertTrue(settings['status'])
            hooks=json.loads(next(e.after for e in result.edits if e.path==context.paths.codex_home/'hooks.json'))['hooks']
            self.assertEqual(set(hooks),set(events.CODEX_EVENTS))
            self.assertEqual(len(hooks),12)
            self.assertNotIn('StopFailure',hooks)
            self.assertTrue(all(len(v)==1 and v[0]['hooks'][0]['timeout']==3 for v in hooks.values()))

    def test_native_reuse_preserves_external_hooks_and_no_daemon_wrapper(self):
        for extra in (set(), {'notifications'}, {'restore'}):
            with self.subTest(extra=extra), Fixture() as f:
                context=discover(resolve_paths(),f.runner)
                path=context.paths.codex_home/'hooks.json'
                path.parent.mkdir()
                command=shlex.join([str(f.app/'Contents/Resources/utilities/cc-status'),'--agent','codex'])
                native={event:[{'hooks':[{'type':'command','command':command,'timeout':3}]}] for event in events.CODEX_EVENTS if event not in {'PreCompact','PostCompact'}}
                path.write_text(json.dumps({'foreign':'keep','hooks':native}))
                context=discover(context.paths,f.runner)
                self.assertTrue(context.installed['codex-native-status']['enabled'])
                selection=Selection(frozenset({'codex'}),frozenset({'status'}|extra),frozenset(),'Default')
                result=plan(context,selection).changes
                settings=json.loads(next(e.after for e in result.edits if e.path==context.paths.config/'runtime.json'))
                self.assertFalse(settings['status'])
                self.assertEqual(settings['notifications'], 'notifications' in extra)
                self.assertEqual(settings['restore'], 'restore' in extra)
                startup=next(e.after for e in result.edits if e.path==context.paths.zshrc)
                self.assertIn(b'codex.zsh',startup)
                hook_edits=[e for e in result.edits if e.path==context.paths.codex_home/'hooks.json']
                self.assertEqual(len(hook_edits),bool(extra))
                if extra:
                    hooks=json.loads(hook_edits[0].after)['hooks']
                    self.assertEqual(len(hooks),12)
                    self.assertEqual(json.loads(hook_edits[0].after)['foreign'],'keep')
                    for event,entries in hooks.items():
                        self.assertEqual(len(entries),1 if event in {'PreCompact','PostCompact'} else 2)
                        if event in native:
                            self.assertIn(native[event][0],entries)
                        own=[v for v in entries if 'current/hook.py' in v['hooks'][0]['command']]
                        self.assertEqual(len(own),1)

    def test_native_conflict_precedes_legacy_reuse(self):
        for inventory in ({'conflict':True},{'enabled':True}):
            with self.subTest(inventory=inventory), Fixture() as f:
                context=discover(resolve_paths(),f.runner)
                context=replace(context,installed={'codex-status':{'enabled':True},'codex-native-status':inventory})
                result=status.build(context,Selection(frozenset({'codex'}),frozenset({'status'}),frozenset(),'Default'))
                self.assertTrue(any(f.code=='native_hook_conflict' and f.state=='conflict' for f in result.findings))
                self.assertFalse(result.edits)

    def test_independent_agent_feature_runtime_flags_and_consumers(self):
        cases=[({'codex':['status']},True,[],False),
               ({'codex':['notifications']},False,['codex'],False),
               ({'codex':['restore']},False,[],True),
               ({'claude':['notifications']},False,['claude'],False),
               ({'codex':['status'],'claude':['notifications']},True,['claude'],False),
               ({'codex':['notifications'],'claude':['status']},False,['codex'],False)]
        for agent_features,want_status,want_agents,want_restore in cases:
            with self.subTest(agent_features=agent_features), Fixture() as f:
                context=discover(resolve_paths(),f.runner)
                features=frozenset(f for fs in agent_features.values() for f in fs)
                selection=Selection(frozenset(agent_features),features,frozenset(),'Default',agent_features=agent_features)
                result=plan(context,selection).changes
                settings=json.loads(next(e.after for e in result.edits if e.path==context.paths.config/'runtime.json'))
                self.assertEqual(settings['status'],want_status)
                self.assertEqual(settings['notification_agents'],want_agents)
                self.assertEqual(settings['notifications'],bool(want_agents))
                self.assertEqual(settings['restore'],want_restore)
                pairs=frozenset(a+':'+f for a,fs in agent_features.items() for f in fs if a=='codex' or f=='notifications')
                self.assertEqual(result.consumers['shared:hooks'],pairs)
                self.assertEqual(result.consumers['shared:runtime'],pairs)
                codex_pairs=frozenset(p for p in pairs if p.startswith('codex:'))
                self.assertEqual(result.consumers.get('shared:codex-hooks',frozenset()),codex_pairs)
                payload=shell.runtime_payload(context,selection)
                self.assertFalse(any(e.path.name in {'cc-status','it2'} for e in payload.edits))

    def test_owned_collision_findings_target_only_python_runtime_consumers(self):
        from tests.test_lifecycle import LifecycleFixture
        fixture=LifecycleFixture();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.assertSuccess(fixture.install('status'))
        fixture.context.installed['codex-native-status']={'enabled':True}
        selection=Selection(frozenset({'codex','claude'}),frozenset({'status','notifications','restore'}),frozenset(),'Default',
                            agent_features={'codex':['status','notifications','restore'],'claude':['status','notifications']})
        result=status.build(fixture.context,selection)
        blockers=[f for f in result.findings if f.state=='conflict']
        self.assertEqual({(f.agent,f.feature) for f in blockers},
                         {('codex','status'),('codex','notifications'),('codex','restore'),('claude','notifications')})
        self.assertEqual([(s.code,s.agent) for s in result.ui],[('claude-native-status','claude')])
        self.assertEqual(result.edits,[])
