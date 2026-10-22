import unittest
from iterm2_utils.features import notifications
class FeatureTests(unittest.TestCase):
    def test_builder_exists(self):
        self.assertTrue(callable(notifications.build))
    def test_native_approval_policy_is_targeted_and_reversible(self):
        from dataclasses import replace
        from iterm2_utils.discovery import discover,resolve_paths
        from iterm2_utils.models import Selection
        from iterm2_utils.config import tomlfile
        from tests.support import Fixture
        with Fixture() as f:
            f.runner.responses['codex']='0.163.0 --no-daemon'
            context=discover(resolve_paths(),f.runner)
            self.assertIn('codex:approval-notifications',context.capabilities)
            context.paths.codex_home.mkdir()
            path=context.paths.codex_home/'config.toml'
            for previous in (False,True,['agent-turn-complete']):
                before=tomlfile.patch(b'[tui]\nother = true\n',('tui','notifications'),previous);path.write_bytes(before)
                changes=notifications.build(context,Selection(frozenset({'codex'}),frozenset({'notifications'}),frozenset(),'Default'))
                edit=changes.edits[0]
                self.assertEqual(edit.before,before)
                self.assertEqual(tomlfile.parse(edit.after),{'tui':{'notifications':['approval-requested'],'other':True}})
                from iterm2_utils import engine
                from iterm2_utils.models import Plan
                selection=Selection(frozenset({'codex'}),frozenset({'notifications'}),frozenset(),'Default')
                outcome=engine.apply(Plan(selection,changes,'fixture'),context,f.runner)
                self.assertEqual(tomlfile.parse(path.read_bytes())['tui']['notifications'],['approval-requested'])
                reverted=engine.revert(outcome.receipt,context,f.runner,frozenset({'notifications'}))
                self.assertEqual(reverted.receipt.resources,[])
                self.assertEqual(tomlfile.parse(path.read_bytes()),tomlfile.parse(before))
    def test_claude_registration_has_exact_notification_matcher(self):
        from iterm2_utils.discovery import discover,resolve_paths
        from iterm2_utils.models import Selection
        from tests.support import Fixture
        import json
        with Fixture() as f:
            context=discover(resolve_paths(),f.runner)
            changes=notifications.build(context,Selection(frozenset({'claude'}),frozenset({'notifications'}),frozenset(),'Default'))
            edit=next(e for e in changes.edits if e.path==context.paths.claude_settings)
            hooks=json.loads(edit.after)['hooks']
            self.assertEqual(set(hooks),set(notifications.CLAUDE_EVENTS))
            self.assertTrue({'PostToolUse','PostToolUseFailure'} <= set(hooks))
            self.assertEqual(hooks['Notification'][0]['matcher'],notifications.MATCHER)
