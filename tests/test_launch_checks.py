"""Launch preflight rejects unknown state before any tab creation."""
import importlib
import importlib.util
import json
import os
import plistlib
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from iterm2_utils.commands import Runner
from iterm2_utils.discovery import resolve_paths
from tests.support import Fixture


def profile():
    keys = {}
    for char in ('0x63', '0x441'):
        keys[char+'-0x40000-0x8-0x1'] = {'Action': 11, 'Text': '0x03'}
        keys[char+'-0x100000-0x8-0x1'] = {'Action': 11, 'Text': '0x1b 0x5b 0x39 0x39 0x3b 0x39 0x75'}
    return {'Name': 'Кодекс personal', 'Guid': 'profile-one', 'Keyboard Map': keys}


class LaunchChecksTests(unittest.TestCase):
    def checks(self):
        self.assertIsNotNone(importlib.util.find_spec('iterm2_utils.launch_checks'),
                             'Launch preflight has not been implemented')
        return importlib.import_module('iterm2_utils.launch_checks')

    def setup_launch(self, f):
        module = self.checks()
        paths = resolve_paths()
        handoff = f.home/'поручение.txt'
        handoff.write_text('PRIVATE_HANDOFF')
        request = module.LaunchRequest('window-one', 'Кодекс personal', f.home, handoff)
        state = {'profile': profile(), 'live': [{'guid': 'profile-one', 'name': request.profile}],
                 'config': {'tui': {'copy_on_select': 'never'}}, 'copy': False,
                 'windows': [{'id': 'window-one'}], 'version': '0.166.0'}
        bodies = {'direct': 'command codex "$@"', 'simple': 'command codex --no-daemon "$@"',
                  'dispatcher': 'fixture shipped dispatcher', '_iterm2_utils_classify': 'fixture classifier',
                  'restore': 'fixture restore', '_codex_restore_call': 'fixture call',
                  '_codex_restore_classify': 'fixture restore classifier',
                  '_codex_restore_previous_call': 'fixture previous', '_codex_restore_sessions': 'fixture sessions'}
        state['identity'] = {'executable': str(f.bin/'codex'), 'version': 'codex-cli 0.166.0',
                             'home': str(f.home), 'codex_home': str(paths.codex_home),
                             'zdotdir': str(paths.zshrc.parent), 'functions': {},
                             'alias': '', 'restore_root': '', 'python': ''}
        original = f.runner.run

        def run(argv, **kwargs):
            original(argv, **kwargs)
            args = argv[1:]
            if Path(argv[0]).name == 'zsh':
                return subprocess.CompletedProcess(argv, 0, json.dumps(bodies), '')
            if Path(argv[0]).name == 'it2':
                if args == ['--help']:
                    out = 'window profile tab'
                elif args == ['tab', 'new', '--help']:
                    out = '--window --profile --command'
                elif args == ['window', 'list', '--json']:
                    out = json.dumps(state['windows'])
                elif args == ['profile', 'list', '--json']:
                    out = json.dumps(state['live'])
                else:
                    raise AssertionError('Unexpected or mutating it2 invocation: '+repr(args))
                return subprocess.CompletedProcess(argv, 0, out, '')
            if Path(argv[0]).name == 'defaults':
                data = {'CopySelection': state['copy'], 'New Bookmarks': state.get('raw', [state['profile']]), 'PRIVATE': 'SECRET'}
                return subprocess.CompletedProcess(argv, 0, plistlib.dumps(data).decode(), '')
            return subprocess.CompletedProcess(argv, 0, state['version'], '')

        def codex_config(argv, *, timeout, env, cwd, check_identity):
            f.runner.calls.append((argv, timeout, None))
            f.runner.environments.append(env)
            self.assertEqual(cwd, request.cwd)
            self.assertEqual(env['CODEX_RESTORE_NO_AUTO'], '1')
            identity = check_identity(state['identity'])
            return identity, state['config']

        f.runner.run = run
        f.runner.codex_config = codex_config
        return module, paths, request, state, bodies

    def test_invalid_paths_create_no_side_effects(self):
        with Fixture() as f:
            m, paths, request, state, bodies = self.setup_launch(f)
            directory = f.home/'directory'
            directory.mkdir()
            link = f.home/'link'
            link.symlink_to(request.handoff)
            fifo = f.home/'fifo'
            os.mkfifo(fifo)
            unreadable = f.home/'unreadable'
            unreadable.write_text('x')
            snapshot = f.snapshot()
            readable_mode = unreadable.stat().st_mode
            unreadable.chmod(0)
            before = {p.name: p.lstat().st_mode for p in f.home.iterdir()}
            for changes in ({'cwd': Path('relative')}, {'handoff': Path('relative')},
                    {'cwd': f.home/'missing'}, {'handoff': directory}, {'handoff': link},
                    {'handoff': fifo}, {'handoff': unreadable}, {'handoff': Path('/nul\0')},
                    {'window_id': ''}, {'profile': 'x\nname'}, {'window_id': 'x\x7f'}):
                with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, '^launch_'):
                    m.validate_request(replace(request, **changes))
            m.validate_request(request)
            self.assertEqual({p.name: p.lstat().st_mode for p in f.home.iterdir()}, before)
            unreadable.chmod(readable_mode)
            self.assertEqual(f.snapshot(), snapshot)
            invalid = replace(request, cwd=Path('relative'))
            result, findings = m.inspect_launch(paths, invalid, f.runner)
            self.assertIsNone(result)
            self.assertTrue(findings)
            self.assertEqual(f.runner.calls, [])

    def test_copy_bindings_compare_semantics(self):
        m = self.checks()
        p = profile()
        for entry in p['Keyboard Map'].values():
            entry.update({'Version': 2, 'Apply Mode': 0})
            entry['Text'] = entry['Text'].replace('0x', '')
        self.assertEqual(m.check_profile(p), [])
        for key in tuple(p['Keyboard Map']):
            q = profile()
            q['Keyboard Map'][key]['Text'] = '0x04'
            self.assertTrue(m.check_profile(q))
            q = profile()
            q['Keyboard Map'][key]['Action'] = 12
            self.assertTrue(m.check_profile(q))
        self.assertTrue(m.check_profile({'name': p['Name'], 'guid': p['Guid']}))

    def test_effective_tui_overrides(self):
        for config, good in (({'tui': {'copy_on_select': 'never'}}, True),
                ({'tui': {'copy_on_select': 'never', 'alternate_screen': 'always'}}, True),
                ({'tui': {'copy_on_select': 'never', 'alternate_screen': 'never'}}, False),
                ({'tui': {'copy_on_select': 'never', 'fullscreen_transcript': False}}, False),
                ({'tui': {}}, False), ({'tui': None}, False), ({'tui': {'copy_on_select': 'auto'}}, False)):
            with self.subTest(config=config), Fixture() as f:
                m, paths, request, state, bodies = self.setup_launch(f)
                # User TOML is compatible, but only the canonical effective RPC wins.
                paths.codex_home.mkdir()
                (paths.codex_home/'config.toml').write_text('[tui]\ncopy_on_select="never"\n')
                state['config'] = dict(config, mcp_servers={'secret': 'SECRET_SENTINEL'})
                before = f.snapshot()
                result, findings = m.inspect_launch(paths, request, f.runner)
                self.assertEqual(result is not None, good)
                self.assertEqual(bool(findings), not good)
                self.assertNotIn('SECRET_SENTINEL', repr(findings))
                self.assertEqual(f.snapshot(), before)

    def test_profile_and_window_must_be_unique_and_materialized(self):
        for mutation in ('duplicate-name', 'duplicate-guid', 'duplicate-raw', 'wrong-guid', 'missing-map', 'missing-window', 'copy-enabled'):
            with self.subTest(mutation=mutation), Fixture() as f:
                m, paths, request, state, bodies = self.setup_launch(f)
                if mutation == 'duplicate-name': state['live'].append(dict(state['live'][0]))
                elif mutation == 'duplicate-guid': state['live'].append({'guid': 'profile-one', 'name': 'other'})
                elif mutation == 'duplicate-raw': state['raw'] = [state['profile'], dict(state['profile'])]
                elif mutation == 'wrong-guid': state['profile']['Guid'] = 'other'
                elif mutation == 'missing-map': state['profile'].pop('Keyboard Map')
                elif mutation == 'missing-window': state['windows'] = []
                else: state['copy'] = True
                result, findings = m.inspect_launch(paths, request, f.runner)
                self.assertIsNone(result)
                self.assertTrue(findings)
                self.assertTrue(all(x.feature == 'launch' and x.agent == 'codex' for x in findings))

    def test_unknown_wrappers_and_profile_changing_wrapper_fail_closed(self):
        for function, good in (('', True), ('command codex "$@"', True),
                ('command codex --no-daemon "$@"', True), ('command codex --profile work "$@"', False),
                (': iterm2-utils dispatcher; command codex -c tui.alternate_screen=never "$@"', False)):
            with self.subTest(function=function), Fixture() as f:
                m, paths, request, state, bodies = self.setup_launch(f)
                if function: state['identity']['functions']['codex'] = function
                result, findings = m.inspect_launch(paths, request, f.runner)
                self.assertEqual(result is not None, good)
                if result:
                    self.assertEqual(result.identity.executable, f.bin/'codex')
                    self.assertEqual(result.profile_guid, 'profile-one')

    def test_known_wrapper_chain_and_tampered_helper(self):
        for tampered in (False, True):
            with self.subTest(tampered=tampered), Fixture() as f:
                m, paths, request, state, bodies = self.setup_launch(f)
                state['identity']['functions'] = {'codex': bodies['dispatcher'],
                    '_iterm2_utils_classify': 'bad classifier' if tampered else bodies['_iterm2_utils_classify']}
                result, findings = m.inspect_launch(paths, request, f.runner)
                self.assertEqual(result is not None, not tampered)

    def test_platform_dependencies_protocol_and_errors_block(self):
        for problem in ('platform', 'app', 'zsh', 'codex', 'it2', 'version', 'protocol', 'rpc', 'alias'):
            with self.subTest(problem=problem), Fixture(platform='Linux' if problem == 'platform' else 'Darwin') as f:
                m, paths, request, state, bodies = self.setup_launch(f)
                if problem == 'app': (f.app/'Contents/Info.plist').unlink()
                elif problem == 'zsh': (f.bin/'zsh').unlink()
                elif problem == 'codex': (f.bin/'codex').unlink()
                elif problem == 'it2': (f.app/'Contents/Resources/utilities/it2').unlink()
                elif problem == 'version': state['identity']['version'] = 'codex-cli 0.167.0'
                elif problem == 'alias': state['identity']['alias'] = 'codex -c secret=SECRET'
                elif problem == 'rpc':
                    def fail(*a, **k): raise ValueError('SECRET_SENTINEL invalid config')
                    f.runner.codex_config = fail
                elif problem == 'protocol':
                    old = f.runner.run
                    def bad(argv, **kw):
                        out = old(argv, **kw)
                        return subprocess.CompletedProcess(argv, 0, 'unknown', '') if argv[-1] == '--help' else out
                    f.runner.run = bad
                result, findings = m.inspect_launch(paths, request, f.runner)
                self.assertIsNone(result)
                self.assertTrue(findings)
                self.assertNotIn('SECRET', repr(findings))

    def test_nondefault_homes_are_retained_in_identity(self):
        with Fixture() as f, patch.dict(os.environ, {'CODEX_HOME': str(f.home/'other-codex'), 'ZDOTDIR': str(f.home/'shell')}):
            m, paths, request, state, bodies = self.setup_launch(f)
            result, findings = m.inspect_launch(paths, request, f.runner)
            self.assertEqual(findings, [])
            self.assertEqual(result.identity.codex_home, paths.codex_home)
            self.assertEqual(result.identity.zdotdir, paths.zshrc.parent)

    def test_shipped_functions_are_canonical_and_guard_detects_changed_shell(self):
        m = self.checks()
        with Fixture() as f:
            paths = resolve_paths()
            env = dict(os.environ, CODEX_RESTORE_NO_AUTO='1')
            # These are package fixture definitions in a non-login, no-rc shell.
            reference = m._references(paths, Path('/bin/zsh'), Runner(), env)
            (f.bin/'codex').write_text('#!/bin/sh\nprintf "codex-cli 0.166.0\\n"\n')
            (f.bin/'codex').chmod(0o755)
            for layers in ([], ['runtime/codex.zsh'], ['runtime/codex_restore/codex-resume.zsh'],
                    ['runtime/codex.zsh', 'runtime/codex_restore/codex-resume.zsh']):
                with self.subTest(layers=layers):
                    source = ''.join('builtin source '+str(paths.repo/name)+'\n' for name in layers)
                    out = Runner().run(['/bin/zsh', '-dfc', source+m._metadata_command(paths)], timeout=3, env=env)
                    self.assertEqual(out.returncode, 0, out.stderr)
                    raw = json.loads(out.stdout)['iterm2_launch_identity']
                    identity = m._check_wrapper(raw, reference, paths)
                    guard = m.identity_guard(paths, identity)
                    out = Runner().run(['/bin/zsh','-dfc',source+guard], timeout=3, env=env)
                    self.assertEqual(out.returncode, 0, out.stderr)
                    out = Runner().run(['/bin/zsh','-dfc',source+'CODEX_HOME=/different\n'+guard], timeout=3, env=env)
                    self.assertNotEqual(out.returncode, 0)
                    if 'runtime/codex_restore/codex-resume.zsh' in layers:
                        raw['functions']['_codex_restore_previous'] = 'command codex --profile work "$@"'
                        with self.assertRaises(ValueError):
                            m._check_wrapper(raw, reference, paths)

    def test_config_errors_and_secret_stderr_are_sanitized(self):
        with Fixture() as f:
            m, paths, request, state, bodies = self.setup_launch(f)
            paths.codex_home.mkdir()
            (paths.codex_home/'config.toml').write_text('profile="legacy"\n')
            for error in (ValueError('SECRET legacy profile invalid'),
                    PermissionError('SECRET unreadable config'),
                    subprocess.TimeoutExpired('SECRET', 1, stderr='SECRET')):
                def fail(*args, **kwargs): raise error
                f.runner.codex_config = fail
                result, findings = m.inspect_launch(paths, request, f.runner)
                self.assertIsNone(result)
                self.assertEqual(findings[0].code, 'launch_config_unverified')
                self.assertNotIn('SECRET', repr(findings))


class ConfigTransportTests(unittest.TestCase):
    def test_staged_protocol_and_cleanup(self):
        self.assertTrue(hasattr(Runner, 'codex_config'), 'Staged config transport is missing')
        script = '''import json,sys
print(json.dumps({"iterm2_launch_identity":{"fixture":True}}),flush=True)
assert input()=="iterm2-utils-continue"
a=json.loads(input()); assert a["method"]=="initialize"
print(json.dumps({"id":1,"result":{"userAgent":"codex/0.166.0"}}),flush=True)
assert json.loads(input())["method"]=="initialized"
b=json.loads(input()); assert b["method"]=="config/read" and b["params"]["cwd"]==sys.argv[1]
print(json.dumps({"id":2,"result":{"config":{"tui":{"copy_on_select":"never"}}}}),flush=True)
sys.stdin.read()
'''
        with Fixture() as f:
            identity, config = Runner().codex_config([sys.executable, '-c', script, str(f.home)],
                timeout=3, env={'HOME': str(f.home)}, cwd=f.home, check_identity=lambda x: x)
            self.assertEqual(identity, {'fixture': True})
            self.assertEqual(config, {'tui': {'copy_on_select': 'never'}})

    def test_unverified_identity_never_starts_rpc_and_timeout_is_bounded(self):
        self.assertTrue(hasattr(Runner, 'codex_config'), 'Staged config transport is missing')
        with Fixture() as f:
            marker = f.home/'started'
            script = 'import json,sys,pathlib; print(json.dumps({"iterm2_launch_identity":{}}),flush=True); input(); pathlib.Path(sys.argv[1]).touch()'
            def reject(identity): raise ValueError('launch_config_unverified')
            with self.assertRaises(ValueError):
                Runner().codex_config([sys.executable,'-c',script,str(marker)], timeout=1,
                    env={}, cwd=f.home, check_identity=reject)
            self.assertFalse(marker.exists())
            with self.assertRaises((TimeoutError, ValueError)):
                Runner().codex_config([sys.executable,'-c','import time; time.sleep(30)'], timeout=.05,
                    env={}, cwd=f.home, check_identity=lambda x: x)
