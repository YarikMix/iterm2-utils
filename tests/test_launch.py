"""One explicit creation, truthful observations and inert shell argument values."""
import importlib
import fcntl
import pty
import termios
import importlib.util
import json
import os
import select
import signal
import shlex
import subprocess
import sys
import unittest
from dataclasses import replace
from itertools import product
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from iterm2_utils.discovery import resolve_paths
from iterm2_utils.launch_api import LaunchCreation
from iterm2_utils.launch_checks import LaunchInspection, LaunchRequest, _identity, _metadata_command
from tests.support import Fixture

SID = '11111111-1111-4111-8111-111111111111'


class LaunchTests(unittest.TestCase):
    def test_preflight_in_other_project_preserves_parent_appearance_and_snapshot(self):
        from iterm2_utils.commands import Runner
        from tests.test_launch_checks import LaunchChecksTests, transcript, RESUME_ID
        from tests.test_payload import APPEARANCE_SDK
        child_id = '22222222-2222-4222-8222-222222222222'
        for resume in (False, True):
            with self.subTest(resume=resume), Fixture() as f:
                checks, paths, request, _, _ = LaunchChecksTests().setup_launch(f)
                project = f.home/'other-project'; project.mkdir()
                request = replace(request, cwd=project)
                if resume:
                    request = replace(request, handoff=None, resume_session_id=RESUME_ID)
                    transcript(paths.codex_home/'sessions'/('rollout-'+RESUME_ID+'.jsonl'), project)
                config = f.home/'appearance.json'
                icon = paths.repo/'runtime/assets/appearance/ios.png'
                config.write_text(json.dumps({'projects': [dict(root=str(project), color='#123456', icon=str(icon))]}))
                (f.home/'iterm2.py').write_text(APPEARANCE_SDK)
                master, slave = pty.openpty()
                self.addCleanup(os.close, master)
                self.addCleanup(os.close, slave)
                parent_master, parent_slave = pty.openpty()
                self.addCleanup(os.close, parent_master)
                self.addCleanup(os.close, parent_slave)
                parent = dict(tty=os.ttyname(parent_slave), profile={'color': 'parent', 'icon': 'manual'}, snapshot='saved parent')
                initial = {SID: parent, child_id: dict(tty=os.ttyname(slave), profile={}, snapshot='child saved')}
                state_path = f.home/'sdk-state.json'
                state_path.write_text(json.dumps(initial))
                mutations = f.home/'sdk-mutations.jsonl'
                (f.bin/'zsh').unlink(); (f.bin/'zsh').symlink_to('/bin/zsh')
                (f.bin/'codex').write_text('#!'+sys.executable+'\n'+'''import json, os, pathlib, sys
if sys.argv[1:] == ['--version']:
    print('codex-cli 0.166.0')
else:
    assert sys.argv[1:] == ['app-server', '--stdio'], sys.argv
    initialize = json.loads(input()); assert initialize['method'] == 'initialize'
    print(json.dumps({'id': initialize['id'], 'result': {'userAgent': 'codex/0.166.0'}}), flush=True)
    assert json.loads(input())['method'] == 'initialized'
    request = json.loads(input()); assert request['method'] == 'config/read'
    pathlib.Path(os.environ['HOME']+'/protocol.json').write_text(json.dumps(
        dict(cwd=request['params']['cwd'], ids=[os.environ.get(key) for key in ('ITERM_SESSION_ID','TERM_SESSION_ID')])))
    print(json.dumps({'id': request['id'], 'result': {'config': {'tui': {'copy_on_select': 'never'}}}}), flush=True)
    sys.stdin.read()
''')
                (f.home/'.zshrc').write_text(
                    'export PATH='+shlex.quote(str(f.bin))+':/usr/bin:/bin\n'
                    'source '+shlex.quote(str(paths.repo/'runtime/appearance.zsh'))+'\n')
                os.environ.update(ZDOTDIR=str(f.home), TERM_PROGRAM='iTerm.app',
                                  ITERM_SESSION_ID='w0t0p0:'+SID, TERM_SESSION_ID=SID,
                                  ITERM2_UTILS_PYTHON=sys.executable, ITERM2_UTILS_APPEARANCE_CONFIG=str(config),
                                  PYTHONPATH=str(f.home))
                before = dict(os.environ)
                f.runner.codex_config = Runner().codex_config
                inspection, findings = checks.inspect_launch(paths, request, f.runner)
                self.assertEqual(findings, [])
                self.assertIsNotNone(inspection)
                self.assertEqual(dict(os.environ), before)
                self.assertEqual(json.loads((f.home/'protocol.json').read_text()), dict(cwd=str(project), ids=[None, None]))
                self.assertEqual(json.loads(state_path.read_text()), initial)
                self.assertFalse(mutations.exists(), 'preflight must not even invalidate a snapshot')
                def own_terminal():
                    os.setsid()
                    fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
                child_env = dict(before, ITERM_SESSION_ID='w0t1p0:'+child_id, TERM_SESSION_ID=child_id)
                with subprocess.Popen(['/bin/zsh', '-ilc', 'true'], env=child_env, cwd=project,
                                      stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      preexec_fn=own_terminal, text=True) as child:
                    try:
                        stdout, stderr = child.communicate(timeout=7)
                    except subprocess.TimeoutExpired as exc:
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        child.wait(timeout=2)
                        self.fail('child login shell timed out after 7 seconds; '
                                  f'stdout tail={(exc.stdout or b"")[-4096:]!r}; '
                                  f'stderr tail={(exc.stderr or b"")[-4096:]!r}')
                self.assertEqual((child.returncode, stdout, stderr), (0, '', ''))
                final = json.loads(state_path.read_text())
                self.assertEqual(final[SID], parent)
                self.assertEqual(final[child_id]['profile']['tab_color'], [18, 52, 86])
                self.assertEqual(final[child_id]['profile']['custom_icon_path'], str(icon))
                self.assertIsNone(final[child_id]['snapshot'])
                records = [json.loads(line) for line in mutations.read_text().splitlines()]
                self.assertEqual([(sid, kind) for sid, kind, _ in records],
                                 [(child_id, 'snapshot'), (child_id, 'profile')])

    def test_resume_arguments_are_exact_and_normalized(self):
        with Fixture() as f:
            m, paths, request, inspection, state = self.fixture(f)
            sid = 'abcdefab-1234-4123-8123-abcdefabcdef'
            request = replace(request, handoff=None, resume_session_id=sid.upper())
            self.assertEqual(m._codex_arguments(request), ['resume', sid, '-C', str(f.home)])
            with patch.object(m, 'inspect_launch', return_value=(None, [])):
                code, output = m.launch(request, paths, f.runner)
            self.assertEqual(code, 2)
            self.assertEqual(output['launch_mode'], 'resume')
            self.assertEqual(output['resume_session_id'], sid)
            state['command_line'] = 'codex resume '+sid+' -C '+str(f.home)
            code, output = m.launch(request, paths, f.runner)
            self.assertEqual(code, 0, output)
            self.assertEqual(output['launch_mode'], 'resume')
            self.assertEqual(output['resume_session_id'], sid)

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
        state = dict(title='codex', command_line='codex -C '+str(request.cwd)+
                     ' Read the handoff file at '+str(request.handoff)+' and carry out the task described there.',
                     job='codex', applied=request.profile, guid='profile-one', sdk_calls=[],
                     now=0., create_seconds=0., creation=None, observed_window=request.window_id,
                     observed_tab='tab-one', observed_session=SID, extra_session=False,
                     create_error=False, inventory_error=False, no_sessions=False, calls=[], active='window-one')

        def run(transport, argv, c_locale=False):
            state['calls'].append(argv)
            self.assertLessEqual(transport.timeout, 3)
            self.assertIsNotNone(transport.deadline)
            args = argv[1:]
            if args == ['tab', 'list', '--json']:
                return json.dumps([dict(id=state['observed_tab'], window_id=state['observed_window'], index=0)])
            if args == ['window', 'list', '--json']:
                return json.dumps([dict(id=state['observed_window'])])
            if args == ['session', 'list', '--json']:
                if state['inventory_error']:
                    return '[{"id":null}]'
                sessions = [dict(id=state['observed_session'], tab_id=state['observed_tab'],
                                 window_id=state['observed_window'])]
                if state['extra_session']:
                    sessions.append(dict(sessions[0], id='22222222-2222-4222-8222-222222222222'))
                return json.dumps([] if state['no_sessions'] else sessions)
            if args == ['profile', 'show', request.profile, '--json']:
                return json.dumps(dict(name=state.get('profile_name', request.profile), guid=state['guid'], command='codex OTHER'))
            if args[:2] == ['session', 'get-var']:
                self.assertEqual(args[3:], ['--session', state['observed_session'].upper()])
                if state.get('variable_error'):
                    raise subprocess.CalledProcessError(1, argv, stderr='PRIVATE_STDERR')
                return json.dumps(state[{'session.profileName': 'applied', 'session.jobName': 'job',
                    'session.processTitle': 'title', 'session.commandLine': 'command_line'}[args[2]]])+'\n'
            raise AssertionError('Unexpected/mutating call: '+repr(argv))

        self.addCleanup(patch.stopall)
        patch.object(m, 'inspect_launch', return_value=(inspection, [])).start()
        patch.object(m.LaunchITerm, '_run', run).start()
        async def create(window, profile, guid, command):
            state['sdk_calls'].append((window, profile, guid, command))
            state['active'] = 'window-other'
            deadline = state['now']+30
            state['now'] += state['create_seconds']
            if state['creation'] is not None:
                return state['creation']
            if state['create_error']:
                return LaunchCreation('unknown', window, None, None, deadline, ())
            return LaunchCreation('created_unverified', window, 'tab-one', SID, deadline, ())

        patch.object(m, 'create_tab', create, create=True).start()
        patch.object(m.time, 'monotonic', side_effect=lambda: state['now']).start()
        patch.object(m.time, 'sleep', side_effect=lambda seconds: state.update(now=state['now']+seconds)).start()
        return m, paths, request, inspection, state

    def test_launch_selects_exact_window_profile_and_one_process(self):
        with Fixture() as f:
            m, paths, request, inspection, state = self.fixture(f)
            code, output = m.launch(request, paths, f.runner)
            self.assertEqual(output['launch_mode'], 'handoff')
            self.assertIsNone(output['resume_session_id'])
            self.assertEqual((code, output['status']), (0, 'launched'))
            self.assertEqual((output['window_id'], output['tab_id'], output['session_id']), ('window-one', 'tab-one', SID))
            creates = state['sdk_calls']
            self.assertEqual(len(creates), 1)
            self.assertEqual(creates[0][:3], ('window-one', request.profile, inspection.profile_guid))
            command = creates[0][3]
            self.assertIn('CODEX_RESTORE_NO_AUTO=1', command)
            self.assertNotIn('--no-alt-screen', command)
            self.assertNotIn('PRIVATE_HANDOFF_CONTENT', command)
            self.assertFalse(any(a[1:3] in (['session', 'run'], ['session', 'focus'], ['session', 'close'], ['tab', 'close']) for a in state['calls']))
            self.assertEqual(output['mode'], 'launch_codex')

    def test_launch_ignores_restore_transport_override(self):
        from runtime.codex_restore.codexlib.iterm import IT2_DEFAULT
        with Fixture() as f:
            m, paths, request, inspection, state = self.fixture(f)
            inspection = replace(inspection, it2=Path(IT2_DEFAULT))
            m.inspect_launch.return_value = (inspection, [])
            with patch.dict('os.environ', {'CODEX_RESTORE_IT2': str(f.home/'unverified-it2')}):
                code, output = m.launch(request, paths, f.runner)
            self.assertEqual((code, output['status']), (0, 'launched'))
            self.assertTrue(state['calls'])
            self.assertTrue(all(argv[0] == IT2_DEFAULT for argv in state['calls']))
            self.assertEqual(len(state['sdk_calls']), 1)

    def test_mutation_timeout_never_retries(self):
        with Fixture() as f:
            m, paths, request, _, state = self.fixture(f)
            state['create_error'] = True
            code, output = m.launch(request, paths, f.runner)
            self.assertEqual((code, output['status']), (3, 'unknown'))
            self.assertIsNone(output['tab_id'])
            self.assertIsNone(output['session_id'])
            self.assertEqual(len(state['sdk_calls']), 1)

    def test_no_job_is_created_unverified(self):
        with Fixture() as f:
            m, paths, request, _, state = self.fixture(f)
            state['job'] = 'zsh'
            code, output = m.launch(request, paths, f.runner)
            self.assertEqual((code, output['status'], output['session_id']), (3, 'created_unverified', SID))
            self.assertEqual(len(state['sdk_calls']), 1)

    def test_helper_or_incomplete_command_line_is_not_launched(self):
        for command_line in ('codex --version', 'codex --help', '', 'codex app-server --stdio',
                             'codex -C /other Read the handoff file at /other', 'codex -C'):
            with self.subTest(command_line=command_line), Fixture() as f:
                m, paths, request, _, state = self.fixture(f)
                state['command_line'] = command_line
                code, output = m.launch(request, paths, f.runner)
                self.assertEqual((code, output['status']), (3, 'created_unverified'))
                self.assertEqual(len(state['sdk_calls']), 1)
                patch.stopall()

    def test_missing_or_malformed_process_evidence_is_unverified(self):
        for field in ('title', 'command_line'):
            for value in ('', None, {}, 123):
                with self.subTest(field=field, value=value), Fixture() as f:
                    m, paths, request, _, state = self.fixture(f)
                    state[field] = value
                    code, output = m.launch(request, paths, f.runner)
                    self.assertEqual((code, output['status']), (3, 'created_unverified'))
                    patch.stopall()

    def test_observation_preserves_literal_argument_values(self):
        with Fixture() as f:
            m, paths, request, _, state = self.fixture(f)
            request = replace(request, cwd=f.home/'space \" quote\nКириллица',
                              handoff=f.home/"handoff ' $(literal)")
            state['title'] = '/package path/vendor/codex'
            state['command_line'] = state['title']+' --no-daemon -C '+str(request.cwd)+' Read the handoff file at '+str(request.handoff)+' and carry out the task described there.'
            code, output = m.launch(request, paths, f.runner)
            self.assertEqual((code, output['status']), (0, 'launched'))
            self.assertNotIn(state['command_line'], json.dumps(output))

    def test_live_double_quoted_handoff_prompt_is_launched(self):
        with Fixture() as f:
            m, paths, request, _, state = self.fixture(f)
            state['command_line'] = ('codex --no-daemon -C '+str(request.cwd)+
                ' "Read the handoff file at '+str(request.handoff)+' and carry out the task described there."')
            code, output = m.launch(request, paths, f.runner)
            self.assertEqual((code, output['status']), (0, 'launched'))
            self.assertNotIn(state['command_line'], json.dumps(output))

    def test_quoted_command_line_preserves_exact_argv_values_and_wrapper_limit(self):
        for resume, count in product((False, True), range(4)):
            with self.subTest(resume=resume, count=count), Fixture() as f:
                m, paths, request, _, state = self.fixture(f)
                sentinel = f.home/'SENTINEL'
                cwd = f.home/('space "quote" \nКириллица $(touch '+str(sentinel)+')')
                handoff = f.home/("handoff 'quote' `touch "+str(sentinel)+'`')
                request = replace(request, cwd=cwd, handoff=None if resume else handoff,
                                  resume_session_id=SID if resume else None)
                mode_argv = (['resume', SID, '-C', str(cwd)] if resume else
                    ['-C', str(cwd), 'Read the handoff file at '+str(handoff)+' and carry out the task described there.'])
                state['title'] = '/package path/vendor/codex'
                state['command_line'] = shlex.join([state['title'], *(['--no-daemon']*count), *mode_argv])
                code, output = m.launch(request, paths, f.runner)
                self.assertEqual(code, 0 if count <= 2 else 3, output)
                self.assertFalse(sentinel.exists())
                patch.stopall()

    def test_quoted_command_line_rejects_wrong_or_malformed_argv(self):
        for resume, mutation in product((False, True),
                ('malformed', 'helper', 'cwd', 'mode-value', 'extra', 'misplaced-flag')):
            with self.subTest(resume=resume, mutation=mutation), Fixture() as f:
                m, paths, request, _, state = self.fixture(f)
                if resume:
                    request = replace(request, handoff=None, resume_session_id=SID)
                    argv = ['codex', 'resume', SID, '-C', str(request.cwd)]
                else:
                    argv = ['codex', '-C', str(request.cwd),
                            'Read the handoff file at '+str(request.handoff)+' and carry out the task described there.']
                if mutation == 'helper':
                    argv = ['codex', '--help']
                elif mutation == 'cwd':
                    argv[argv.index('-C')+1] = '/other project'
                elif mutation == 'mode-value':
                    argv[2 if resume else 3] = ('22222222-2222-4222-8222-222222222222' if resume else 'Other prompt')
                elif mutation == 'extra':
                    argv.append('extra prompt')
                elif mutation == 'misplaced-flag':
                    argv.append('--no-daemon')
                # Force a quoted representation even when every value could be written bare.
                state['command_line'] = ' '.join("'"+value+"'" for value in argv)
                if mutation == 'malformed':
                    state['command_line'] += ' "unterminated'
                code, output = m.launch(request, paths, f.runner)
                self.assertEqual((code, output['status']), (3, 'created_unverified'))
                self.assertEqual(output['session_id'], SID)
                patch.stopall()

    def test_delayed_helpers_guard_refusal_and_actual_tui(self):
        # Pipes hold each real fake invocation at an exact phase; no timing is launch evidence.
        chains = ('direct', 'passthrough', 'simple', 'dispatcher', 'restore',
                  'restore-passthrough', 'restore-simple', 'restore-dispatcher')
        for chain, resume in product(chains, (False, True)):
            for phase in ('version-refused', 'tui', *(['help'] if chain.startswith('restore') else [])):
                with self.subTest(chain=chain, phase=phase, resume=resume), Fixture() as f:
                    m, paths, request, inspection, state = self.fixture(f)
                    if resume:
                        request = replace(request, handoff=None, resume_session_id=SID)
                    fake = '''import json, os, sys
if os.environ.get('LAUNCH_TEST_OBSERVE'):
    os.write(int(os.environ['LAUNCH_TEST_OBSERVE']), (json.dumps(sys.argv)+'\\n').encode())
    os.read(int(os.environ['LAUNCH_TEST_GATE']), 1)
if sys.argv[1:] == ['--version']:
    print('codex-cli 0.166.0')
elif sys.argv[1:] == ['--help']:
    print('--no-daemon')
else:
    open(os.environ['HOME']+'/tui-ran', 'w').write('yes')
'''
                    (f.bin/'codex').write_text('#!'+sys.executable+'\n'+fake)
                    startup = 'export PATH='+shlex.quote(str(f.bin))+':/usr/bin:/bin\n'
                    if 'passthrough' in chain:
                        startup += 'function codex { command codex "$@" }\n'
                    if 'simple' in chain:
                        startup += 'function codex { command codex --no-daemon "$@" }\n'
                    if 'dispatcher' in chain:
                        startup += 'source '+shlex.quote(str(paths.repo/'runtime/codex.zsh'))+'\n'
                    if chain.startswith('restore'):
                        startup += 'source '+shlex.quote(str(paths.repo/'runtime/codex_restore/codex-resume.zsh'))+'\n'
                    (f.home/'.zshrc').write_text(startup)
                    env = dict(HOME=str(f.home), ZDOTDIR=str(f.home), PATH=str(f.bin)+':/usr/bin:/bin',
                               CODEX_RESTORE_NO_AUTO='1', ITERM2_UTILS_CODEX_NO_DAEMON='1')
                    raw = subprocess.run(['/bin/zsh', '-ilc', _metadata_command(paths)], env=env,
                                         capture_output=True, text=True, timeout=3, cwd=f.home)
                    self.assertEqual(raw.returncode, 0, raw.stderr)
                    identity = _identity(json.loads(raw.stdout)['iterm2_launch_identity'])
                    if phase == 'version-refused':
                        identity = replace(identity, home=f.home/'different')
                    inspection = replace(inspection, zsh=Path('/bin/zsh'), identity=identity)
                    m.inspect_launch.return_value = (inspection, [])
                    observe_read, observe_write = os.pipe()
                    gate_read, gate_write = os.pipe()
                    env.update(LAUNCH_TEST_OBSERVE=str(observe_write), LAUNCH_TEST_GATE=str(gate_read))
                    process = subprocess.Popen(shlex.split(m.build_command(request, inspection, paths)),
                        env=env, cwd=f.home, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, start_new_session=True, pass_fds=(observe_write, gate_read))
                    os.close(observe_write)
                    os.close(gate_read)
                    try:
                        stages = ['--version']
                        if phase != 'version-refused' and chain.startswith('restore'):
                            stages.append('--help')
                        if phase == 'tui':
                            stages.append('tui')
                        for index, stage in enumerate(stages):
                            self.assertTrue(select.select([observe_read], [], [], 4)[0], 'fake invocation timed out')
                            argv = json.loads(os.read(observe_read, 16384))
                            if stage == 'tui':
                                count = 2 if chain == 'restore-simple' else int(chain not in ('direct', 'passthrough'))
                                expected = (['resume', SID, '-C', str(request.cwd)] if resume else
                                    ['-C', str(request.cwd), 'Read the handoff file at '+str(request.handoff)+' and carry out the task described there.'])
                                self.assertEqual(argv[1:], ['--no-daemon']*count+expected)
                            else:
                                self.assertEqual(argv[1:], [stage])
                            if index == len(stages)-1:
                                state.update(title=argv[0], command_line=' '.join(argv))
                                code, output = m.launch(request, paths, f.runner)
                                wanted = (0, 'launched') if phase == 'tui' else (3, 'created_unverified')
                                self.assertEqual((code, output['status']), wanted)
                                self.assertEqual(len(state['sdk_calls']), 1)
                            os.write(gate_write, b'x')
                        if phase == 'version-refused':
                            self.assertEqual(process.wait(timeout=4), 0)
                            self.assertFalse((f.home/'tui-ran').exists())
                        elif phase == 'tui':
                            self.assertEqual(process.wait(timeout=4), 0)
                            self.assertTrue((f.home/'tui-ran').exists())
                    finally:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=4)
                        os.close(observe_read)
                        os.close(gate_write)
                    patch.stopall()

    def test_wrong_profile_is_not_launched(self):
        for field in ('applied', 'guid', 'profile_name'):
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
                self.assertEqual(output['session_id'], SID)
                patch.stopall()

    def test_launch_never_uses_legacy_creation(self):
        for resume in (False, True):
            with self.subTest(resume=resume), Fixture() as f:
                m, paths, request, _, state = self.fixture(f)
                if resume:
                    request = replace(request, handoff=None, resume_session_id=SID)
                    state['command_line'] = 'codex resume '+SID+' -C '+str(f.home)
                code, output = m.launch(request, paths, f.runner)
                self.assertEqual(code, 0, output)
                self.assertEqual(len(state['sdk_calls']), 1)
                it2_mutations = [a for a in state['calls'] if a[1:3] not in
                    (['session', 'list'], ['tab', 'list'], ['window', 'list'],
                     ['profile', 'show'], ['session', 'get-var'])]
                self.assertEqual(it2_mutations, [])
                patch.stopall()

    def test_creation_and_verification_share_deadline(self):
        for used in (29.5, 30.):
            with self.subTest(used=used), Fixture() as f:
                m, paths, request, _, state = self.fixture(f)
                state.update(create_seconds=used, job='zsh')
                code, output = m.launch(request, paths, f.runner)
                self.assertEqual((code, output['status']), (3, 'created_unverified'))
                self.assertLessEqual(state['now'], 30.)
                self.assertEqual(output['session_id'], SID)
                self.assertEqual(bool(state['calls']), used < 30)
                patch.stopall()

    def test_observation_subprocesses_receive_only_remaining_budget(self):
        m = self.module()
        real_run = m.LaunchITerm._run
        with Fixture() as f:
            m, paths, request, _, state = self.fixture(f)
            fake_observe = m.LaunchITerm._run
            state['create_seconds'] = 28.75
            budgets = []

            def popen(argv, **kwargs):
                stdout = fake_observe(SimpleNamespace(timeout=3, deadline=30), argv)
                def communicate(timeout):
                    self.assertAlmostEqual(timeout, 30-state['now'])
                    budgets.append(timeout)
                    state['now'] += min(.2, timeout)
                    return stdout, ''
                return SimpleNamespace(communicate=communicate, returncode=0)

            with patch.object(m.LaunchITerm, '_run', real_run), patch.object(m.subprocess, 'Popen', popen):
                code, output = m.launch(request, paths, f.runner)
            self.assertEqual((code, output['status']), (3, 'created_unverified'))
            self.assertEqual(output['session_id'], SID)
            self.assertTrue(budgets)
            self.assertLessEqual(max(budgets), 1.25)
            self.assertEqual(state['now'], 30)

    def test_sdk_session_uuid_is_normalized_for_comparison_and_it2(self):
        with Fixture() as f:
            m, paths, request, _, state = self.fixture(f)
            terminal = 'abcdefab-1111-4111-8111-111111111111'
            state['creation'] = LaunchCreation('created_unverified', request.window_id,
                                               'tab-one', terminal.upper(), 30., ())
            state['observed_session'] = terminal.upper()
            code, output = m.launch(request, paths, f.runner)
            self.assertEqual(code, 0, output)
            self.assertEqual(output['session_id'], terminal)
            variables = [argv for argv in state['calls'] if argv[1:3] == ['session', 'get-var']]
            self.assertEqual(len(variables), 4)
            self.assertTrue(all(argv[-2:] == ['--session', terminal.upper()] for argv in variables))

    def test_sdk_partial_and_blocked_results_preserve_known_ids(self):
        for status, tab, session, wanted in (
                ('blocked', None, None, (2, 'blocked')),
                ('unknown', None, None, (3, 'unknown')),
                ('unknown', 'tab-one', None, (3, 'created_unverified')),
                ('unknown', 'tab-one', 'malformed', (3, 'created_unverified')),
                ('unknown', 'tab-one', SID, (0, 'launched'))):
            with self.subTest(status=status, tab=tab, session=session), Fixture() as f:
                m, paths, request, _, state = self.fixture(f)
                state['creation'] = LaunchCreation(status, 'window-one' if status != 'blocked' else None,
                                                   tab, session, 30., ())
                code, output = m.launch(request, paths, f.runner)
                self.assertEqual((code, output['status']), wanted)
                self.assertEqual((output['tab_id'], output['session_id']), (tab, session))
                self.assertEqual(len(state['sdk_calls']), 1)
                patch.stopall()

    def test_exact_sdk_identity_and_single_session_are_required(self):
        for field, value in (('observed_window', 'other'), ('observed_tab', 'other'),
                             ('observed_session', '22222222-2222-4222-8222-222222222222'),
                             ('extra_session', True), ('profile_name', 'other')):
            with self.subTest(field=field), Fixture() as f:
                m, paths, request, _, state = self.fixture(f)
                state[field] = value
                code, output = m.launch(request, paths, f.runner)
                self.assertEqual((code, output['status']), (3, 'created_unverified'))
                self.assertEqual((output['tab_id'], output['session_id']), ('tab-one', SID))
                patch.stopall()

    def test_resume_requires_exact_argv(self):
        for resume in (False, True):
            for count in (0, 1, 2, 3):
                with self.subTest(resume=resume, count=count), Fixture() as f:
                    m, paths, request, _, state = self.fixture(f)
                    if resume:
                        request = replace(request, handoff=None, resume_session_id=SID)
                        args = 'resume '+SID+' -C '+str(request.cwd)
                    else:
                        args = state['command_line'][len('codex '):]
                    state['command_line'] = 'codex '+('--no-daemon '*count)+args
                    code, output = m.launch(request, paths, f.runner)
                    self.assertEqual(code, 0 if count <= 2 else 3, output)
                    patch.stopall()
        for command in ('codex', 'codex --help', 'codex --version', 'codex app-server --stdio',
                        'codex resume OTHER -C CWD', 'codex resume SID -C /other',
                        'codex resume SID -C CWD extra prompt', 'codex resume SID --no-daemon -C CWD',
                        'codex resume SID -C CWD --no-daemon'):
            with self.subTest(command=command), Fixture() as f:
                m, paths, request, _, state = self.fixture(f)
                request = replace(request, handoff=None, resume_session_id=SID)
                state['command_line'] = command.replace('SID', SID).replace('CWD', str(request.cwd))
                self.assertEqual(m.launch(request, paths, f.runner)[0], 3)
                patch.stopall()

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
            self.assertEqual(state['sdk_calls'], [])

    def shell_fixture(self, f):
        m = self.module()
        paths = resolve_paths()
        log_code = 'import json,os,sys; open(os.environ["HOME"]+"/args.json","w").write(json.dumps(sys.argv[1:])); open(os.environ["HOME"]+"/invocations","a").write("1\\n"); open(os.environ["HOME"]+"/restore-auto","w").write(os.environ.get("CODEX_RESTORE_NO_AUTO", ""))'
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
        fields = ('version', 'codex_home', 'home', 'executable', 'wrapper_fingerprint')
        for field, resume in product(fields, (False, True)):
            with self.subTest(field=field, resume=resume), Fixture() as f:
                m, paths, inspection, env = self.shell_fixture(f)
                old = getattr(inspection.identity, field)
                replacement = old/'other' if isinstance(old, Path) else old+'-different'
                inspection = replace(inspection, identity=replace(inspection.identity, **{field: replacement}))
                request = LaunchRequest('window-one', 'Codex', f.home, f.home/'handoff')
                if resume:
                    request = replace(request, handoff=None, resume_session_id=SID)
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
        suffixes = ('space here', 'Кириллица', "single'quote", 'double"quote', 'new\nline',
                    '`touch SENTINEL`', '$(touch SENTINEL)')
        for suffix, resume in product(suffixes, (False, True)):
            with self.subTest(suffix=suffix, resume=resume), Fixture() as f:
                m, paths, inspection, env = self.shell_fixture(f)
                cwd = f.home/('cwd '+suffix)
                cwd.mkdir()
                handoff = f.home/('handoff '+suffix)
                handoff.write_text('PRIVATE_HANDOFF_CONTENT $(touch CONTENT_SENTINEL)')
                request = LaunchRequest('window-one', 'Codex', cwd, handoff)
                if resume:
                    request = replace(request, handoff=None, resume_session_id=SID.upper())
                env.pop('CODEX_RESTORE_NO_AUTO')
                result = self.execute_command(m.build_command(request, inspection, paths), env)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = json.loads((f.home/'args.json').read_text())
                expected = (['resume', SID, '-C', str(cwd)] if resume else
                    ['-C', str(cwd), 'Read the handoff file at '+str(handoff)+' and carry out the task described there.'])
                self.assertEqual(args, expected)
                self.assertEqual((f.home/'restore-auto').read_text(), '1')
                self.assertFalse((cwd/'SENTINEL').exists())
                self.assertFalse((f.home/'SENTINEL').exists())
                self.assertFalse((cwd/'CONTENT_SENTINEL').exists())
