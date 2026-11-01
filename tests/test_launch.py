"""One explicit creation, truthful observations and inert shell argument values."""
import importlib
import importlib.util
import json
import shlex
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from iterm2_utils.discovery import resolve_paths
from iterm2_utils.launch_checks import LaunchInspection, LaunchRequest, _identity, _metadata_command
from tests.support import Fixture

SID = '11111111-1111-4111-8111-111111111111'


class LaunchTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('iterm2_utils.launch'), 'Launch is not implemented')
        return importlib.import_module('iterm2_utils.launch')

    def fixture(self, f):
        m = self.module()
        paths = resolve_paths()
        handoff = f.home/'handoff.txt'
        handoff.write_text('PRIVATE_HANDOFF_CONTENT')
        request = LaunchRequest('window-one', 'Кодекс personal', f.home, handoff)
        identity = _identity(dict(executable=str(f.bin/'codex'), version='codex-cli 0.166.0',
            home=str(f.home), codex_home=str(paths.codex_home), zdotdir=str(f.home),
            functions={}, alias='', restore_root='', python=''))
        inspection = LaunchInspection(f.app/'Contents/Resources/utilities/it2', f.bin/'zsh', 'profile-one', identity)
        state = dict(job='codex', applied=request.profile, guid='profile-one', created_key='tab-one',
                     create_error=False, inventory_error=False, no_sessions=False, calls=[], active='window-one')

        def run(transport, argv, c_locale=False):
            state['calls'].append(argv)
            self.assertLessEqual(transport.timeout, 3)
            self.assertIsNotNone(transport.deadline)
            args = argv[1:]
            if args[:2] == ['tab', 'new']:
                state['active'] = 'window-other'
                if state['create_error']:
                    raise subprocess.TimeoutExpired(argv, 3, stderr='PRIVATE_STDERR')
                return 'Created new tab: '+state['created_key']+'\n'
            if args == ['tab', 'list', '--json']:
                return json.dumps([dict(id='tab-one', window_id=request.window_id, index=0)])
            if args == ['window', 'list', '--json']:
                return json.dumps([dict(id=request.window_id)])
            if args == ['session', 'list', '--json']:
                if state['inventory_error']:
                    return '[{"id":null}]'
                return json.dumps([] if state['no_sessions'] else [dict(id=SID, tab_id='tab-one', window_id=request.window_id)])
            if args == ['profile', 'show', request.profile, '--json']:
                return json.dumps(dict(name=request.profile, guid=state['guid'], command='codex OTHER'))
            if args[:2] == ['session', 'get-var']:
                self.assertEqual(args[3:], ['--session', SID.upper()])
                if state.get('variable_error'):
                    raise subprocess.CalledProcessError(1, argv, stderr='PRIVATE_STDERR')
                return json.dumps(state['applied'] if args[2] == 'session.profileName' else state['job'])+'\n'
            raise AssertionError('Unexpected/mutating call: '+repr(argv))

        self.addCleanup(patch.stopall)
        patch.object(m, 'inspect_launch', return_value=(inspection, [])).start()
        patch.object(m.LaunchITerm, '_run', run).start()
        # Bound polling without sleeping in tests; inherited transport keeps its real deadline.
        ticks = iter(i*.1 for i in range(10000))
        patch.object(m.time, 'monotonic', side_effect=lambda: next(ticks)).start()
        patch.object(m.time, 'sleep').start()
        return m, paths, request, inspection, state

    def test_launch_selects_exact_window_profile_and_one_process(self):
        with Fixture() as f:
            m, paths, request, inspection, state = self.fixture(f)
            code, output = m.launch(request, paths, f.runner)
            self.assertEqual((code, output['status']), (0, 'launched'))
            self.assertEqual((output['window_id'], output['tab_id'], output['session_id']), ('window-one', 'tab-one', SID))
            creates = [a for a in state['calls'] if a[1:3] == ['tab', 'new']]
            self.assertEqual(len(creates), 1)
            self.assertEqual(creates[0][3:7], ['--window', 'window-one', '--profile', request.profile])
            self.assertEqual(creates[0][7], '--command')
            command = creates[0][8]
            self.assertIn('CODEX_RESTORE_NO_AUTO=1', command)
            self.assertNotIn('--no-alt-screen', command)
            self.assertNotIn('PRIVATE_HANDOFF_CONTENT', command)
            self.assertFalse(any(a[1:3] in (['session', 'run'], ['session', 'focus'], ['session', 'close'], ['tab', 'close']) for a in state['calls']))
            self.assertEqual(output['mode'], 'launch_codex')

    def test_mutation_timeout_never_retries(self):
        with Fixture() as f:
            m, paths, request, _, state = self.fixture(f)
            state['create_error'] = True
            code, output = m.launch(request, paths, f.runner)
            self.assertEqual((code, output['status']), (3, 'unknown'))
            self.assertIsNone(output['tab_id'])
            self.assertIsNone(output['session_id'])
            self.assertEqual(sum(a[1:3] == ['tab', 'new'] for a in state['calls']), 1)

    def test_no_job_is_created_unverified(self):
        with Fixture() as f:
            m, paths, request, _, state = self.fixture(f)
            state['job'] = 'zsh'
            code, output = m.launch(request, paths, f.runner)
            self.assertEqual((code, output['status'], output['session_id']), (3, 'created_unverified', SID))
            self.assertEqual(sum(a[1:3] == ['tab', 'new'] for a in state['calls']), 1)

    def test_wrong_profile_is_not_launched(self):
        for field in ('applied', 'guid'):
            with self.subTest(field=field), Fixture() as f:
                m, paths, request, _, state = self.fixture(f)
                state[field] = 'wrong'
                code, output = m.launch(request, paths, f.runner)
                self.assertEqual((code, output['status']), (3, 'created_unverified'))
                self.assertEqual(output['session_id'], SID)
                patch.stopall()

    def test_failed_observation_preserves_ids(self):
        for failure in ('inventory_error', 'variable_error', 'no_sessions'):
            with self.subTest(failure=failure), Fixture() as f:
                m, paths, request, _, state = self.fixture(f)
                state[failure] = True
                code, output = m.launch(request, paths, f.runner)
                self.assertEqual((code, output['status']), (3, 'created_unverified'))
                self.assertEqual(output['tab_id'], 'tab-one')
                if failure == 'variable_error':
                    self.assertEqual(output['session_id'], SID)
                else:
                    self.assertIsNone(output['session_id'])
                patch.stopall()

    def test_legacy_session_key_is_never_mislabeled_as_tab_id(self):
        with Fixture() as f:
            m, paths, request, _, state = self.fixture(f)
            state.update(created_key=SID, inventory_error=True)
            code, output = m.launch(request, paths, f.runner)
            self.assertEqual((code, output['status']), (3, 'unknown'))
            self.assertIsNone(output['tab_id'])
            self.assertIsNone(output['session_id'])

    def test_legacy_session_key_resolves_to_exact_typed_ids(self):
        with Fixture() as f:
            m, paths, request, _, state = self.fixture(f)
            state['created_key'] = SID
            code, output = m.launch(request, paths, f.runner)
            self.assertEqual((code, output['status']), (0, 'launched'))
            self.assertEqual((output['tab_id'], output['session_id']), ('tab-one', SID))

    def test_subprocess_stderr_is_not_echoed(self):
        with Fixture() as f:
            m, paths, request, _, state = self.fixture(f)
            state['variable_error'] = True
            _, output = m.launch(request, paths, f.runner)
            self.assertNotIn('PRIVATE_STDERR', json.dumps(output))
            self.assertNotIn('PRIVATE_HANDOFF_CONTENT', json.dumps(output))

    def test_blocked_prerequisite_never_creates(self):
        from iterm2_utils.models import Finding
        with Fixture() as f:
            m, paths, request, _, state = self.fixture(f)
            finding = Finding('launch', 'codex', 'launch_dependency', 'unavailable', 'Unavailable.')
            m.inspect_launch.return_value = (None, [finding])
            code, output = m.launch(request, paths, f.runner)
            self.assertEqual((code, output['status']), (2, 'blocked'))
            self.assertEqual(state['calls'], [])

    def shell_fixture(self, f):
        m = self.module()
        paths = resolve_paths()
        log_code = 'import json,os,sys; open(os.environ["HOME"]+"/args.json","w").write(json.dumps(sys.argv[1:])); open(os.environ["HOME"]+"/invocations","a").write("1\\n")'
        function = 'function codex { '+shlex.join([sys.executable, '-c', log_code])+' "$@"; }\n'
        (f.bin/'codex').write_text('#!/bin/sh\nif [ "$1" = --version ]; then echo "codex-cli 0.166.0"; else echo BYPASSED >> "$HOME/bypass"; fi\n')
        (f.home/'.zshrc').write_text('export PATH='+shlex.quote(str(f.bin))+':/usr/bin:/bin\n'
            'print -r -- "$CODEX_RESTORE_NO_AUTO" >> "$HOME/startup"\n'
            'print -r -- "$PWD" > "$HOME/startup-cwd"\n'
            '[[ $CODEX_RESTORE_NO_AUTO == 1 ]] || print RESTORE > "$HOME/restore"\n'+function)
        env = dict(HOME=str(f.home), ZDOTDIR=str(f.home), PATH=str(f.bin)+':/usr/bin:/bin', CODEX_RESTORE_NO_AUTO='1')
        result = subprocess.run(['/bin/zsh', '-ilc', _metadata_command(paths)], env=env,
                                cwd=f.home, capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        identity = _identity(json.loads(result.stdout)['iterm2_launch_identity'])
        inspection = LaunchInspection(f.app/'Contents/Resources/utilities/it2', Path('/bin/zsh'), 'profile-one', identity)
        (f.home/'startup').unlink()
        return m, paths, inspection, env

    def execute_command(self, command, env):
        # iTerm parses --command into an argv; emulate exactly that boundary.
        return subprocess.run(shlex.split(command), env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=4)

    def test_login_shell_keeps_function_and_blocks_auto_restore(self):
        with Fixture() as f:
            m, paths, inspection, env = self.shell_fixture(f)
            cwd = f.home/'working directory'
            cwd.mkdir()
            handoff = f.home/'handoff.md'
            handoff.write_text('PRIVATE_HANDOFF_CONTENT')
            request = LaunchRequest('window-one', 'Codex', cwd, handoff)
            env.pop('CODEX_RESTORE_NO_AUTO')
            result = self.execute_command(m.build_command(request, inspection, paths), env)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = json.loads((f.home/'args.json').read_text())
            self.assertEqual(args[:2], ['-C', str(cwd)])
            self.assertEqual(len(args), 3)
            self.assertIn(str(handoff), args[2])
            self.assertNotIn('PRIVATE_HANDOFF_CONTENT', args[2])
            self.assertEqual((f.home/'invocations').read_text(), '1\n')
            self.assertEqual(set((f.home/'startup').read_text().splitlines()), {'1'})
            self.assertEqual((f.home/'startup-cwd').read_text().rstrip('\n'), str(cwd))
            self.assertFalse((f.home/'restore').exists())
            self.assertFalse((f.home/'bypass').exists())

    def test_changed_shell_identity_blocks_codex(self):
        for field in ('version', 'codex_home', 'home', 'executable', 'wrapper_fingerprint'):
            with self.subTest(field=field), Fixture() as f:
                m, paths, inspection, env = self.shell_fixture(f)
                old = getattr(inspection.identity, field)
                replacement = old/'other' if isinstance(old, Path) else old+'-different'
                inspection = replace(inspection, identity=replace(inspection.identity, **{field: replacement}))
                request = LaunchRequest('window-one', 'Codex', f.home, f.home/'handoff')
                self.execute_command(m.build_command(request, inspection, paths), env)
                self.assertFalse((f.home/'args.json').exists())
                self.assertEqual((f.home/'startup').read_text().splitlines(), ['1', '1'])

    def test_disappeared_cwd_keeps_shell_without_running_codex(self):
        with Fixture() as f:
            m, paths, inspection, env = self.shell_fixture(f)
            request = LaunchRequest('window-one', 'Codex', f.home/'deleted', f.home/'handoff')
            self.execute_command(m.build_command(request, inspection, paths), env)
            self.assertFalse((f.home/'args.json').exists())
            self.assertTrue((f.home/'startup').exists(), 'failed cd must leave an interactive shell')
            self.assertEqual((f.home/'startup').read_text().splitlines(), ['1'])

    def test_quoting_does_not_execute_user_values(self):
        for suffix in ('space here', 'Кириллица', "single'quote", 'double"quote', 'new\nline', '`touch SENTINEL`', '$(touch SENTINEL)'):
            with self.subTest(suffix=suffix), Fixture() as f:
                m, paths, inspection, env = self.shell_fixture(f)
                cwd = f.home/('cwd '+suffix)
                cwd.mkdir()
                handoff = f.home/('handoff '+suffix)
                handoff.write_text('PRIVATE_HANDOFF_CONTENT $(touch CONTENT_SENTINEL)')
                request = LaunchRequest('window-one', 'Codex', cwd, handoff)
                result = self.execute_command(m.build_command(request, inspection, paths), env)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = json.loads((f.home/'args.json').read_text())
                self.assertEqual(args[:2], ['-C', str(cwd)])
                self.assertEqual(len(args), 3)
                self.assertIn(str(handoff), args[2])
                self.assertNotIn('PRIVATE_HANDOFF_CONTENT', args[2])
                self.assertFalse((cwd/'SENTINEL').exists())
                self.assertFalse((f.home/'SENTINEL').exists())
                self.assertFalse((cwd/'CONTENT_SENTINEL').exists())
