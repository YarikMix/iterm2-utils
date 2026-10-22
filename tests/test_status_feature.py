import json
import unittest
from dataclasses import replace
from iterm2_utils.discovery import discover, resolve_paths
from iterm2_utils.models import Selection
from iterm2_utils.features import status
from tests.support import Fixture
class StatusFeatureTests(unittest.TestCase):
    def test_claude_status_is_pending_native_ui_without_workgroup(self):
        with Fixture() as f:
            context=discover(resolve_paths(),f.runner)
            result=status.build(context,Selection(frozenset({'claude'}),frozenset({'status'}),frozenset(),'Default'))
            self.assertEqual(result.edits,[])
            self.assertEqual(len(result.ui),1)
            self.assertIn('Install/Reinstall Claude Code Integration',result.ui[0].instruction)
            self.assertIn('Session Status',result.ui[0].instruction)
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
            self.assertEqual(set(hooks),set(status.EVENTS))
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
