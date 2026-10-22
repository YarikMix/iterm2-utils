"""Offline restore integration: real state and registrations, external terminal double."""
import contextlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from codexlib import registry, restore, snapshots, store
from codexlib.models import Pane, SavedTab, Session, Snapshot
from tests.restore.helpers import TerminalTools, write_session

SID1 = "11111111-1111-4111-8111-111111111111"
SID2 = "22222222-2222-4222-8222-222222222222"
SID3 = "33333333-3333-4333-8333-333333333333"
TERM = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class Terminal:
    def __init__(self, paths):
        self.paths = paths
        self.inventory = [Pane(TERM, "T1", "W1", 1, 1)]
        self.opened, self.commands, self.focused = [], [], []
        self.timeout = False
        self.fail = 0

    def launch_id(self):
        return "new-launch"

    def panes(self):
        return list(self.inventory)

    def identity(self, pid):
        return "shell-start"

    def new_tab(self, window):
        self.opened.append(window)
        if self.fail:
            self.fail -= 1
            raise ValueError("new tab failed")
        terminal = str(uuid4())
        self.inventory.append(Pane(terminal, "T" + terminal, window, 1, len(self.inventory) + 1))
        return terminal

    def run(self, terminal, command):
        self.commands.append((terminal, command))
        if self.timeout:
            raise TimeoutError("response lost after sending")
        args = shlex.split(command)
        request = next(arg.split("=", 1)[1] for arg in args if arg.startswith("CODEX_RESTORE_REQUEST="))
        registry.register(self.paths, terminal, 100, "shell-start", "new-launch", time.time(), request)

    def focus(self, terminal):
        self.focused.append(terminal)


class SharedTerminal(Terminal):
    """State shared by independently running coordinators, like the external app."""
    def panes(self):
        return [Pane(*entry) for entry in (json.loads((self.paths.state_dir / "panes-fixture.json").read_text()))]

    def new_tab(self, window):
        terminal = str(uuid4())
        panes = self.panes()
        with (self.paths.state_dir / "new-tabs.log").open("a") as stream:
            stream.write(terminal + "\n")
        (self.paths.state_dir / "panes-fixture.json").write_text(json.dumps([
            [p.terminal, p.tab_id, p.window_id, p.window_no, p.tab_no] for p in panes] +
            [[terminal, "T" + terminal, window, 1, len(panes) + 1]]))
        return terminal


def concurrent_restore(paths, queue, gate, auto):
    try:
        client = SharedTerminal(paths)
        gate.wait()
        if auto:
            queue.put(len(restore.choices(paths, client, True, 200)[0]))
        else:
            first = restore.prepare(paths, client, [SID2, SID1, SID3], TERM, 200)
            queue.put(first.session.session_id if first else None)
    except Exception as exc:
        queue.put("ERROR: " + str(exc))


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.paths = store.paths(self.root / "home", self.root / "custom-cache")
        self.sessions = []
        for number, sid in enumerate((SID1, SID2, SID3), 1):
            cwd = self.root / ("project" + str(number))
            cwd.mkdir()
            path = write_session(self.paths.codex_home, sid, cwd)
            os.utime(path, (100, 100))
            self.sessions.append(Session(sid, cwd, path, self.paths.codex_home))
        self.save(self.sessions)
        self.client = Terminal(self.paths)

    def save(self, sessions, launch="old-launch", name="tabs.json"):
        store.write(self.paths, name, snapshots._encode(Snapshot(launch, 100, [
            SavedTab((1, index), session) for index, session in enumerate(sessions, 1)])))

    def pending(self):
        return store.read(self.paths, "pending.json")["pending"]

    def test_resumed_current_cwd_survives_binding_snapshot_and_restore_revalidation(self):
        original = self.sessions[0]
        current = self.root / "resumed project"
        current.mkdir()
        reg = registry.register(self.paths, TERM, 100, "shell-start", "new-launch", 101)
        event = {"hook_event_name": "Stop", "session_id": SID1,
                 "cwd": str(current), "transcript_path": str(original.transcript)}
        self.assertTrue(registry.accept_event(self.paths, reg.token, TERM, event,
                                             self.client.identity, 102))
        live = registry.live(self.paths, self.client.panes(), self.client.identity)
        self.assertEqual(len(live), 1)
        self.assertEqual(live[0].session.cwd, current)
        self.assertTrue(snapshots.capture(self.paths, self.client, 103,
                                         required_terminal=TERM, required_token=reg.token))
        saved = store.read(self.paths, "tabs.json")["tabs"]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["session"]["cwd"], str(current))
        self.assertEqual(json.loads(original.transcript.read_text().splitlines()[0])[
            "payload"]["cwd"], str(original.cwd))
        registry.finish(self.paths, reg.token)
        self.client.launch_id = lambda: "next-launch"
        choices, notes = restore.choices(self.paths, self.client, False, 200)
        self.assertEqual(notes, [])
        self.assertEqual(len(choices), 1)
        self.assertEqual((choices[0].session.session_id, choices[0].session.cwd), (SID1, current))
        first = restore.prepare(self.paths, self.client, [SID1], TERM, 200)
        self.assertEqual((first.session.session_id, first.session.cwd), (SID1, current))
        resumed = registry.register(self.paths, TERM, 100, "shell-start", "next-launch", 201,
                                    request=first.request)
        self.assertEqual(resumed.session.cwd, current)
        self.assertEqual(self.pending()[0]["status"], "acknowledged")
        registry.finish(self.paths, resumed.token)
        self.assertEqual(self.pending(), [])

    def test_filter_and_original_order(self):
        reg = registry.register(self.paths, TERM, 100, "shell-start", "new-launch", 1)
        registry.accept_event(self.paths, reg.token, TERM, {"hook_event_name": "Stop", "session_id": SID3,
            "cwd": str(self.sessions[2].cwd), "transcript_path": str(self.sessions[2].transcript)}, self.client.identity, 2)
        choices, notes = restore.choices(self.paths, self.client, False, 3700)
        self.assertEqual([c.session.session_id for c in choices], [SID1, SID2])
        self.assertEqual(len(choices), 2)
        self.assertEqual([c.age for c in choices], ["1 ч", "1 ч"])
        first = restore.prepare(self.paths, self.client, [SID2, SID1], TERM, 3700)
        self.assertEqual(first.session.session_id, SID1)
        self.assertEqual(len(self.client.opened), 1)
        self.assertEqual(len(self.client.commands), 1)
        self.assertEqual(self.client.focused, [TERM])
        self.assertEqual([entry["session"]["session_id"] for entry in self.pending()], [SID1, SID2])

    def test_invalid_and_empty_selection_does_not_open(self):
        for selection in ([], ["foreign"], [SID1, SID1], [str(uuid4())]):
            try:
                result = restore.prepare(self.paths, self.client, selection, TERM, 200)
                self.assertIsNone(result)
            except ValueError:
                pass
        self.assertEqual(len(self.client.opened), 0)
        self.assertEqual(len(self.client.commands), 0)

    def test_revalidate_missing_paths_and_current_launch(self):
        self.sessions[0].cwd.rmdir()
        self.sessions[1].transcript.unlink()
        choices, notes = restore.choices(self.paths, self.client, False, 200)
        self.assertEqual([choice.session.session_id for choice in choices], [SID3])
        self.assertEqual(len(notes), 2)
        self.save(self.sessions, "new-launch")
        self.assertEqual(restore.choices(self.paths, self.client, False, 200)[0], [])
        self.save([self.sessions[2]], name="tabs-prev.json")
        self.assertEqual(len(restore.choices(self.paths, self.client, False, 200)[0]), 1)

    def test_auto_claim_once_even_after_escape_or_two_shells(self):
        lists = [restore.choices(self.paths, self.client, True, 200)[0] for _ in range(2)]
        self.assertEqual(sum(bool(value) for value in lists), 1)
        self.assertEqual(len(restore.choices(self.paths, self.client, False, 200)[0]), 3)
        first = restore.prepare(self.paths, self.client, [SID1], TERM, 200)
        restore.cancel(self.paths, first.request)
        self.assertEqual(restore.choices(self.paths, self.client, True, 200)[0], [])
        self.assertEqual(len(restore.choices(self.paths, self.client, False, 200)[0]), 3)

    def test_prepare_claims_auto_before_any_list(self):
        restore.prepare(self.paths, self.client, [SID1], TERM, 200)
        self.assertEqual(restore.choices(self.paths, self.client, True, 200)[0], [])

    def test_auto_never_reoffers_snapshot_in_later_launch_or_second_snapshot_in_same_launch(self):
        self.assertEqual(len(restore.choices(self.paths, self.client, True, 200)[0]), 3)
        self.client.launch_id = lambda: "third-launch"
        self.assertEqual(restore.choices(self.paths, self.client, True, 201)[0], [])
        self.assertEqual(len(restore.choices(self.paths, self.client, False, 201)[0]), 3)
        self.client.launch_id = lambda: "new-launch"
        self.save(self.sessions, "different-old-launch")
        self.assertEqual(restore.choices(self.paths, self.client, True, 202)[0], [])
        self.assertEqual(len(restore.choices(self.paths, self.client, False, 202)[0]), 3)

    def test_manual_restore_in_new_launch_marks_it_processed_even_for_previously_offered_snapshot(self):
        restore.choices(self.paths, self.client, True, 200)
        self.client.launch_id = lambda: "third-launch"
        first = restore.prepare(self.paths, self.client, [SID1], TERM, 201)
        restore.cancel(self.paths, first.request)
        self.save(self.sessions, "different-old-launch")
        self.assertEqual(restore.choices(self.paths, self.client, True, 202)[0], [])
        self.assertEqual(len(restore.choices(self.paths, self.client, False, 202)[0]), 3)

    def test_run_timeout_does_not_duplicate(self):
        self.client.timeout = True
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            restore.prepare(self.paths, self.client, [SID1, SID2], TERM, 200)
            restore.prepare(self.paths, self.client, [SID1, SID2], TERM, 201)
        self.assertEqual(len(self.client.opened), 1)
        self.assertEqual(len(self.client.commands), 1)
        self.assertIn("не подтверждён", stderr.getvalue())
        self.assertIn("codex resume " + SID2, stderr.getvalue())
        self.assertEqual(len(self.pending()), 2)
        restore.cancel(self.paths, self.pending()[1]["request"])
        self.assertEqual(len(self.pending()), 2)
        self.client.inventory = self.client.inventory[:1]
        self.assertEqual([c.session.session_id for c in restore.choices(self.paths, self.client, False, 202)[0]], [SID2, SID3])

    def test_stale_choices_inventory_cannot_remove_concurrently_sent_reservation(self):
        self.client.timeout = True
        listing_client = Terminal(self.paths)
        sent = []
        def inventory_before_concurrent_prepare():
            observed = self.client.panes()
            self.assertEqual(len(observed), 1)
            restore.prepare(self.paths, self.client, [SID1, SID2], TERM, 200)
            self.assertEqual(len(self.client.panes()), 2)
            sent.extend(self.pending())
            self.assertEqual([entry["status"] for entry in sent], ["reserved", "sent"])
            return observed
        listing_client.panes = inventory_before_concurrent_prepare
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            choices, notes = restore.choices(self.paths, listing_client, False, 201)
        self.assertEqual(self.pending(), sent)
        self.assertEqual([choice.session.session_id for choice in choices], [SID3])
        self.assertIsNone(restore.prepare(self.paths, self.client, [SID2], TERM, 202))
        self.assertEqual(len(self.client.opened), 1)
        self.assertEqual(len(self.client.commands), 1)
        self.assertEqual(len(self.client.panes()), 2)
        self.assertIn("не подтверждён", stderr.getvalue())

    def test_failed_new_tab_releases_only_that_reservation_and_continues(self):
        self.client.fail = 1
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            first = restore.prepare(self.paths, self.client, [SID1, SID2, SID3], TERM, 200)
        self.assertEqual(first.session.session_id, SID1)
        self.assertEqual(len(self.client.opened), 2)
        self.assertEqual(len(self.client.commands), 1)
        self.assertEqual([entry["session"]["session_id"] for entry in self.pending()], [SID1, SID3])
        self.assertIn("codex resume " + SID2, stderr.getvalue())

    def test_missing_source_window_and_unavailable_iterm_preserve_snapshots(self):
        before = (self.paths.state_dir / "tabs.json").read_bytes()
        self.client.inventory = []
        with self.assertRaises(ValueError):
            restore.prepare(self.paths, self.client, [SID1, SID2], TERM, 200)
        self.assertEqual(len(self.client.opened), 0)
        self.assertFalse((self.paths.state_dir / "pending.json").exists())
        self.assertEqual((self.paths.state_dir / "tabs.json").read_bytes(), before)

    def test_acknowledgement_and_finish_work_under_restore_lock(self):
        first = restore.prepare(self.paths, self.client, [SID1], TERM, 200)
        with store.lock(self.paths, "restore.lock"):
            wrong = registry.register(self.paths, str(uuid4()), 100, "shell-start", "new-launch", 201, first.request)
            self.assertIsNone(wrong.session)
            reg = registry.register(self.paths, TERM, 100, "shell-start", "new-launch", 202, first.request)
            self.assertEqual(reg.session.session_id, SID1)
            restore.cancel(self.paths, first.request)
            self.assertEqual(len(self.pending()), 1)
            registry.finish(self.paths, reg.token)
            self.assertEqual(self.pending(), [])
        self.assertEqual(len(restore.choices(self.paths, self.client, False, 203)[0]), 3)

    def test_cancel_only_matching_unstarted_request_and_revalidates_ack(self):
        first = restore.prepare(self.paths, self.client, [SID1], TERM, 200)
        restore.cancel(self.paths, str(uuid4()))
        self.assertEqual(len(self.pending()), 1)
        self.sessions[0].transcript.unlink()
        reg = registry.register(self.paths, TERM, 100, "shell-start", "new-launch", 201, first.request)
        self.assertIsNone(reg.session)
        restore.cancel(self.paths, first.request)
        self.assertEqual(self.pending(), [])

    def test_wrong_pane_supersession_cannot_release_another_panes_reservation(self):
        first = restore.prepare(self.paths, self.client, [SID1], TERM, 200)
        other = str(uuid4())
        wrong = registry.register(self.paths, other, 100, "shell-start", "new-launch", 201, first.request)
        registry.finish(self.paths, wrong.token)
        self.assertEqual(len(self.pending()), 1)
        registry.register(self.paths, other, 100, "shell-start", "new-launch", 202)
        self.assertEqual(len(self.pending()), 1)

    def test_finish_releases_expected_request_even_when_session_revalidation_failed(self):
        first = restore.prepare(self.paths, self.client, [SID1], TERM, 200)
        self.sessions[0].transcript.unlink()
        reg = registry.register(self.paths, TERM, 100, "shell-start", "new-launch", 201, first.request)
        self.assertIsNone(reg.session)
        registry.finish(self.paths, reg.token)
        self.assertEqual(self.pending(), [])

    def test_rows_strip_ansi_and_controls_and_do_not_contain_raw_cwd(self):
        write_session(self.paths.codex_home, SID1, self.sessions[0].cwd, prompt="hello\x1b[31mRED\x1b[0m\tline\n\x00end")
        choices, _ = restore.choices(self.paths, self.client, False, 200)
        rows = restore.rows(choices)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].split("\t")[:2], ["1", SID1])
        self.assertEqual(len(rows[0].split("\t")), 6)
        self.assertIn("helloRED", rows[0])
        self.assertNotIn(str(self.sessions[0].cwd), rows[0])
        self.assertFalse(any(ord(c) < 32 and c != "\t" for c in rows[0]))
        self.assertNotIn("\x1b", rows[0])

    def test_paths_are_values_not_shell_source(self):
        cwd = self.root / "space ' quote\tline\n$(touch INJECTED)"
        cwd.mkdir()
        home = self.root / "home ' \t\n$(touch INJECTED)"
        cache = self.root / "cache ' \t\n$(touch INJECTED)"
        session = Session(SID1, cwd, home / "unused", home)
        request = "44444444-4444-4444-8444-444444444444"
        command = restore.command(session, request, cache)
        expected = ["cd", "--", str(cwd), "&&", "CODEX_HOME=" + str(home),
                    "CODEX_RESTORE_CACHE_DIR=" + str(cache), "CODEX_RESTORE_REQUEST=" + request, "codex", "resume", SID1]
        self.assertEqual(shlex.split(command), expected)
        script = 'codex() { python3 -c \'import json,os,sys; print(json.dumps([os.getcwd(),os.getenv("CODEX_HOME"),os.getenv("CODEX_RESTORE_CACHE_DIR"),os.getenv("CODEX_RESTORE_REQUEST"),sys.argv[1:]]))\' "$@"; }; ' + command
        result = subprocess.run(["zsh", "-f", "-c", script], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [str(cwd), str(home), str(cache), request, ["resume", SID1]])
        self.assertFalse((self.root / "INJECTED").exists())
        self.assertFalse((cwd / "INJECTED").exists())

    def test_custom_cache_reaches_new_tabs(self):
        tools = TerminalTools(self.root)
        default_cache = self.root / "default-cache"
        wrapper = Path(__file__).resolve().parents[2] / "runtime/codex_restore/codex-sessions"
        def run_shell(terminal, command):
            self.client.commands.append((terminal, command))
            # A missing assignment uses an isolated fallback; never the real cache.
            function = 'codex() { if [[ -z "$CODEX_RESTORE_CACHE_DIR" ]]; then export CODEX_RESTORE_CACHE_DIR=' + shlex.quote(str(default_cache)) + '; fi; '
            function += shlex.quote(sys.executable) + ' ' + shlex.quote(str(wrapper))
            function += ' register --terminal ' + shlex.quote(terminal) + ' --shell-pid 100 --request "$CODEX_RESTORE_REQUEST"; }; '
            environment = dict(os.environ)
            for key in ("CODEX_HOME", "CODEX_RESTORE_CACHE_DIR", "CODEX_RESTORE_REQUEST"):
                environment.pop(key, None)
            environment.update(CODEX_RESTORE_PS=str(tools.ps), CODEX_RESTORE_ITERM_LAUNCH="new-launch")
            result = subprocess.run(["zsh", "-f", "-c", function + command], env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.client.run = run_shell
        self.client.identity = lambda pid: "Thu Oct 15 10:00:00 2026"
        restore.prepare(self.paths, self.client, [SID1, SID2], TERM, 200)
        terminal, command = self.client.commands[0]
        request = next(arg.split("=", 1)[1] for arg in shlex.split(command) if arg.startswith("CODEX_RESTORE_REQUEST="))
        new_registration = registry.live(self.paths, self.client.panes(), self.client.identity)[0]
        self.assertEqual(new_registration.request, request)
        self.assertEqual(new_registration.session.session_id, SID2)
        self.assertIn("CODEX_RESTORE_CACHE_DIR=" + str(self.root / "custom-cache"), command)
        self.assertFalse(default_cache.exists())

    def test_register_after_filter_before_reserve_is_not_opened_again(self):
        original = restore.choices
        def late_registration(*args):
            result = original(*args)
            reg = registry.register(self.paths, TERM, 100, "shell-start", "new-launch", 1)
            registry.accept_event(self.paths, reg.token, TERM, {"hook_event_name": "Stop", "session_id": SID1,
                "cwd": str(self.sessions[0].cwd), "transcript_path": str(self.sessions[0].transcript)}, self.client.identity, 2)
            return result
        with patch.object(restore, "choices", side_effect=late_registration):
            first = restore.prepare(self.paths, self.client, [SID1, SID2], TERM, 200)
        self.assertEqual(first.session.session_id, SID2)
        self.assertEqual(len(self.client.opened), 0)
        self.assertEqual(len(self.pending()), 1)

    def _process_pair(self, auto):
        (self.paths.state_dir / "panes-fixture.json").write_text(json.dumps([[TERM, "T1", "W1", 1, 1]]))
        context = multiprocessing.get_context("spawn")
        queue, gate = context.Queue(), context.Event()
        processes = [context.Process(target=concurrent_restore, args=(self.paths, queue, gate, auto)) for _ in range(2)]
        for process in processes:
            process.start()
        gate.set()
        results = [queue.get(timeout=8) for _ in processes]
        for process in processes:
            process.join(8)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 0)
        queue.close()
        return results

    def test_two_processes_restore_exactly_two_extra_tabs(self):
        self.assertCountEqual(self._process_pair(False), [SID1, None])
        opened = (self.paths.state_dir / "new-tabs.log").read_text().splitlines()
        self.assertEqual(len(opened), 2)
        self.assertEqual(len(set(opened)), 2)
        pending = self.pending()
        self.assertEqual([entry["session"]["session_id"] for entry in pending], [SID1, SID2, SID3])
        self.assertEqual(len(pending), 3)

    def test_two_processes_auto_claim_only_once(self):
        self.assertCountEqual(self._process_pair(True), [3, 0])


if __name__ == "__main__":
    unittest.main()
