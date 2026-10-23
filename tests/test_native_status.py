"""Native delivery contracts; all applications, payloads and homes are synthetic."""
import contextlib
import copy
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from runtime import events, hook
from tests.support import FakeRunner
from tests.test_runtime_events import UUID


class NativeStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = self.root/'Applications/i Term 测试.app'
        self.utilities = self.app/'Contents/Resources/utilities'
        self.utilities.mkdir(parents=True)
        for name in ('cc-status', 'it2'):
            path = self.utilities/name
            path.write_text('#!/bin/sh\nexit 0\n')
            path.chmod(0o700)
        self.settings = {'status': True, 'status_backend': 'cc-status',
                         'iterm2_app': str(self.app),
                         'native_identity_cache': str(self.root/'identity'),
                         'cache': str(self.root/'old-cache')}
        self.environment = {'HOME': str(self.root), 'ITERM_SESSION_ID': UUID}
        self.runner = FakeRunner()

    def event(self, name, **extra):
        raw = {'session_id': 's', 'hook_event_name': name, **extra}
        return events.normalize(raw, 'codex', UUID), raw

    def deliver(self, name, **extra):
        event, raw = self.event(name, **extra)
        hook.dispatch(event, self.settings, self.runner, raw_event=raw,
                      environment=self.environment)

    def test_status_only_uses_one_native_process(self):
        with patch('vendor.codex_status.status.transition', side_effect=AssertionError), \
             patch('vendor.codex_status.iterm_support.status_command', side_effect=AssertionError):
            self.deliver('Stop')
        self.assertEqual(len(self.runner.calls), 1)
        argv, timeout, stdin = self.runner.calls[0]
        self.assertEqual(argv, [str(self.utilities/'cc-status'), '--agent', 'codex'])
        self.assertEqual(json.loads(stdin)['hook_event_name'], 'Stop')
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 1.65)
        self.assertEqual(self.runner.environments[0]['TERM_SESSION_ID'], 'w0t0p0:'+UUID)
        self.assertEqual(self.runner.environments[0]['ITERM_SESSION_ID'], 'w0t0p0:'+UUID)
        self.assertNotIn('TERM_SESSION_ID', self.environment)

    def test_input_mapping_contains_no_question(self):
        from runtime import native_status
        for tool in ('request_user_input', 'request_user_input_async'):
            event, raw = self.event('PreToolUse', tool_name=tool,
                                   tool_input={'questions': ['PRIVATE']})
            self.assertEqual(native_status.prepare_payload(event, raw), {
                'hook_event_name': 'Notification', 'notification_type': 'elicitation_dialog',
                'message': 'Input needed'})
            event, raw = self.event('PostToolUse', tool_name=tool)
            self.assertEqual(native_status.prepare_payload(event, raw)['hook_event_name'], 'PostToolUse')

    def test_compact_does_not_send_session_reset(self):
        self.deliver('UserPromptSubmit', turn_id='one')
        for name, expected, extra in [('PreCompact', 'PreToolUse', {}),
                                      ('PostCompact', 'PostToolUse', {}),
                                      ('SessionStart', 'PreToolUse', {'source': 'compact'})]:
            self.deliver(name, tool_name='PRIVATE', **extra)
            self.assertEqual(json.loads(self.runner.calls[-1][2]), {'hook_event_name': expected})
        state = json.loads((self.root/'identity'/f'{UUID}.json').read_text())
        self.assertEqual(state, {'session_id': 's', 'turn_id': 'one', 'ended': False})
        self.deliver('SessionStart', source='resume')
        self.assertEqual(json.loads(self.runner.calls[-1][2])['hook_event_name'], 'SessionStart')

    def test_allowlist_does_not_mutate_input_or_forward_private_fields(self):
        from runtime import native_status
        for name in ('PermissionRequest', 'Stop', 'PreToolUse'):
            event, raw = self.event(name, tool_name='Bash', tool_input={'command': 'DETAIL'},
                                   last_assistant_message='REPLY', prompt='PRIVATE', cwd='PRIVATE',
                                   transcript_path='PRIVATE', tool_output='PRIVATE', unknown='PRIVATE',
                                   agent_id='agent', background_tasks=[{'id': 'a', 'status': 'running', 'private': 'PRIVATE'}])
            original = copy.deepcopy(raw)
            result = native_status.prepare_payload(event, raw)
            self.assertEqual(raw, original)
            self.assertNotIn('PRIVATE', json.dumps(result))
            self.assertEqual(result['background_tasks'], [{'id': 'a', 'status': 'running'}])
            self.assertEqual('tool_input' in result, name == 'PermissionRequest')
            self.assertEqual('last_assistant_message' in result, name == 'Stop')
            self.assertEqual(result['agent_id'], 'agent')

    def test_private_fields_not_persisted(self):
        for name in ('UserPromptSubmit', 'PermissionRequest', 'Stop'):
            self.deliver(name, turn_id='one', tool_name='Bash',
                         tool_input={'command': 'PRIVATE'}, last_assistant_message='PRIVATE',
                         prompt='PRIVATE', cwd='PRIVATE', transcript_path='PRIVATE')
        files = list((self.root/'identity').glob('*'))
        self.assertEqual(len(files), 2)
        for file in files:
            self.assertNotIn('PRIVATE', file.read_text())
        state = json.loads((self.root/'identity'/f'{UUID}.json').read_text())
        self.assertEqual(set(state), {'session_id', 'turn_id', 'ended'})
        self.assertEqual((self.root/'identity').stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root/'identity'/f'{UUID}.json').stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.root/'old-cache').exists())

    def test_conflicting_or_tmux_environment_never_calls_native(self):
        other = 'AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'
        for env in ({}, {'ITERM_SESSION_ID': UUID, 'TERM_SESSION_ID': other},
                    {'ITERM_SESSION_ID': UUID, 'TERM_SESSION_ID': ''},
                    {'ITERM_SESSION_ID': 'bad'}, {'ITERM_SESSION_ID': other},
                    {'ITERM_SESSION_ID': UUID, 'TMUX': '/fake/tmux'}):
            self.environment = env
            self.deliver('Stop')
        self.assertEqual(self.runner.calls, [])
        self.environment = {'TERM_SESSION_ID': UUID}
        self.deliver('Stop')
        self.assertEqual(len(self.runner.calls), 1)

    def test_late_stop_and_foreign_session_are_ignored(self):
        self.deliver('UserPromptSubmit', turn_id='one')
        self.deliver('UserPromptSubmit', turn_id='two')
        for name in ('Stop', 'Interrupt', 'PreCompact', 'PostCompact'):
            self.deliver(name, turn_id='one')
        self.deliver('SessionStart', source='compact', turn_id='one')
        self.deliver('PreToolUse', session_id='foreign')
        self.deliver('SessionStart', source='compact', session_id='foreign')
        self.assertEqual(len(self.runner.calls), 2)
        self.deliver('SessionStart', session_id='new', source='resume')
        self.deliver('UserPromptSubmit', session_id='newer', turn_id='three')
        self.assertEqual(len(self.runner.calls), 4)

    def test_session_end_blocks_tail_events(self):
        self.deliver('SessionEnd')
        for name in ('Stop', 'SubagentStop', 'PermissionRequest', 'PreToolUse'):
            self.deliver(name)
        self.deliver('SessionStart', source='compact')
        self.assertEqual(len(self.runner.calls), 1)
        self.deliver('UserPromptSubmit', turn_id='next')
        self.deliver('Stop', turn_id='next')
        self.assertEqual(len(self.runner.calls), 3)

    def test_corrupt_identity_rejects_ending_until_new_boundary(self):
        cache = self.root/'identity'
        cache.mkdir()
        for content in ('bad', '[]', '{}', '{"session_id":"s","turn_id":null,"ended":"no"}'):
            (cache/f'{UUID}.json').write_text(content)
            self.deliver('Stop')
            self.deliver('Interrupt')
            self.deliver('SessionEnd')
        self.assertEqual(self.runner.calls, [])
        self.deliver('UserPromptSubmit', turn_id='new')
        self.deliver('Stop', turn_id='new')
        self.assertEqual(len(self.runner.calls), 2)

    def test_turn_start_and_stop_are_serialized(self):
        entered, release, stop_started = threading.Event(), threading.Event(), threading.Event()
        errors = []
        invocations = []
        real_run = self.runner.run
        def blocked_run(*args, **kwargs):
            invocations.append(json.loads(kwargs['stdin'])['hook_event_name'])
            entered.set()
            if not release.wait(1):
                raise AssertionError('test release did not arrive')
            return real_run(*args, **kwargs)
        self.runner.run = blocked_run
        def deliver(name):
            try:
                if name == 'Stop': stop_started.set()
                self.deliver(name, turn_id='one')
            except BaseException as exc: errors.append(exc)
        first = threading.Thread(target=deliver, args=('UserPromptSubmit',))
        second = threading.Thread(target=deliver, args=('Stop',))
        try:
            first.start()
            self.assertTrue(entered.wait(1))
            second.start()
            self.assertTrue(stop_started.wait(1))
            time.sleep(0.05)
            self.assertEqual(self.runner.calls, [])
            self.assertEqual(invocations, ['UserPromptSubmit'])
            state = json.loads((self.root/'identity'/f'{UUID}.json').read_text())
            self.assertEqual(state['turn_id'], 'one')
        finally:
            release.set()
            first.join(2)
            if second.ident: second.join(2)
        self.assertEqual(errors, [])
        self.assertEqual([json.loads(call[2])['hook_event_name'] for call in self.runner.calls],
                         ['UserPromptSubmit', 'Stop'])

    def test_no_native_when_status_disabled(self):
        for change in ({'status': False}, {'status': True, 'status_backend': 'old'}):
            self.settings.update(change)
            self.deliver('Stop')
        self.assertEqual(self.runner.calls, [])

    def test_missing_pair_is_unavailable_and_never_falls_back(self):
        from runtime import native_status
        (self.utilities/'it2').unlink()
        event, raw = self.event('Stop')
        self.assertEqual(native_status.forward(event, raw, self.settings, self.runner,
                         environment=self.environment, deadline=time.monotonic()+2.7), 'unavailable')
        self.assertEqual(self.runner.calls, [])

    def test_native_failure_allows_independent_handlers_with_time_left(self):
        self.settings.update(notifications=True, restore=True)
        self.runner.run = unittest.mock.Mock(side_effect=OSError('unavailable'))
        with patch('runtime.notifier.handle') as notify, patch('runtime.codex_restore.registry.handle') as restore:
            self.deliver('Stop')
        notify.assert_called_once()
        restore.assert_called_once()

    def test_expired_deadline_does_not_start_handlers(self):
        event, raw = self.event('Stop')
        self.settings.update(notifications=True, restore=True)
        with patch('runtime.notifier.handle') as notify, patch('runtime.codex_restore.registry.handle') as restore:
            with self.assertRaises(hook.HookBudgetExpired):
                hook.dispatch(event, self.settings, self.runner, raw_event=raw,
                              environment=self.environment, deadline=time.monotonic()-1)
        self.assertEqual(self.runner.calls, [])
        notify.assert_not_called()
        restore.assert_not_called()

    def test_held_lock_is_bounded(self):
        from runtime import native_status
        cache = self.root/'identity'
        cache.mkdir()
        with (cache/f'{UUID}.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            event, raw = self.event('Stop')
            start = time.monotonic()
            result = native_status.forward(event, raw, self.settings, self.runner,
                     environment=self.environment, deadline=start+2.7)
        self.assertEqual(result, 'timeout')
        self.assertLess(time.monotonic()-start, 0.6)
        self.assertEqual(self.runner.calls, [])

    def test_native_mapping_keeps_notification_and_restore_event(self):
        event, raw = self.event('PreToolUse', tool_name='request_user_input')
        metadata = {'cwd': 'PRIVATE_PATH'}
        self.settings.update(notifications=True, restore=True)
        order = []
        real_run = self.runner.run
        def run(*args, **kwargs):
            order.append('native')
            return real_run(*args, **kwargs)
        self.runner.run = run
        with patch('runtime.notifier.handle', side_effect=lambda *args: order.append('notify')) as notify, \
             patch('runtime.codex_restore.registry.handle', side_effect=lambda *args: order.append('restore')) as restore:
            hook.dispatch(event, self.settings, self.runner, raw_event=raw,
                          environment=self.environment, restore_metadata=metadata)
        self.assertEqual(order, ['native', 'notify', 'restore'])
        self.assertIs(notify.call_args.args[0], event)
        self.assertIs(restore.call_args.args[0], event)
        self.assertEqual(restore.call_args.args[3], metadata)
        self.assertEqual(event.name, 'PreToolUse')
        self.assertEqual(json.loads(self.runner.calls[0][2])['hook_event_name'], 'Notification')

    def test_lock_wait_uses_phase_and_overall_remaining_budget(self):
        from runtime import native_status
        clock = [100.0]
        lock_timeouts = []
        @contextlib.contextmanager
        def lock(path, timeout):
            lock_timeouts.append(timeout)
            clock[0] += 0.3
            yield
        event, raw = self.event('Stop')
        with patch('runtime.native_status.time.monotonic', side_effect=lambda: clock[0]), \
             patch('runtime.native_status.status.locked', side_effect=lock):
            result = native_status.forward(event, raw, self.settings, self.runner,
                     environment=self.environment, deadline=101.0)
        self.assertEqual(result, 'sent')
        self.assertEqual(lock_timeouts, [0.4])
        self.assertAlmostEqual(self.runner.calls[0][1], 0.55)

    def test_native_exit_result_and_claude_exclusion(self):
        from runtime import native_status
        event, raw = self.event('Stop')
        for code, expected in ((0, 'sent'), (1, 'failed')):
            self.runner.run = unittest.mock.Mock(return_value=subprocess.CompletedProcess([], code, 'PRIVATE', 'PRIVATE'))
            self.assertEqual(native_status.forward(event, raw, self.settings, self.runner,
                             environment=self.environment, deadline=time.monotonic()+2.7), expected)
            self.assertEqual(self.runner.run.call_count, 1)
        claude = events.normalize(raw, 'claude', UUID)
        runner = FakeRunner()
        hook.dispatch(claude, self.settings, runner, raw_event=raw, environment=self.environment)
        self.assertEqual(runner.calls, [])
        for name in ('StopFailure', 'Notification', 'PostToolUseFailure'):
            event, raw = self.event(name)
            self.assertIsNone(native_status.prepare_payload(event, raw))

    def run_hook(self, payload=None, *, prefix='', timeout=4):
        settings_path = self.root/'settings.json'
        settings_path.write_text(json.dumps(self.settings))
        if prefix:
            command = [sys.executable, '-c', prefix + '\nfrom runtime.hook import main\nmain(__import__("sys").argv[1:])']
        else:
            command = [sys.executable, '-m', 'runtime.hook']
        start = time.monotonic()
        result = subprocess.run(command + ['--settings', str(settings_path)],
                                input=payload if payload is not None else json.dumps({'session_id': 's', 'hook_event_name': 'UserPromptSubmit'}),
                                env=self.environment, capture_output=True, text=True, timeout=timeout)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '{}\n', ''))
        self.assertLess(time.monotonic()-start, 3)
        return result

    def executable(self, body):
        path = self.utilities/'cc-status'
        path.write_text('#!'+sys.executable+'\n'+body+'\n')
        path.chmod(0o700)
        return path

    def test_replaced_bundle_binary_is_used(self):
        marker = self.root/'marker'
        self.executable('from pathlib import Path\nPath('+repr(str(marker))+').write_text("first")')
        self.run_hook()
        self.assertEqual(marker.read_text(), 'first')
        self.executable('from pathlib import Path\nPath('+repr(str(marker))+').write_text("second")')
        self.run_hook()
        self.assertEqual(marker.read_text(), 'second')

    def child_cleanup_case(self, *, overall=False):
        pid_path = self.root/'child.pid'
        launches = self.root/'launches'
        self.executable('import subprocess,sys,time\nfrom pathlib import Path\n'
                        'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"])\n'
                        'Path('+repr(str(pid_path))+').write_text(str(child.pid))\n'
                        'with open('+repr(str(launches))+',"a") as f: f.write("launch\\n")\n'
                        'time.sleep(30)')
        # Force the overall alarm to interrupt communicate before its phase timeout.
        prefix = ('from runtime.hook import Runner\noriginal = Runner.run\n'
                  'def run(self, argv, *, timeout, stdin=None, env=None):\n'
                  '    return original(self, argv, timeout=10, stdin=stdin, env=env)\n'
                  'Runner.run = run') if overall else ''
        pid = None
        try:
            self.run_hook(prefix=prefix)
            self.assertTrue(pid_path.exists(), 'native must actually start')
            pid = int(pid_path.read_text())
            self.assertEqual(launches.read_text().splitlines(), ['launch'])
            until = time.monotonic()+0.5
            while time.monotonic() < until and self.process_running(pid):
                time.sleep(0.01)
            self.assertFalse(self.process_running(pid), 'native child survived hook')
        finally:
            if pid is None and pid_path.exists(): pid = int(pid_path.read_text())
            if pid:
                try: os.killpg(os.getpgid(pid), signal.SIGKILL)
                except ProcessLookupError: pass
                try: os.kill(pid, signal.SIGKILL)
                except ProcessLookupError: pass
                try: os.waitpid(pid, 0)
                except ChildProcessError: pass  # Reparented grandchildren are reaped by init.

    @staticmethod
    def process_running(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        # Linux container init may defer reaping a dead orphan.
        stat = Path('/proc')/str(pid)/'stat'
        if stat.exists():
            return stat.read_text().rsplit(')', 1)[1].split()[0] != 'Z'
        return True

    def test_native_timeout_kills_child_process_group(self):
        self.child_cleanup_case()

    def test_overall_alarm_kills_child_process_group(self):
        self.child_cleanup_case(overall=True)

    def sigterm_cleanup_case(self, *, spawn=False):
        marker=self.root/'signal-pids'
        self.executable('import os,subprocess,sys,time\nfrom pathlib import Path\n'
                        'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"])\n'
                        'Path('+repr(str(marker))+').write_text(str(os.getpid())+" "+str(child.pid))\n'
                        'time.sleep(30)')
        # Hold the OS spawn return before Popen assigns self.pid. The release
        # handshake makes SIGTERM land in the actual PID-registration window.
        spawned=self.root/'spawned';release=self.root/'release-spawn';returned=self.root/'spawn-returned'
        prefix=''
        if spawn:
            prefix=('import subprocess,time\nfrom pathlib import Path\n'
                    'original=subprocess._fork_exec\n'
                    'def fork_exec(*a,**k):\n'
                    '    pid=original(*a,**k)\n'
                    '    Path('+repr(str(spawned))+').touch()\n'
                    '    until=time.monotonic()+1\n'
                    '    while not Path('+repr(str(release))+').exists() and time.monotonic()<until: time.sleep(.005)\n'
                    '    Path('+repr(str(returned))+').touch()\n'
                    '    return pid\n'
                    'subprocess._fork_exec=fork_exec\n')
        settings_path=self.root/'settings.json';settings_path.write_text(json.dumps(self.settings))
        command=[sys.executable,'-c',prefix+'from runtime.hook import main; main(__import__("sys").argv[1:])']
        proc=subprocess.Popen(command+['--settings',str(settings_path)],env=self.environment,
                              stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        start=time.monotonic();pids=[]
        try:
            proc.stdin.write(json.dumps({'session_id':'s','hook_event_name':'UserPromptSubmit'}))
            proc.stdin.close();proc.stdin=None
            until=time.monotonic()+2
            while not marker.exists() and time.monotonic()<until: time.sleep(.005)
            self.assertTrue(marker.exists(),'native and grandchild must start before SIGTERM')
            pids=list(map(int,marker.read_text().split()))
            if spawn:
                self.assertTrue(spawned.exists(),'must be inside OS spawn before PID registration')
                self.assertFalse(returned.exists(),'spawn must still be waiting for SIGTERM')
            proc.send_signal(signal.SIGTERM)
            if spawn: release.touch()
            stdout,stderr=proc.communicate(timeout=3)
            self.assertEqual((proc.returncode,stdout,stderr),(0,'{}\n',''))
            self.assertLess(time.monotonic()-start,2.7)
            until=time.monotonic()+.5
            while any(self.process_running(pid) for pid in pids) and time.monotonic()<until: time.sleep(.01)
            self.assertEqual([pid for pid in pids if self.process_running(pid)],[],'SIGTERM leaked process group')
        finally:
            if not pids and marker.exists(): pids=list(map(int,marker.read_text().split()))
            for pid in pids:
                try: os.killpg(pid,signal.SIGKILL)
                except ProcessLookupError: pass
                try: os.kill(pid,signal.SIGKILL)
                except ProcessLookupError: pass
            if proc.poll() is None: proc.kill()
            proc.communicate()

    def test_real_sigterm_cleans_native_and_grandchild(self):
        self.sigterm_cleanup_case()

    def test_real_sigterm_during_spawn_cleans_native_and_grandchild(self):
        self.sigterm_cleanup_case(spawn=True)

    def test_main_restores_sigterm_and_alarm_handlers(self):
        import io
        previous={number:signal.getsignal(number) for number in (signal.SIGTERM,signal.SIGALRM)}
        observed=[]
        def read(*args,**kwargs):
            observed.append(signal.getsignal(signal.SIGTERM) is not sentinel)
            os.kill(os.getpid(),signal.SIGTERM)
            observed.append('continued after cancellation')
        # A sentinel keeps the pre-fix process alive, so this test fails safely.
        def sentinel(*args): pass
        try:
            signal.signal(signal.SIGTERM,sentinel)
            with patch.object(Path,'read_text',read), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(hook.main(['--settings','unused']),0)
            self.assertEqual(output.getvalue(),'{}\n')
            self.assertEqual(observed,[True])
            self.assertIs(signal.getsignal(signal.SIGTERM),sentinel)
            self.assertIs(signal.getsignal(signal.SIGALRM),previous[signal.SIGALRM])
        finally:
            for number,handler in previous.items(): signal.signal(number,handler)

    def test_malformed_oversize_and_native_failures_are_silent(self):
        marker = self.root/'calls'
        self.executable('from pathlib import Path\nPath('+repr(str(marker))+').touch()')
        for payload in ('bad', '[]', 'null', '{}', json.dumps({'session_id': 's', 'hook_event_name': 'Stop', 'extra': 'x'*(2*1024*1024)})):
            self.run_hook(payload)
            self.assertFalse(marker.exists())
        for body in ('raise RuntimeError("private stderr")', 'import sys; print("private stdout"); sys.exit(1)', 'pass'):
            self.executable(body)
            self.run_hook()
        (self.utilities/'cc-status').write_text('bad executable')
        self.run_hook()

    def constructor_cancellation_case(self, *, alarm, internal=False):
        children = []
        constructor_returned = []
        method = '_execute_child' if internal else '__init__'
        original = getattr(subprocess.Popen, method)
        previous_interrupt = signal.getsignal(signal.SIGINT)
        previous_handler = signal.getsignal(signal.SIGALRM)
        def expired(*args):
            raise hook.HookBudgetExpired('inside constructor')
        def init(child, *args, **kwargs):
            original(child, *args, **kwargs)
            children.append(child)
            if alarm:
                os.kill(os.getpid(), signal.SIGALRM)
                constructor_returned.append(True)
            else:
                raise hook.HookBudgetExpired('constructor exception')
        try:
            signal.signal(signal.SIGALRM, expired)
            with patch.object(subprocess.Popen, method, init):
                with self.assertRaises(hook.HookBudgetExpired):
                    hook.Runner().run([sys.executable, '-c', 'import time; time.sleep(30)'],
                                      timeout=1, env=self.environment)
            self.assertIs(signal.getsignal(signal.SIGALRM), expired)
            self.assertIs(signal.getsignal(signal.SIGINT), previous_interrupt)
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[0].returncode, 'constructor cancellation did not kill/reap child')
            if alarm:
                self.assertEqual(constructor_returned, [True], 'alarm must defer until child registration')
        finally:
            signal.signal(signal.SIGALRM, previous_handler)
            for child in children:
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                if child.stdout.closed:
                    child.wait()
                else:
                    child.communicate()

    def test_constructor_exception_after_spawn_kills_real_child(self):
        for internal in (False, True):
            with self.subTest(internal=internal):
                self.constructor_cancellation_case(alarm=False, internal=internal)

    def test_constructor_alarm_is_deferred_until_child_registration(self):
        for internal in (False, True):
            with self.subTest(internal=internal):
                self.constructor_cancellation_case(alarm=True, internal=internal)

    def test_slow_settings_read_is_bounded(self):
        self.run_hook(prefix='import pathlib,time\npathlib.Path.read_text = lambda *a, **k: time.sleep(10)')


if __name__ == '__main__':
    unittest.main()
