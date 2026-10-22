"""Trust and ownership boundaries for the interactive-session registry."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codexlib import registry, store, transcripts
from codexlib.models import Pane
from tests.restore.helpers import write_session


SID = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
TERMINAL = "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"
FOREIGN = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "codex"
        self.cwd = self.root / "project"
        self.cwd.mkdir()
        self.paths = store.paths(self.home, self.root / "cache")
        self.transcript = write_session(self.home, SID, self.cwd)
        self.reg = self.register()
        self.identity = lambda pid: "shell-start" if pid == 100 else None
        self.panes = [Pane(TERMINAL.lower(), "tab", "window", 1, 1)]

    def register(self, **changes):
        args = dict(terminal=TERMINAL, shell_pid=100,
                    shell_started="shell-start", launch="iterm-start", now=1.0)
        args.update(changes)
        return registry.register(self.paths, **args)

    def event(self, **changes):
        event = dict(hook_event_name="SessionStart", session_id=SID,
                     cwd=str(self.cwd), transcript_path=str(self.transcript))
        event.update(changes)
        return event

    def accept(self, event=None, **changes):
        args = dict(token=self.reg.token, terminal=TERMINAL,
                    event=self.event() if event is None else event,
                    identity=self.identity, now=2.0)
        args.update(changes)
        return registry.accept_event(self.paths, **args)

    def rewrite_header(self, **changes):
        lines = self.transcript.read_text().splitlines()
        header = json.loads(lines[0])
        header["payload"].update(changes)
        self.transcript.write_text(json.dumps(header) + "\n" + "\n".join(lines[1:]))

    # Accepting any event without validating its transcript would break these cases.
    def test_bind_only_main_interactive(self):
        for name in ("SessionStart", "UserPromptSubmit", "Stop"):
            with self.subTest(name=name):
                self.assertTrue(self.accept(self.event(hook_event_name=name)))
        for source, originator in (({"subagent": "worker"}, "codex-tui"),
                                    ("exec", "codex-exec"), ("cli", "codex-exec")):
            with self.subTest(source=source, originator=originator):
                write_session(self.home, SID, self.cwd, source, originator)
                self.assertFalse(self.accept())
        write_session(self.home, SID, self.cwd)
        self.assertFalse(self.accept(self.event(session_id=OTHER)))
        self.assertFalse(self.accept(self.event(hook_event_name="SessionEnd")))

    def test_outside_or_symlink_outside_home(self):
        outside = write_session(self.root / "outside", SID, self.cwd)
        self.assertFalse(self.accept(self.event(transcript_path=str(outside))))
        link = self.home / "sessions" / "linked.jsonl"
        link.symlink_to(outside)
        self.assertFalse(self.accept(self.event(transcript_path=str(link))))

    def test_missing_malformed_and_non_header_transcript(self):
        for text in (None, "not json\n", "{}\n", '[]\n',
                     '{"type":"response_item","payload":{}}\n'):
            with self.subTest(text=text):
                if text is None:
                    self.transcript.unlink(missing_ok=True)
                else:
                    self.transcript.write_text(text)
                self.assertFalse(self.accept())

    def test_both_supported_header_ids_and_conflicts(self):
        self.rewrite_header(session_id=SID)
        self.assertTrue(self.accept())
        self.rewrite_header(session_id=OTHER)
        self.assertFalse(self.accept())
        header = json.loads(self.transcript.read_text().splitlines()[0])
        del header["payload"]["id"]
        header["payload"]["session_id"] = SID
        self.transcript.write_text(json.dumps(header) + "\n")
        self.assertTrue(self.accept())

    def test_absolute_current_and_header_cwds_required(self):
        self.assertFalse(self.accept(self.event(cwd="relative")))
        self.rewrite_header(cwd="relative")
        self.assertFalse(self.accept())

    def test_bad_uuid_and_missing_event_fields(self):
        self.assertFalse(self.accept(self.event(session_id="not-a-uuid")))
        for key in ("session_id", "cwd", "transcript_path", "hook_event_name"):
            event = self.event()
            del event[key]
            self.assertFalse(self.accept(event))
        for event in ([], None, {"session_id": []}):
            self.assertFalse(registry.accept_event(
                self.paths, self.reg.token, TERMINAL, event, self.identity, 2.0))

    def test_reused_pid_and_late_hook(self):
        self.assertTrue(self.accept())
        current = self.register(now=3.0, shell_started="new-shell")
        self.assertNotEqual(current.token, self.reg.token)
        self.assertFalse(self.accept())
        self.assertEqual(registry.live(self.paths, self.panes, self.identity), [])
        self.assertFalse(self.accept(token=current.token))
        self.assertFalse(self.accept(identity=lambda pid: None))

    def test_current_call_owns_panel_and_session_id_is_immutable(self):
        self.assertTrue(self.accept())
        other_path = write_session(self.home, OTHER, self.cwd)
        self.assertFalse(self.accept(self.event(session_id=OTHER,
                                                transcript_path=str(other_path))))
        new = self.register(now=4.0, request="restore-request")
        self.assertFalse(self.accept())
        self.assertTrue(self.accept(self.event(session_id=OTHER,
                                               transcript_path=str(other_path)), token=new.token, now=5.0))
        live = registry.live(self.paths, self.panes, self.identity)
        self.assertEqual(len(live), 1)
        self.assertEqual(live[0].session.session_id, OTHER)
        self.assertEqual(live[0].request, "restore-request")

    def test_foreign_panel_and_dead_shell_ignored(self):
        self.assertFalse(self.accept(terminal=FOREIGN))
        self.assertFalse(self.accept(identity=lambda pid: None))
        self.assertTrue(self.accept())
        self.assertEqual(registry.live(self.paths, [], self.identity), [])
        self.assertEqual(registry.live(self.paths, self.panes, lambda pid: None), [])

    def test_finish_preserves_saved_tabs(self):
        self.assertTrue(self.accept())
        snapshot = {"version": 1, "tabs": ["preserved"]}
        store.write(self.paths, "tabs.json", snapshot)
        before = (self.paths.state_dir / "tabs.json").read_bytes()
        registry.finish(self.paths, self.reg.token)
        self.assertFalse(self.accept())
        self.assertEqual(registry.live(self.paths, self.panes, self.identity), [])
        self.assertEqual((self.paths.state_dir / "tabs.json").read_bytes(), before)
        registry.finish(self.paths, "unknown-token")

    def test_metadata_only_and_private_storage(self):
        write_session(self.home, SID, self.cwd, prompt="SECRET_TEST_PROMPT")
        self.assertTrue(self.accept(self.event(prompt="SECRET_TEST_PROMPT",
                                               reply="SECRET_TEST_REPLY")))
        contents = b"".join(p.read_bytes() for p in self.paths.state_dir.iterdir())
        self.assertNotIn(b"SECRET_TEST_PROMPT", contents)
        self.assertNotIn(b"SECRET_TEST_REPLY", contents)
        self.assertEqual(self.paths.state_dir.stat().st_mode & 0o777, 0o700)
        for name in ("registry.json", "state.lock"):
            self.assertEqual((self.paths.state_dir / name).stat().st_mode & 0o777, 0o600)

    def test_home_partitions_use_full_filesystem_sha256(self):
        other = store.paths(self.root / "other-home", self.root / "cache")
        expected = hashlib.sha256(os.fsencode(self.home.resolve())).hexdigest()
        self.assertEqual(self.paths.state_dir.name, expected)
        self.assertEqual(self.paths.codex_home, self.home.resolve())
        self.assertNotEqual(other.state_dir, self.paths.state_dir)
        self.assertEqual(registry.live(other, self.panes, self.identity), [])
        alias = self.root / "alias"
        alias.symlink_to(self.home, target_is_directory=True)
        self.assertEqual(store.paths(alias, self.root / "cache"), self.paths)

    def test_terminal_normalization_and_registration_validation(self):
        self.assertEqual(self.reg.terminal, TERMINAL.lower())
        self.assertTrue(self.accept(terminal="w0t0p0:" + TERMINAL))
        self.assertEqual(len(registry.live(self.paths, self.panes, self.identity)), 1)
        for changes in ({"terminal": "invalid"}, {"shell_pid": 0},
                        {"shell_started": ""}, {"launch": ""}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.register(**changes)

    def test_store_missing_corruption_and_io_error_are_distinct(self):
        self.assertIsNone(store.read(self.paths, "missing.json"))
        target = self.paths.state_dir / "registry.json"
        for content in ("invalid", "[]", '{"version":2}', '{"version":1,"registrations":{}}'):
            with self.subTest(content=content):
                target.write_text(content)
                with self.assertRaises(ValueError):
                    registry.live(self.paths, self.panes, self.identity)
                with self.assertRaises(ValueError):
                    self.register()
        target.unlink()
        target.mkdir()
        with self.assertRaises(OSError):
            store.read(self.paths, "registry.json")

    def test_atomic_write_keeps_old_data_on_replace_failure(self):
        store.write(self.paths, "tabs.json", {"version": 1, "old": True})
        with patch("os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                store.write(self.paths, "tabs.json", {"version": 1, "new": True})
        self.assertEqual(store.read(self.paths, "tabs.json"), {"version": 1, "old": True})
        self.assertEqual(sorted(p.name for p in self.paths.state_dir.iterdir()),
                         ["registry.json", "state.lock", "tabs.json"])

    def test_lock_has_bounded_wait(self):
        with store.lock(self.paths, "state.lock"):
            with self.assertRaises(TimeoutError):
                with store.lock(self.paths, "state.lock"):
                    self.fail("a second lock must not be acquired")

    def test_title_string_and_content_blocks(self):
        for content in ("  Починить вкладки\n и окна  ",
                        [{"type": "input_text", "text": "Починить вкладки\n и окна"}]):
            message = {"type": "response_item", "payload": {
                "type": "message", "role": "user", "content": content}}
            self.transcript.write_text(self.transcript.read_text().splitlines()[0] +
                                       "\n" + json.dumps(message) + "\n")
            session = transcripts.validate(self.transcript, SID, self.home, self.cwd)
            self.assertEqual(transcripts.title(session), "Починить вкладки и окна")

    def test_title_ignores_injected_context(self):
        texts = ["# AGENTS.md instructions\nRules", "<environment_context>ctx",
                 "Починить вкладки", "<skill>instructions"]
        kinds = ["agents_md.instructions", "environments.environment_context",
                 "user.text", "skills.selected_skill_instructions"]
        for metadata in (True, False):
            with self.subTest(metadata=metadata):
                payload = {"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": text} for text in texts]}
                if metadata:
                    payload["internal_chat_message_metadata_passthrough"] = {
                        "content_item_kinds": kinds}
                self.transcript.write_text(self.transcript.read_text().splitlines()[0] +
                    "\n" + json.dumps({"type": "response_item", "payload": payload}) + "\n")
                session = transcripts.validate(self.transcript, SID, self.home, self.cwd)
                self.assertEqual(transcripts.title(session), "Починить вкладки")

    def test_title_falls_back_to_short_id_and_ignores_non_user_text(self):
        payload = {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "Injected text"}],
            "internal_chat_message_metadata_passthrough": {
                "content_item_kinds": ["skills.selected_skill_instructions"]}}
        self.transcript.write_text(self.transcript.read_text().splitlines()[0] +
            "\n" + json.dumps({"type": "response_item", "payload": payload}) + "\n")
        session = transcripts.validate(self.transcript, SID, self.home, self.cwd)
        self.assertEqual(transcripts.title(session), "11111111")


if __name__ == "__main__":
    unittest.main()
