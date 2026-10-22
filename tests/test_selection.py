import unittest
from tests.support import Fixture
from iterm2_utils.discovery import discover, resolve_paths
from iterm2_utils.models import Selection
from iterm2_utils.planner import plan, validate


class SelectionTests(unittest.TestCase):
    def test_missing_binary_blocks_only_affected_feature(self):
        with Fixture() as f:
            (f.bin / 'terminal-notifier').unlink()
            context = discover(resolve_paths(), f.runner)
            findings = validate(Selection(frozenset({'codex'}), frozenset({'notifications', 'shell'}), frozenset(), 'Default'), context)
            self.assertTrue(any(x.feature == 'notifications' and x.state == 'missing_dependency' for x in findings))
            self.assertTrue(any(x.feature == 'shell' and x.state == 'ready' for x in findings))

    def test_claude_does_not_select_codex_only_features(self):
        with Fixture() as f:
            context = discover(resolve_paths(), f.runner)
            result = plan(context, Selection(frozenset({'claude'}), frozenset({'clipboard', 'shell'}), frozenset(), 'Default'))
            self.assertNotIn('clipboard', result.selection.features)
            self.assertIn('shell', result.selection.features)
            self.assertTrue(any(x.feature == 'clipboard' and x.state == 'unavailable' for x in result.changes.findings))
            self.assertEqual(result.changes.edits, [])

    def test_shortcuts_require_explicit_valid_selection(self):
        with Fixture() as f:
            context = discover(resolve_paths(), f.runner)
            for features, shortcuts in (({'shell'}, {'ctrl-q'}), ({'shortcuts'}, set()), ({'shortcuts'}, {'unknown'})):
                findings = validate(Selection(frozenset({'codex'}), frozenset(features), frozenset(shortcuts), 'Default'), context)
                self.assertTrue(any(x.state == 'conflict' for x in findings))
