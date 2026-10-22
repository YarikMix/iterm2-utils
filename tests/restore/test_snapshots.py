"""Only complete inventories of current pane owners may replace a good snapshot."""
import concurrent.futures
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codexlib import iterm, registry, snapshots, store
from codexlib.models import Pane
from tests.restore.helpers import TerminalTools, write_session

SID = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
THIRD = "33333333-3333-4333-8333-333333333333"
TERMS = ["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "cccccccc-cccc-4ccc-8ccc-cccccccccccc"]


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = store.paths(self.root / "home", self.root / "cache")
        self.tools = TerminalTools(self.root)
        self.client = iterm.ITerm(str(self.tools.it2), str(self.tools.ps))
        self.launch = self.client.launch_id()
        self.started = self.client.identity(100)
        self.tools.set_inventory(
            [{"id": "w0t0p0:" + TERMS[0].upper(), "tab_id": "T1", "window_id": "W1"},
             {"id": TERMS[1], "tab_id": "T1", "window_id": "W1"},
             {"id": TERMS[2], "tab_id": "T2", "window_id": "W2"}],
            [{"id": "T2", "index": 0, "window_id": "W2"},
             {"id": "T1", "index": 0, "window_id": "W1"}], [{"id": "W1"}, {"id": "W2"}])
        self.add_session(TERMS[0], SID, 3)
        self.add_session(TERMS[1], OTHER, 1)
        self.add_session(TERMS[2], THIRD, 2)

    def add_session(self, terminal, sid, now):
        reg = registry.register(self.paths, terminal, 100, self.started, self.launch, now)
        path = write_session(self.paths.codex_home, sid, self.root)
        event = {"hook_event_name": "Stop", "session_id": sid, "transcript_path": str(path), "cwd": str(self.root)}
        self.assertTrue(registry.accept_event(self.paths, reg.token, terminal, event, self.client.identity, now + 1))
        return reg

    def saved(self):
        return (self.paths.state_dir / "tabs.json").read_bytes()

    def test_order_and_earliest_pane(self):
        self.assertTrue(snapshots.capture(self.paths, self.client, 10))
        snapshot = snapshots.candidate(self.paths, "next-launch")
        self.assertEqual(len(snapshot.tabs), 2)
        self.assertEqual([t.session.session_id for t in snapshot.tabs], [OTHER, THIRD])
        self.assertEqual([t.order for t in snapshot.tabs], [(1, 1), (2, 1)])
        self.assertIsNone(snapshots.candidate(self.paths, self.launch))
        self.assertEqual((self.paths.state_dir / "tabs.json").stat().st_mode & 0o777, 0o600)

    def test_partial_inventory_preserves_snapshot(self):
        self.assertTrue(snapshots.capture(self.paths, self.client, 10))
        before = self.saved()
        valid_tabs = (self.tools.root / "tab-list.json").read_text()
        bad = [[], [{"id": "T1", "index": 0}], [{"id": "T1", "index": 0, "window_id": "missing"}]]
        for tabs in bad:
            with self.subTest(tabs=tabs):
                (self.tools.root / "tab-list.json").write_text(json.dumps(tabs))
                self.assertFalse(snapshots.capture(self.paths, self.client, 20))
                self.assertEqual(self.saved(), before)
        (self.tools.root / "tab-list.json").write_text("not-json")
        self.assertFalse(snapshots.capture(self.paths, self.client, 20))
        with patch.object(self.client, "panes", side_effect=OSError("unavailable")):
            self.assertFalse(snapshots.capture(self.paths, self.client, 20))
        (self.tools.root / "tab-list.json").write_text(valid_tabs)
        with patch.object(self.client, "launch_id", side_effect=[self.launch, "changed"]):
            self.assertFalse(snapshots.capture(self.paths, self.client, 20))
        self.assertEqual(self.saved(), before)

    def test_new_launch_and_late_capture(self):
        self.assertTrue(snapshots.capture(self.paths, self.client, 10))
        # A new iTerm launch has no old active owners; valid empty state rotates history.
        with patch.object(self.client, "launch_id", return_value="new-launch"):
            self.assertTrue(snapshots.capture(self.paths, self.client, 30))
            self.assertFalse(snapshots.capture(self.paths, self.client, 20))
        candidate = snapshots.candidate(self.paths, "new-launch")
        self.assertEqual(candidate.launch, self.launch)
        self.assertEqual(len(candidate.tabs), 2)
        self.assertEqual(store.read(self.paths, "tabs.json")["saved_at"], 30)

    def test_no_iterm_and_untrusted_registry_preserve_snapshot(self):
        self.assertTrue(snapshots.capture(self.paths, self.client, 10))
        before = self.saved()
        self.tools.set_ps(False)
        self.assertFalse(snapshots.capture(self.paths, self.client, 20))
        self.tools.set_ps()
        for content in ("{", '{"version":1}', '{"version":1,"registrations":[{}]}', None):
            target = self.paths.state_dir / "registry.json"
            if content is None:
                target.unlink()
            else:
                target.write_text(content)
            self.assertFalse(snapshots.capture(self.paths, self.client, 20))
            self.assertEqual(self.saved(), before)

    def test_trustworthy_empty_inventory_and_registry(self):
        store.write(self.paths, "registry.json", {"version": 1, "registrations": []})
        self.tools.set_inventory([], [], [])
        self.assertTrue(snapshots.capture(self.paths, self.client, 10))
        self.assertEqual(snapshots.candidate(self.paths, "other").tabs, [])

    def test_owner_change_between_live_and_publish_cannot_publish(self):
        self.assertTrue(snapshots.capture(self.paths, self.client, 10))
        before = self.saved()
        original = registry.live
        def changed(*args):
            result = original(*args)
            registry.register(self.paths, TERMS[0], 100, self.started, self.launch, 15)
            return result
        with patch.object(registry, "live", side_effect=changed):
            self.assertFalse(snapshots.capture(self.paths, self.client, 20))
        self.assertEqual(self.saved(), before)

    def test_finished_source_owner_cannot_publish_even_while_pane_survives(self):
        for registration in store.read(self.paths, "registry.json")["registrations"]:
            registry.finish(self.paths, registration["token"])
        source = self.add_session(TERMS[0], SID, 4)
        self.assertTrue(snapshots.capture(self.paths, self.client, 10))
        before = self.saved()
        registry.finish(self.paths, source.token)
        self.assertFalse(snapshots.capture(self.paths, self.client, 20, required_terminal=TERMS[0]))
        self.assertEqual(self.saved(), before)

    def test_source_token_must_still_own_the_panel(self):
        source = next(item for item in store.read(self.paths, "registry.json")["registrations"]
                      if item["terminal"] == TERMS[0])
        self.assertTrue(snapshots.capture(self.paths, self.client, 10))
        before = self.saved()
        replacement = self.add_session(TERMS[0], SID, 4)
        self.assertFalse(snapshots.capture(self.paths, self.client, 20,
                                         required_terminal=TERMS[0], required_token=source["token"]))
        self.assertEqual(self.saved(), before)
        self.assertTrue(snapshots.capture(self.paths, self.client, 20,
                                        required_terminal=TERMS[0], required_token=replacement.token))

    def test_contention_and_parallel_captures_keep_newest(self):
        self.assertTrue(snapshots.capture(self.paths, self.client, 10))
        before = self.saved()
        with store.lock(self.paths, "state.lock"):
            self.assertFalse(snapshots.capture(self.paths, self.client, 20))
        self.assertEqual(self.saved(), before)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda now: snapshots.capture(self.paths, self.client, now), [30, 20]))
        self.assertIn(True, results)
        self.assertEqual(store.read(self.paths, "tabs.json")["saved_at"], 30)

    def test_corrupt_snapshot_candidate_is_unavailable(self):
        store.write(self.paths, "tabs.json", {"version": 1, "tabs": []})
        self.assertIsNone(snapshots.candidate(self.paths, "next"))

    def test_iterm_identities_inventory_and_actions(self):
        self.assertEqual(self.launch, "200:Thu Oct 15 09:00:00 2026")
        self.assertEqual(self.started, "Thu Oct 15 10:00:00 2026")
        self.assertIsNone(self.client.identity(999))
        self.assertEqual(self.client.panes(), [Pane(TERMS[0], "T1", "W1", 1, 1), Pane(TERMS[1], "T1", "W1", 1, 1), Pane(TERMS[2], "T2", "W2", 2, 1)])
        self.tools.set_inventory([{"id": TERMS[0], "tab_id": "T-new", "window_id": "W1"}], [], [])
        self.assertEqual(self.client.new_tab("W1"), TERMS[0])
        self.client.run(TERMS[0], "cd -- '/a b' && codex resume " + SID)
        self.client.focus(TERMS[0])
        calls = self.tools.calls()
        self.assertIn(["it2", "tab", "new", "--window", "W1"], calls)
        self.assertIn(["it2", "session", "run", "cd -- '/a b' && codex resume " + SID, "-s", TERMS[0].upper()], calls)
        self.assertIn(["it2", "session", "focus", TERMS[0].upper()], calls)

    def test_new_tab_waits_for_fifth_inventory_and_matches_session_uuid(self):
        from unittest.mock import patch
        terminal = TERMS[0].upper()
        listing = [{"id": terminal, "tab_id": "T-new", "window_id": "pty-UPPER"}]
        inventories = iter([[], [], [], [], listing])
        with patch.object(self.client, "_run", return_value="Created new tab: " + terminal), patch.object(
                self.client, "_list", side_effect=lambda kind: next(inventories)), patch(
                "codexlib.iterm.time.sleep") as sleep:
            self.assertEqual(self.client.new_tab("pty-UPPER"), TERMS[0])
        self.assertEqual(sleep.call_args_list, [unittest.mock.call(0.2)] * 4)
