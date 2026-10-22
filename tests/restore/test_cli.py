"""Hooks remain observational even on malformed input, disk failure and a slow tool."""
import io
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from codexlib import cli, registry, snapshots, store
from codexlib.models import SavedTab, Session, Snapshot
from tests.restore.helpers import TerminalTools, write_session

SID = "11111111-1111-4111-8111-111111111111"
TERM = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
WRAPPER = Path(__file__).resolve().parents[2] / "runtime/codex_restore/codex-sessions"


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.paths = store.paths(self.home, self.root / "cache")
        self.tools = TerminalTools(self.root)
        self.tools.set_inventory([{"id": TERM, "tab_id": "T1", "window_id": "W1"}], [{"id": "T1", "index": 0, "window_id": "W1"}], [{"id": "W1"}])
        self.environ = dict(os.environ, CODEX_HOME=str(self.home), CODEX_RESTORE_CACHE_DIR=str(self.root / "cache"), CODEX_RESTORE_IT2=str(self.tools.it2), CODEX_RESTORE_PS=str(self.tools.ps), ITERM_SESSION_ID="w0t0p0:" + TERM)
        self.environ.pop("CODEX_RESTORE_ITERM_LAUNCH", None)
        self.environ.pop("CODEX_RESTORE_TOKEN", None)
        path = write_session(self.home, SID, self.root, prompt="PRIVATE_PROMPT_MARKER")
        self.event = {"hook_event_name": "Stop", "session_id": SID, "transcript_path": str(path), "cwd": str(self.root), "prompt": "PRIVATE_PROMPT_MARKER"}

    def command(self, *args, payload="", executable=None):
        return subprocess.run([sys.executable, str(executable or WRAPPER), *args], input=payload, text=True, capture_output=True, env=self.environ, cwd=self.root, timeout=5)

    def register(self):
        result = self.command("register", "--terminal", TERM, "--shell-pid", "100")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.environ["CODEX_RESTORE_TOKEN"] = result.stdout.strip()
        return result.stdout.strip()

    def assert_observational(self, result):
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "{}"))
        self.assertEqual(result.stderr, "")

    def test_hook_saves_only_metadata_and_never_passes_payload_to_subprocess(self):
        self.register()
        self.assert_observational(self.command("hook", payload=json.dumps(self.event)))
        snapshot = store.read(self.paths, "tabs.json")
        self.assertEqual(snapshot["tabs"][0]["session"]["session_id"], SID)
        for path in self.paths.state_dir.iterdir():
            self.assertNotIn(b"PRIVATE_PROMPT_MARKER", path.read_bytes())
        self.assertNotIn("PRIVATE_PROMPT_MARKER", self.tools.log.read_text())
        self.assertNotIn(SID, self.tools.log.read_text())

    def test_hook_is_observational_for_malformed_input(self):
        for payload in ("{", "[]", "null", "{}"):
            self.assert_observational(self.command("hook", payload=payload))

    def test_hook_is_observational_on_disk_error(self):
        self.register()
        (self.paths.state_dir / "registry.json").unlink()
        (self.paths.state_dir / "registry.json").mkdir()
        self.assert_observational(self.command("hook", payload=json.dumps(self.event)))

    def test_finish_and_session_end_preserve_snapshot(self):
        token = self.register()
        self.assert_observational(self.command("hook", payload=json.dumps(self.event)))
        before = (self.paths.state_dir / "tabs.json").read_bytes()
        self.tools.log.unlink()
        self.assert_observational(self.command("hook", payload=json.dumps(dict(self.event, hook_event_name="SessionEnd"))))
        self.assertEqual(self.tools.calls(), [])
        self.assertEqual(self.command("finish", token).returncode, 0)
        self.register()
        self.assertEqual((self.paths.state_dir / "tabs.json").read_bytes(), before)

    def test_disappeared_source_pane_cannot_erase_last_good_snapshot(self):
        self.register()
        self.assert_observational(self.command("hook", payload=json.dumps(self.event)))
        before = (self.paths.state_dir / "tabs.json").read_bytes()
        self.tools.set_inventory([], [], [])
        self.assert_observational(self.command("hook", payload=json.dumps(self.event)))
        self.assertEqual((self.paths.state_dir / "tabs.json").read_bytes(), before)

    def test_finished_source_after_accept_cannot_erase_last_good_snapshot(self):
        token = self.register()
        self.assert_observational(self.command("hook", payload=json.dumps(self.event)))
        before = (self.paths.state_dir / "tabs.json").read_bytes()
        accept = registry.accept_event
        accepted = []
        def finish_after_accept(*args, **kwargs):
            result = accept(*args, **kwargs)
            accepted.append(result)
            registry.finish(self.paths, token)
            return result
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, self.environ, clear=True), patch.object(
                registry, "accept_event", side_effect=finish_after_accept), patch(
                "sys.stdin", io.StringIO(json.dumps(self.event))), patch(
                "sys.stdout", stdout), patch("sys.stderr", stderr):
            result = cli.main(["hook"])
        self.assertEqual(accepted, [True])
        self.assertEqual((result, stdout.getvalue().strip(), stderr.getvalue()), (0, "{}", ""))
        self.assertEqual((self.paths.state_dir / "tabs.json").read_bytes(), before)

    def test_replaced_source_after_accept_cannot_publish_for_a_different_token(self):
        self.register()
        self.assert_observational(self.command("hook", payload=json.dumps(self.event)))
        before = (self.paths.state_dir / "tabs.json").read_bytes()
        accept = registry.accept_event
        accepted = []
        def replace_after_accept(*args, **kwargs):
            result = accept(*args, **kwargs)
            accepted.append(result)
            source = store.read(self.paths, "registry.json")["registrations"][0]
            replacement = registry.register(self.paths, TERM, source["shell_pid"],
                                            source["shell_started"], source["launch"], time.time())
            accepted.append(accept(self.paths, replacement.token, TERM, self.event,
                                   args[4], replacement.started_at))
            return result
        stdout = io.StringIO()
        with patch.dict(os.environ, self.environ, clear=True), patch.object(
                registry, "accept_event", side_effect=replace_after_accept), patch(
                "sys.stdin", io.StringIO(json.dumps(self.event))), patch("sys.stdout", stdout):
            result = cli.main(["hook"])
        self.assertEqual(accepted, [True, True])
        self.assertEqual((result, stdout.getvalue().strip()), (0, "{}"))
        self.assertEqual((self.paths.state_dir / "tabs.json").read_bytes(), before)

    def test_hook_deadline_kills_slow_subprocess(self):
        self.register()
        (self.tools.root / "delay").write_text("10")
        start = time.monotonic()
        self.assert_observational(self.command("hook", payload=json.dumps(self.event)))
        self.assertLess(time.monotonic() - start, 3.0)
        pid = int(self.tools.pid.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        # A timed out hook must release the lock for subsequent operations.
        with store.lock(self.paths, "state.lock"):
            pass

    def test_hook_deadline_is_shared_by_all_inventory_commands(self):
        self.register()
        (self.tools.root / "delay").write_text("0.8")
        start = time.monotonic()
        self.assert_observational(self.command("hook", payload=json.dumps(self.event)))
        self.assertLess(time.monotonic() - start, 3.0)
        self.assertFalse((self.paths.state_dir / "tabs.json").exists())
        pid = int(self.tools.pid.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_regular_errors_are_visible_and_launch_override_and_symlink_work(self):
        self.assertNotEqual(self.command("register", "--terminal", "bad", "--shell-pid", "100").returncode, 0)
        self.assertTrue(self.command("finish").stderr)
        self.environ["CODEX_RESTORE_ITERM_LAUNCH"] = "test-launch"
        link = self.root / "linked-sessions"
        link.symlink_to(WRAPPER)
        result = self.command("register", "--terminal", TERM, "--shell-pid", "100", "--request", SID, executable=link)
        self.assertEqual(result.returncode, 0, result.stderr)
        direct = subprocess.run([str(link), "finish", result.stdout.strip()], text=True, capture_output=True, env=self.environ, cwd=self.root, timeout=5)
        self.assertEqual(direct.returncode, 0, direct.stderr)
        state = store.read(self.paths, "registry.json")["registrations"][0]
        self.assertEqual((state["launch"], state["request"]), ("test-launch", SID))

    def test_common_deadline_includes_lock_contention(self):
        token = self.register()
        with store.lock(self.paths, "state.lock"):
            start = time.monotonic()
            self.assert_observational(self.command("hook", payload=json.dumps(self.event)))
            self.assertLess(time.monotonic() - start, 3)

    def test_restore_cli_nul_protocol_list_and_cancel(self):
        session = Session(SID, self.root.resolve(), Path(self.event["transcript_path"]).resolve(), self.paths.codex_home)
        store.write(self.paths, "tabs.json", snapshots._encode(Snapshot("old-launch", 1, [SavedTab((1, 1), session)])))
        listed = self.command("restore-list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(listed.stdout.split("\t")[:2], ["1", SID])
        result = self.command("restore-open", payload=SID + "\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        fields = result.stdout.split("\0")
        self.assertEqual(len(fields), 6)
        self.assertEqual(fields[1:], [SID, str(self.root.resolve()), str(self.paths.codex_home),
                                    str(self.paths.state_dir.parent), ""])
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.command("restore-cancel", fields[0]).returncode, 0)
        self.assertEqual(store.read(self.paths, "pending.json")["pending"], [])
        self.assertEqual(self.command("restore-open", payload="").stdout, "")
        self.assertEqual(self.command("restore-list", "--auto").stdout, "")

    def test_restore_cli_unavailable_iterm_has_no_stdout_or_snapshot_mutation(self):
        store.write(self.paths, "tabs.json", {"version": 1, "launch": "old-launch", "saved_at": 1, "tabs": []})
        before = (self.paths.state_dir / "tabs.json").read_bytes()
        self.environ["CODEX_RESTORE_IT2"] = str(self.root / "absent-it2")
        result = self.command("restore-list")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr)
        self.assertEqual((self.paths.state_dir / "tabs.json").read_bytes(), before)


class ProcessRestoreTests(unittest.TestCase):
    setUp = CLITests.setUp
    command = CLITests.command
    register = CLITests.register
    assert_observational = CLITests.assert_observational
    """Real CLI processes across registration, hooks and restoration transitions."""

    def test_first_restore_keeps_relative_cache_partition_through_hook_and_finish(self):
        project = self.root / "resumed project"
        project.mkdir()
        transcript = write_session(self.home, SID, project)
        session = Session(SID, project.resolve(), transcript.resolve(), self.paths.codex_home)
        store.write(self.paths, "tabs.json", snapshots._encode(Snapshot(
            "old-launch", 1, [SavedTab((1, 1), session)])))
        self.environ.update(CODEX_RESTORE_CACHE_DIR="cache", TERM_PROGRAM="iTerm.app",
                            CODEX_RESTORE_ITERM_LAUNCH="restored-launch",
                            PATH=str(self.root) + os.pathsep + os.defpath)
        self.environ.pop("CODEX_RESTORE_REQUEST", None)
        # Keep the real register/owner checks; only the OS process inventory is external.
        self.tools.ps.write_text(self.tools.ps.read_text() + """
if os.environ.get("CODEX_RESTORE_TEST_SHELL_PID"):
    print(os.environ["CODEX_RESTORE_TEST_SHELL_PID"] + " Thu Oct 15 10:00:00 2026 /bin/zsh")
""")
        fzf = self.root / "fzf"
        fzf.write_text("#!" + sys.executable + "\nimport sys\nsys.stdin.read()\nprint(" + repr(SID) + ")\n")
        fzf.chmod(0o755)
        probe = self.root / "agent-probe"
        trace = self.root / "resume-observed.json"
        probe.write_text("#!" + sys.executable + "\n" +
            "import sys\nsys.path.insert(0, " + repr(str(WRAPPER.parent)) + ")\n" +
            "ROOT = " + repr(str(self.root)) + "\nWRAPPER = " + repr(str(WRAPPER)) + "\n" + """
import json, os, subprocess
from pathlib import Path
from codexlib import store
paths = store.paths(Path(ROOT) / "home", Path(ROOT) / "cache")
before = store.read(paths, "registry.json")
pending = store.read(paths, "pending.json")
event = {"hook_event_name": "Stop", "session_id": SID,
         "cwd": os.getcwd(), "transcript_path": TRANSCRIPT}
hook = subprocess.run([sys.executable, WRAPPER, "hook"], input=json.dumps(event),
                      text=True, capture_output=True)
observed = {"before": before, "pending": pending,
            "hook": [hook.returncode, hook.stdout, hook.stderr],
            "snapshot": store.read(paths, "tabs.json"),
            "cache": os.environ["CODEX_RESTORE_CACHE_DIR"], "argv": sys.argv[1:]}
(Path(ROOT) / "resume-observed.json").write_text(json.dumps(observed))
raise SystemExit(42)
""".replace("SID", repr(SID)).replace("TRANSCRIPT", repr(str(transcript.resolve()))))
        probe.chmod(0o755)
        self.environ["CODEX_RESTORE_TEST_PROBE"] = str(probe)
        source = WRAPPER.parent / "codex-resume.zsh"
        shell = ("function codex { command \"$CODEX_RESTORE_TEST_PROBE\" \"$@\"; }; "
                 "source \"$1\"; _codex_restore_no_daemon=1; zmodload zsh/system; "
                 "export CODEX_RESTORE_TEST_SHELL_PID=$sysparams[pid]; "
                 "codex resume --restore; code=$?; "
                 "print -r -- \"$code:$CODEX_RESTORE_CACHE_DIR:${CODEX_RESTORE_REQUEST-unset}\"; exit $code")
        result = subprocess.run(["zsh", "-f", "-c", shell, "test", str(source)],
                                env=self.environ, text=True, capture_output=True,
                                cwd=self.root, timeout=10)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (42, "42:cache:unset\n", ""))
        observed = json.loads(trace.read_text())
        self.assertIsNotNone(observed["before"], "first resume registered in a different cache")
        owner = observed["before"]["registrations"][0]
        self.assertEqual(owner["session"]["session_id"], SID)
        self.assertEqual(observed["pending"]["pending"][0]["status"], "acknowledged")
        self.assertEqual(observed["hook"], [0, "{}\n", ""])
        self.assertEqual(observed["snapshot"]["launch"], "restored-launch")
        self.assertGreater(observed["snapshot"]["saved_at"], 1)
        self.assertEqual(observed["snapshot"]["tabs"][0]["session"]["cwd"], str(project.resolve()))
        self.assertEqual(observed["cache"], str((self.root / "cache").resolve()))
        self.assertEqual(observed["argv"], ["--no-daemon", "resume", SID])
        self.assertFalse(store.read(self.paths, "registry.json")["registrations"][0]["active"])
        self.assertEqual(store.read(self.paths, "pending.json")["pending"], [])
        self.assertFalse((project / "cache").exists())
        self.assertEqual(sorted(path.resolve() for path in self.root.glob("**/registry.json")),
                         [self.paths.state_dir / "registry.json"])

    def test_two_sessions_survive_launch_restore_and_closed_session_is_available_again(self):
        sid2 = "22222222-2222-4222-8222-222222222222"
        term2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        target = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        cwd2 = self.root / "second project 'quoted'"
        cwd2.mkdir()
        transcript2 = write_session(self.home, sid2, cwd2)
        event2 = dict(self.event, session_id=sid2, cwd=str(cwd2), transcript_path=str(transcript2))
        self.tools.set_inventory(
            [{"id": TERM, "tab_id": "T1", "window_id": "W1"},
             {"id": term2, "tab_id": "T2", "window_id": "W1"}],
            [{"id": "T1", "index": 0, "window_id": "W1"},
             {"id": "T2", "index": 1, "window_id": "W1"}], [{"id": "W1"}])
        self.environ["CODEX_RESTORE_ITERM_LAUNCH"] = "first-launch"
        first_token = self.register()
        self.assert_observational(self.command("hook", payload=json.dumps(self.event)))
        self.environ["ITERM_SESSION_ID"] = term2
        second = self.command("register", "--terminal", term2, "--shell-pid", "100")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.environ["CODEX_RESTORE_TOKEN"] = second.stdout.strip()
        self.assert_observational(self.command("hook", payload=json.dumps(event2)))
        saved = store.read(self.paths, "tabs.json")
        self.assertEqual([entry["session"]["session_id"] for entry in saved["tabs"]], [SID, sid2])
        self.assertEqual([entry["order"] for entry in saved["tabs"]], [[1, 1], [1, 2]])
        self.assertEqual(self.command("finish", first_token).returncode, 0)
        self.assertEqual(self.command("finish", second.stdout.strip()).returncode, 0)
        self.environ["CODEX_RESTORE_ITERM_LAUNCH"] = "second-launch"
        self.environ["ITERM_SESSION_ID"] = TERM
        self.tools.set_inventory([{"id": TERM, "tab_id": "T1", "window_id": "W1"}],
                                 [{"id": "T1", "index": 0, "window_id": "W1"}], [{"id": "W1"}])
        # This terminal double creates a pane and acknowledges delivery by running
        # the real registration CLI, but delays the first prompt/hook until below.
        script = self.tools.it2.read_text()
        script = script.replace('print("Created new tab: T-new")', '''
        sessions = json.loads((root / "session-list.json").read_text())
        sessions.append({"id": "TARGET", "tab_id": "T-new", "window_id": "W1"})
        (root / "session-list.json").write_text(json.dumps(sessions))
        tabs = json.loads((root / "tab-list.json").read_text())
        tabs.append({"id": "T-new", "index": len(tabs), "window_id": "W1"})
        (root / "tab-list.json").write_text(json.dumps(tabs))
        print("Created new tab: T-new")
    elif command == "session-run":
        import shlex, subprocess
        words = shlex.split(sys.argv[3])
        request = next(word.split("=", 1)[1] for word in words if word.startswith("CODEX_RESTORE_REQUEST="))
        environment = dict(os.environ, ITERM_SESSION_ID="TARGET")
        result = subprocess.run([sys.executable, "WRAPPER", "register", "--terminal", "TARGET", "--shell-pid", "100", "--request", request], env=environment, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        (root / "restored-token").write_text(result.stdout.strip())
'''.replace("TARGET", target).replace("WRAPPER", str(WRAPPER)))
        self.tools.it2.write_text(script)
        listed = self.command("restore-list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual([row.split("\t")[1] for row in listed.stdout.splitlines()], [SID, sid2])
        result = self.command("restore-open", payload=sid2 + "\n" + SID + "\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        fields = result.stdout.split("\0")
        self.assertEqual(fields[1:], [SID, str(self.root.resolve()), str(self.paths.codex_home),
                                    str(self.paths.state_dir.parent), ""])
        calls = self.tools.calls()
        self.assertEqual(sum(call[1:3] == ["tab", "new"] for call in calls), 1)
        sent = [call for call in calls if call[1:3] == ["session", "run"]]
        self.assertEqual(len(sent), 1)
        words = shlex.split(sent[0][3])
        self.assertIn(str(cwd2.resolve()), words)
        self.assertIn("CODEX_HOME=" + str(self.paths.codex_home), words)
        self.assertEqual(words[-3:], ["codex", "resume", sid2])
        self.assertEqual(sent[0][-2:], ["-s", target.upper()])
        selection = SID + "\n" + sid2 + "\n"
        self.assertEqual(self.command("restore-open", payload=selection).stdout, "")
        first = self.command("register", "--terminal", TERM, "--shell-pid", "100", "--request", fields[0])
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.command("restore-list").stdout, "")
        self.assertEqual(self.command("restore-open", payload=selection).stdout, "")
        self.environ["CODEX_RESTORE_TOKEN"] = first.stdout.strip()
        self.assert_observational(self.command("hook", payload=json.dumps(self.event)))
        self.environ["ITERM_SESSION_ID"] = target
        self.environ["CODEX_RESTORE_TOKEN"] = (self.tools.root / "restored-token").read_text()
        self.assert_observational(self.command("hook", payload=json.dumps(event2)))
        self.assertEqual(self.command("restore-open", payload=selection).stdout, "")
        self.assertEqual(sum(call[1:3] == ["tab", "new"] for call in self.tools.calls()), 1)
        self.assertEqual(self.command("finish", first.stdout.strip()).returncode, 0)
        self.assertEqual(self.command("finish", self.environ["CODEX_RESTORE_TOKEN"]).returncode, 0)
        self.environ["CODEX_RESTORE_ITERM_LAUNCH"] = "third-launch"
        available = self.command("restore-list")
        self.assertEqual(available.returncode, 0, available.stderr)
        self.assertEqual([row.split("\t")[1] for row in available.stdout.splitlines()], [SID, sid2])

    def test_broken_cache_preserves_ordinary_codex_exit_hook_and_good_snapshot(self):
        self.register()
        self.assert_observational(self.command("hook", payload=json.dumps(self.event)))
        snapshot = (self.paths.state_dir / "tabs.json").read_bytes()
        registry_path = self.paths.state_dir / "registry.json"
        good_registry = registry_path.read_bytes()
        trace = self.root / "cache-operations.jsonl"
        fixture = self.root / "fault-cli"
        fixture.mkdir()
        instrumented = fixture / "codex-sessions"
        instrumented.write_text("#!" + sys.executable + "\n" +
            "import sys\nsys.path.insert(0, " + repr(str(WRAPPER.parent)) + ")\n" +
            "TRACE = " + repr(str(trace)) + "\n" + """
import json, os
from pathlib import Path
from codexlib import cli, store

def record(operation, result):
    with open(TRACE, "a") as stream:
        stream.write(json.dumps([operation, result]) + "\\n")

read = store.read
replace = store.os.replace

def traced_read(paths, name):
    try:
        value = read(paths, name)
    except ValueError:
        if name == "registry.json":
            record("registry-read", "failed")
        raise
    if name == "registry.json":
        record("registry-read", "succeeded")
    return value

def failing_replace(source, target):
    if Path(target).name == "registry.json":
        record("registry-replace", "failed")
        raise PermissionError("injected registry write failure")
    return replace(source, target)

store.read = traced_read
if os.environ["CODEX_RESTORE_TEST_FAULT"] == "write":
    store.os.replace = failing_replace
raise SystemExit(cli.main(sys.argv[1:]))
""")
        instrumented.chmod(0o755)
        # The actual zsh PID is carried explicitly to the ps double; therefore
        # CLI register reaches the cache rather than failing shell identity.
        recognized = self.root / "recognized-shell-pid"
        ps = self.tools.ps.read_text()
        ps += """
if os.environ.get("CODEX_RESTORE_TEST_SHELL_PID"):
    pid = os.environ["CODEX_RESTORE_TEST_SHELL_PID"]
    print(pid + " Thu Oct 15 10:00:00 2026 /bin/zsh")
    pathlib.Path(RECOGNIZED).write_text(pid)
""".replace("RECOGNIZED", repr(str(recognized)))
        self.tools.ps.write_text(ps)
        for mode in ("read", "write"):
            with self.subTest(mode=mode):
                registry_path.write_bytes(b"malformed json" if mode == "read" else good_registry)
                self.environ["CODEX_RESTORE_TEST_FAULT"] = mode
                if trace.exists():
                    trace.unlink()
                hook = self.command("hook", payload=json.dumps(self.event), executable=instrumented)
                self.assert_observational(hook)
                expected = ([["registry-read", "failed"]] if mode == "read" else
                            [["registry-read", "succeeded"], ["registry-replace", "failed"]])
                self.assertEqual([json.loads(line) for line in trace.read_text().splitlines()], expected)
                # A write fault leaves valid readable bytes, and occurs only
                # after store.write created/flushed the replacement temporary.
                if mode == "write":
                    self.assertEqual(registry_path.read_bytes(), good_registry)
                    self.assertIsInstance(store.read(self.paths, "registry.json"), dict)
                trace.unlink()
                # A previous function represents ordinary Codex; no actual agent
                # or user .zshrc is launched by this process-level test.
                source = WRAPPER.parent / "codex-resume.zsh"
                shell = ("function codex { return 42; }; source \"$1\"; "
                         "_codex_restore_root=$2; _codex_restore_no_daemon=1; "
                         "zmodload zsh/system; export CODEX_RESTORE_TEST_SHELL_PID=$sysparams[pid]; "
                         "codex harmless")
                environment = dict(self.environ, TERM_PROGRAM="iTerm.app")
                ordinary = subprocess.Popen(["zsh", "-f", "-c", shell, "test", str(source), str(fixture)],
                                            env=environment, text=True,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = ordinary.communicate(timeout=5)
                self.assertEqual(ordinary.returncode, 42, stderr)
                self.assertEqual(stdout, "")
                self.assertEqual(recognized.read_text(), str(ordinary.pid))
                self.assertEqual([json.loads(line) for line in trace.read_text().splitlines()], expected)
                self.assertIn("invalid state JSON" if mode == "read" else
                              "injected registry write failure", stderr)
                self.assertEqual((self.paths.state_dir / "tabs.json").read_bytes(), snapshot)
