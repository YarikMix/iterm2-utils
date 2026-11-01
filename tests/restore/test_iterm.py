"""Tab creation stays addressed, bounded and safe after an uncertain reply."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codexlib.iterm import ITerm, UnknownTabOutcome
from tests.restore.helpers import TerminalTools

TERMINAL = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


class ITermTabTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tools = TerminalTools(Path(temporary.name))
        self.client = ITerm(str(self.tools.it2), str(self.tools.ps))
        self.tools.set_inventory([
            {"id": "w0t0p0:" + TERMINAL.upper(), "tab_id": "T-new", "window_id": "W1"},
        ], [], [])

    def test_legacy_new_tab_argv_unchanged(self):
        self.assertEqual(self.client.new_tab("W1"), TERMINAL)
        self.assertEqual(self.tools.calls(), [
            ["it2", "tab", "new", "--window", "W1"],
            ["it2", "session", "list", "--json"],
        ])

    def test_explicit_profile_command_are_single_argv(self):
        profile = "Кодекс 'profile' $(false)"
        command = "zsh -lic 'codex -C /tmp/проект'\n# $(false)"
        self.assertEqual(self.client.new_tab("W1", profile=profile, command=command), TERMINAL)
        calls = self.tools.calls()
        self.assertEqual(calls[0], [
            "it2", "tab", "new", "--window", "W1", "--profile", profile, "--command", command,
        ])
        self.assertEqual(sum(call[1:3] == ["tab", "new"] for call in calls), 1)

    def test_result_must_belong_to_requested_window(self):
        unrelated = {"id": OTHER, "tab_id": "T-new", "window_id": "W2"}
        requested = {"id": TERMINAL, "tab_id": "T-new", "window_id": "W1"}
        with patch.object(self.client, "_list", side_effect=[[unrelated], [unrelated, requested]]), patch(
                "codexlib.iterm.time.sleep"):
            self.assertEqual(self.client.new_tab("W1"), TERMINAL)
        self.assertEqual(self.tools.calls(), [["it2", "tab", "new", "--window", "W1"]])

    def test_created_but_inventory_times_out_retains_tab_id(self):
        with patch.object(self.client, "_list", side_effect=TimeoutError("inventory deadline")):
            with self.assertRaises(UnknownTabOutcome) as caught:
                self.client.new_tab("W1")
        self.assertEqual(caught.exception.tab_id, "T-new")
        self.assertIsInstance(caught.exception.__cause__, TimeoutError)
        self.assertEqual(self.tools.calls(), [["it2", "tab", "new", "--window", "W1"]])

    def test_missing_or_ambiguous_inventory_is_unknown_without_retry(self):
        for inventory in ([], [
                {"id": TERMINAL, "tab_id": "T-new", "window_id": "W2"},
        ], [
                {"id": TERMINAL, "tab_id": "T-new", "window_id": "W1"},
                {"id": OTHER, "tab_id": "T-new", "window_id": "W1"},
        ]):
            with self.subTest(inventory=inventory), patch.object(
                    self.client, "_list", return_value=inventory), patch("codexlib.iterm.time.sleep"):
                before = len(self.tools.calls())
                with self.assertRaises(UnknownTabOutcome) as caught:
                    self.client.new_tab("W1")
                self.assertEqual(caught.exception.tab_id, "T-new")
                self.assertEqual(self.tools.calls()[before:], [["it2", "tab", "new", "--window", "W1"]])

    def test_invalid_optional_values_are_rejected_before_creation(self):
        for name in ("profile", "command"):
            for value in ("", " \t", "a\0b", 42, [], False):
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ValueError):
                        self.client.new_tab("W1", **{name: value})
        self.assertEqual(self.tools.calls(), [])
