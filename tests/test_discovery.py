import os
import json
import plistlib
import shlex
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.support import Fixture
from iterm2_utils.discovery import discover, resolve_paths
from iterm2_utils import discovery


class DiscoveryTests(unittest.TestCase):
    def test_notifier_uses_read_only_single_dash_version_probe(self):
        with Fixture() as f:
            run = f.runner.run
            def notifier_flags(argv, **kwargs):
                result = run(argv, **kwargs)
                if Path(argv[0]).name == 'terminal-notifier':
                    return subprocess.CompletedProcess(argv, 0 if argv[1:] == ['-version'] else 1,
                                                       'terminal-notifier 3.1.0' if argv[1:] == ['-version'] else '', '')
                return result
            f.runner.run = notifier_flags
            before = f.snapshot()
            context = discover(resolve_paths(), f.runner)
            self.assertEqual(context.versions.get('terminal-notifier'), '3.1.0')
            self.assertEqual(context.executables.get('terminal-notifier'), f.bin/'terminal-notifier')
            self.assertEqual([call for call in f.runner.calls if Path(call[0][0]).name == 'terminal-notifier'],
                             [([str(f.bin/'terminal-notifier'), '-version'], 5, None)])
            for name in ('codex', 'claude', 'zsh', 'python3', 'peekaboo'):
                self.assertIn(([str(f.bin/name), '--version'], 5, None), f.runner.calls)
            self.assertEqual(f.snapshot(), before)

    def test_missing_or_failing_notifier_remains_unavailable(self):
        for missing in (True, False):
            with self.subTest(missing=missing), Fixture() as f:
                if missing:
                    (f.bin/'terminal-notifier').unlink()
                run = f.runner.run
                def fail_notifier(argv, **kwargs):
                    result = run(argv, **kwargs)
                    return subprocess.CompletedProcess(argv, 1, '', '') if Path(argv[0]).name == 'terminal-notifier' else result
                f.runner.run = fail_notifier
                context = discover(resolve_paths(), f.runner)
                self.assertNotIn('terminal-notifier', context.executables)
                self.assertNotIn('terminal-notifier', context.versions)

    def test_codex_approval_policy_only_exact_source_verified_versions(self):
        for version, supported in (('0.163.0', True), ('0.164.0', True),
                                   ('0.165.0', False), ('unknown', False)):
            with self.subTest(version=version), Fixture() as f:
                f.runner.responses['codex'] = 'codex-cli '+version+' --no-daemon'
                context = discover(resolve_paths(), f.runner)
                self.assertEqual('codex:approval-notifications' in context.capabilities, supported)
                self.assertEqual('codex:alt-enter' in context.capabilities, version == '0.163.0')

    def test_live_status_accepts_native_terminal_states_without_payload(self):
        from iterm2_utils.models import Selection
        from tests.test_runtime_events import UUID
        with Fixture() as f:
            context=discover(resolve_paths(),f.runner)
            selection=Selection(frozenset({'codex'}),frozenset({'status'}),frozenset(),'Default')
            with patch.dict(os.environ,{'TERM_SESSION_ID':'w0t0p0:'+UUID}):
                for state in ('','idle','working','waiting','done','error','invalid',None,[],{}):
                    with self.subTest(state=state):
                        f.runner.responses['it2']=json.dumps({'status':state,'detail':'PRIVATE'})
                        f.runner.calls.clear()
                        findings=discovery.live_status(context,f.runner,selection)
                        api=next(item for item in findings if item.code=='status_api')
                        self.assertEqual(api.state,'ready' if isinstance(state,str) and state!='invalid' else 'pending_ui')
                        self.assertEqual(f.runner.calls, [([str(context.executables['it2']),'session','get-status','--session',UUID],2,None)])
                        self.assertNotIn('PRIVATE',repr(findings))

    def test_live_status_rejects_ambiguous_invalid_and_tmux_targets(self):
        from iterm2_utils.models import Selection
        from tests.test_runtime_events import UUID
        for environment in ({}, {'TERM_SESSION_ID':'bad'},
                {'TERM_SESSION_ID':UUID,'ITERM_SESSION_ID':'00000000-0000-0000-0000-000000000000'},
                {'TERM_SESSION_ID':UUID,'ITERM_SESSION_ID':''}, {'TERM_SESSION_ID':UUID,'TMUX':'test'}):
            with self.subTest(environment=environment), Fixture() as f:
                context=discover(resolve_paths(),f.runner)
                f.runner.responses['it2']='{"status":"idle"}'
                f.runner.calls.clear()
                selection=Selection(frozenset({'codex'}),frozenset({'status'}),frozenset(),'Default')
                with patch.dict(os.environ,environment):
                    findings=discovery.live_status(context,f.runner,selection)
                self.assertEqual(f.runner.calls,[])
                self.assertEqual(next(item for item in findings if item.code=='status_api').state,'pending_ui')

    def test_claude_only_never_probes_codex(self):
        with Fixture() as f:
            context = discover(resolve_paths(), f.runner, agents=frozenset({'claude'}))
            self.assertIn('claude', context.executables)
            self.assertNotIn('codex', context.executables)
            self.assertFalse(any(Path(call[0][0]).name == 'codex' for call in f.runner.calls))
            self.assertTrue(all(call[1] == 5 for call in f.runner.calls))

    def test_paths_respect_overrides_without_sourcing_shell(self):
        with Fixture() as f:
            with patch.dict(os.environ, {key: str(f.home / key) for key in ('ZDOTDIR', 'CODEX_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME')}):
                paths = resolve_paths()
                self.assertEqual(paths.zshrc, f.home / 'ZDOTDIR/.zshrc')
                self.assertEqual(paths.codex_home, f.home / 'CODEX_HOME')
                self.assertEqual(paths.config, f.home / 'XDG_CONFIG_HOME/iterm2-utils')
                before = f.snapshot()
                discover(paths, f.runner)
                self.assertEqual(f.snapshot(), before)
                self.assertFalse(any('-c' in call[0] for call in f.runner.calls))

    def test_invalid_app_is_not_accepted(self):
        with Fixture() as f:
            (f.app / 'Contents/Info.plist').write_bytes(b'broken')
            context = discover(resolve_paths(), f.runner)
            self.assertNotIn('iterm2', context.executables)

    def test_timeout_does_not_expose_process_output(self):
        with Fixture() as f:
            def fail(argv, **kwargs):
                raise subprocess.TimeoutExpired(argv, 5, output='UNRELATED_SECRET_MARKER')
            f.runner.run = fail
            context = discover(resolve_paths(), f.runner)
            self.assertNotIn('UNRELATED_SECRET_MARKER', repr(context))

    def test_preferences_snapshot_is_allowlisted_and_native_profiles_discovered(self):
        import plistlib
        with Fixture() as f:
            f.runner.responses['defaults']=plistlib.dumps({'CopySelection':True,'PreventApplicationInitiatedProfileChanges':False,'PRIVATE_MARKER':'do not retain','New Bookmarks':[{'Name':'Default','Guid':'native'}]}).decode()
            context=discover(resolve_paths(),f.runner)
            self.assertEqual(context.preferences,{'com.googlecode.iterm2':{'CopySelection':True}})
            self.assertEqual(context.profiles['Default']['Guid'],'native')
            self.assertNotIn('PRIVATE_MARKER',repr(context))

    def test_claude_alt_enter_only_current_documented_exact_release(self):
        with Fixture() as f:
            f.runner.responses['claude']='2.1.308 (Claude Code)'
            self.assertIn('claude:alt-enter',discover(resolve_paths(),f.runner).capabilities)
            for output in ('0.1 (Claude Code)', '2.1.309 (Claude Code)', '99.0.0 (Claude Code)', 'version unavailable'):
                with self.subTest(output=output):
                    f.runner.responses['claude']=output
                    self.assertNotIn('claude:alt-enter',discover(resolve_paths(),f.runner).capabilities)

    def test_codex_alt_enter_only_source_verified_version(self):
        with Fixture() as f:
            f.runner.responses['codex']='codex-cli 0.163.0 --no-daemon'
            self.assertIn('codex:alt-enter',discover(resolve_paths(),f.runner).capabilities)
            f.runner.responses['codex']='codex-cli 0.164.0 --no-daemon'
            self.assertNotIn('codex:alt-enter',discover(resolve_paths(),f.runner).capabilities)


class NativeCodexDiscoveryTests(unittest.TestCase):
    NATIVE_EVENTS = ('SessionStart', 'SessionEnd', 'UserPromptSubmit', 'PreToolUse',
                     'PermissionRequest', 'PostToolUse', 'SubagentStart',
                     'SubagentStop', 'Stop', 'Interrupt')

    def hooks(self, app):
        command = shlex.quote(str(app/'Contents/Resources/utilities/cc-status'))+' --agent codex'
        return {event: [{'hooks': [{'type': 'command', 'command': command, 'timeout': 3}]}]
                for event in self.NATIVE_EVENTS}

    def write_hooks(self, paths, hooks):
        paths.codex_home.mkdir(exist_ok=True)
        (paths.codex_home/'hooks.json').write_text(json.dumps({'hooks': hooks, 'private': 'PRIVATE_MARKER'}))

    def test_native_bundle_version_floor_and_read_only_probes(self):
        for version, expected in [('3.7.5', False), ('3.7.6', True), ('3.7.7', True), ('unknown', False)]:
            with self.subTest(version=version), Fixture() as f:
                info = f.app/'Contents/Info.plist'
                document = plistlib.loads(info.read_bytes())
                document['CFBundleShortVersionString'] = version
                info.write_bytes(plistlib.dumps(document))
                before = f.snapshot()
                context = discover(resolve_paths(), f.runner)
                self.assertEqual('iterm2:cc-status-codex' in context.capabilities, expected)
                self.assertEqual(f.snapshot(), before)
                self.assertFalse(any(Path(call[0][0]).name == 'cc-status' for call in f.runner.calls))
                if expected:
                    self.assertIn([str(f.app/'Contents/Resources/utilities/it2'), 'set-status', '--help'],
                                  [call[0] for call in f.runner.calls])

    def test_native_bundle_requires_executable_siblings(self):
        for name in ('it2', 'cc-status'):
            for mode in ('missing', 'non-executable'):
                with self.subTest(name=name, mode=mode), Fixture() as f:
                    target = f.app/'Contents/Resources/utilities'/name
                    if mode == 'missing':
                        target.unlink()
                    else:
                        target.chmod(0o644)
                    self.assertNotIn('iterm2:cc-status-codex', discover(resolve_paths(), f.runner).capabilities)

    def test_native_bundle_requires_every_exact_help_flag(self):
        flags = ('--background-tasks', '--background-tasks-delta', '--turn-open',
                 '--if-turn-open', '--if-background-tasks', '--json')
        for missing in flags:
            with self.subTest(missing=missing), Fixture() as f:
                f.runner.responses['it2'] = 'set-status session-status '+' '.join(flag for flag in flags if flag != missing)
                self.assertNotIn('iterm2:cc-status-codex', discover(resolve_paths(), f.runner).capabilities)

    def test_bundle_paths_with_spaces_and_unicode(self):
        with Fixture() as f:
            moved = f.app.parent/'Тест iTerm.app'
            f.app.rename(moved)
            with patch.dict(os.environ, {'ITERM2_APP': str(moved)}):
                context = discover(resolve_paths(), f.runner)
                self.assertIn('iterm2:cc-status-codex', context.capabilities)
                paths = resolve_paths()
                self.write_hooks(paths, self.hooks(moved))
                self.assertEqual(discovery.native_codex_hook_state(paths, moved), 'complete')

    def test_external_native_complete_inventory_contains_only_booleans(self):
        with Fixture() as f:
            paths = resolve_paths()
            self.write_hooks(paths, self.hooks(f.app))
            before = f.snapshot()
            self.assertEqual(discovery.native_codex_hook_state(paths, f.app), 'complete')
            installed = discover(paths, f.runner).installed
            self.assertEqual(installed.get('codex-native-status'), {'enabled': True})
            self.assertNotIn('PRIVATE_MARKER', repr(installed))
            self.assertEqual(f.snapshot(), before)
            self.assertFalse(any(Path(call[0][0]).name == 'cc-status' for call in f.runner.calls))

    def test_external_partial_duplicate_wrapped_or_other_bundle_conflicts(self):
        for case in ('partial', 'duplicate', 'other-bundle', 'shell', 'extra-argument',
                     'wrong-agent', 'matcher', 'extra-event', 'legacy'):
            with self.subTest(case=case), Fixture() as f:
                paths = resolve_paths()
                hooks = self.hooks(f.app)
                group = hooks['Stop'][0]
                native = group['hooks'][0]
                if case == 'partial':
                    del hooks['Interrupt']
                elif case == 'duplicate':
                    hooks['Stop'].append(group)
                elif case == 'other-bundle':
                    native['command'] = '/other/iTerm.app/Contents/Resources/utilities/cc-status --agent codex'
                elif case == 'shell':
                    native['command'] = 'sh -c '+shlex.quote(native['command'])
                elif case == 'extra-argument':
                    native['command'] += ' --json'
                elif case == 'wrong-agent':
                    native['command'] = native['command'].replace('--agent codex', '--agent claude')
                elif case == 'matcher':
                    group['matcher'] = 'Bash'
                elif case == 'extra-event':
                    hooks['PreCompact'] = hooks['Stop']
                self.write_hooks(paths, hooks)
                if case == 'legacy':
                    (paths.codex_home/'config.toml').write_text('[plugins."iterm2-status@known"]\nenabled = true\n')
                self.assertEqual(discovery.native_codex_hook_state(paths, f.app), 'conflict')
                self.assertEqual(discover(paths, f.runner).installed.get('codex-native-status'), {'conflict': True})

    def test_external_native_symlink_must_resolve_to_selected_bundle(self):
        for correct in (True, False):
            with self.subTest(correct=correct), Fixture() as f:
                paths = resolve_paths()
                target = f.app/'Contents/Resources/utilities/cc-status' if correct else f.bin/'codex'
                link = f.home/'.config/iterm2/cc-status'
                link.parent.mkdir(parents=True)
                link.symlink_to(target)
                hooks = self.hooks(f.app)
                for groups in hooks.values():
                    groups[0]['hooks'][0]['command'] = shlex.quote(str(link))+' --agent codex'
                    groups[0]['matcher'] = '*'
                self.write_hooks(paths, hooks)
                self.assertEqual(discovery.native_codex_hook_state(paths, f.app), 'complete' if correct else 'conflict')

    def test_ordinary_foreign_hook_is_preserved_and_not_guessed_to_be_status(self):
        with Fixture() as f:
            paths = resolve_paths()
            self.assertEqual(discovery.native_codex_hook_state(paths, f.app), 'absent')
            hooks = {'Stop': [{'hooks': [{'type': 'command', 'command': '/third-party/foreign-hook'}]}]}
            self.write_hooks(paths, hooks)
            before = f.snapshot()
            self.assertEqual(discovery.native_codex_hook_state(paths, f.app), 'absent')
            self.assertNotIn('codex-native-status', discover(paths, f.runner).installed)
            self.assertEqual(f.snapshot(), before)
            complete = self.hooks(f.app)
            complete['Stop'] += hooks['Stop']
            self.write_hooks(paths, complete)
            self.assertEqual(discovery.native_codex_hook_state(paths, f.app), 'complete')

    def test_status_names_in_foreign_arguments_are_not_writer_evidence(self):
        for name in ('cc-status', 'iterm2-status', 'codex-iterm2-status'):
            ordinary = '/third-party/record-event --tag '+name
            quoted_separator = "/third-party/record-event --tag ';' "+name
            for command in (ordinary, quoted_separator, 'sh -c '+shlex.quote(ordinary),
                            'sh -c '+shlex.quote(quoted_separator),
                            'env -u '+name+' /third-party/record-event',
                            'exec -a '+name+' /third-party/record-event',
                            'nice -n 5 /third-party/record-event '+name,
                            '> '+name+' /third-party/record-event',
                            "'>' /dev/null "+name):
                for complete in (False, True):
                    with self.subTest(command=command, complete=complete), Fixture() as f:
                        paths = resolve_paths()
                        hooks = self.hooks(f.app) if complete else {}
                        hooks.setdefault('Stop', []).append(
                            {'hooks': [{'type': 'command', 'command': command}]})
                        self.write_hooks(paths, hooks)
                        before = f.snapshot()
                        self.assertEqual(discovery.native_codex_hook_state(paths, f.app),
                                         'complete' if complete else 'absent')
                        self.assertEqual(f.snapshot(), before)

    def test_actual_wrapped_status_commands_still_conflict(self):
        for name in ('cc-status', 'iterm2-status', 'codex-iterm2-status'):
            actual = '/third-party/'+name+' --agent codex'
            for command in (actual, 'sh -c '+shlex.quote(actual),
                            'sh -lc '+shlex.quote('/third-party/record-event; '+actual),
                            'sh -c '+shlex.quote('if true; then '+actual+'; fi'),
                            'env MODE=test '+actual, 'exec '+actual):
                with self.subTest(command=command), Fixture() as f:
                    paths = resolve_paths()
                    hooks = self.hooks(f.app)
                    hooks['Stop'].append({'hooks': [{'type': 'command', 'command': command}]})
                    self.write_hooks(paths, hooks)
                    self.assertEqual(discovery.native_codex_hook_state(paths, f.app), 'conflict')

    def test_nice_and_leading_redirection_are_executable_positions(self):
        commands = (
            '/usr/bin/nice -n 5 /third-party/cc-status --agent codex',
            '/usr/bin/nice --adjustment=5 /third-party/cc-status --agent codex',
            '> /dev/null /third-party/cc-status --agent codex',
            '2>/dev/null MODE=test > /dev/null /third-party/cc-status --agent codex',
        )
        for command in commands:
            for complete in (False, True):
                with self.subTest(command=command, complete=complete), Fixture() as f:
                    paths=resolve_paths();hooks=self.hooks(f.app) if complete else {}
                    hooks.setdefault('Stop',[]).append({'hooks':[{'type':'command','command':command}]})
                    self.write_hooks(paths,hooks);before=f.snapshot()
                    self.assertEqual(discovery.native_codex_hook_state(paths,f.app),'conflict')
                    self.assertEqual(f.snapshot(),before)

    def test_wrapper_option_operands_do_not_hide_executing_native_writer(self):
        commands = (
            'env -u UNUSED /third-party/cc-status --agent codex',
            'exec -a custom-name /third-party/cc-status --agent codex',
            'env --unset UNUSED /third-party/cc-status --agent codex',
        )
        for command in commands:
            for complete in (False, True):
                with self.subTest(command=command, complete=complete), Fixture() as f:
                    paths = resolve_paths()
                    hooks = self.hooks(f.app) if complete else {}
                    hooks.setdefault('Stop', []).append({'hooks': [{'type': 'command', 'command': command}]})
                    self.write_hooks(paths, hooks)
                    self.assertEqual(discovery.native_codex_hook_state(paths, f.app), 'conflict')

    def test_executing_shell_substitutions_conflict_but_literal_arguments_do_not(self):
        actual = '/third-party/cc-status --agent codex'
        backslash = chr(92)
        bodies = (
            ('/third-party/record-event "$('+actual+')"', True),
            ('/third-party/record-event "`'+actual+'`"', True),
            ("/third-party/record-event '$("+actual+")'", False),
            ('/third-party/record-event "'+backslash+'$('+actual+')"', False),
            ("/third-party/record-event '`"+actual+"`'", False),
            ('/third-party/record-event "'+backslash+'`'+actual+backslash+'`"', False),
            ('/third-party/record-event "$(/third-party/record-event --tag cc-status)"', False),
        )
        for body, executing in bodies:
            command = 'sh -c '+shlex.quote(body)
            for complete in (False, True):
                with self.subTest(body=body, complete=complete), Fixture() as f:
                    paths = resolve_paths()
                    hooks = self.hooks(f.app) if complete else {}
                    hooks.setdefault('Stop', []).append({'hooks': [{'type': 'command', 'command': command}]})
                    self.write_hooks(paths, hooks)
                    before = f.snapshot()
                    expected = 'conflict' if executing else ('complete' if complete else 'absent')
                    self.assertEqual(discovery.native_codex_hook_state(paths, f.app), expected)
                    self.assertEqual(f.snapshot(), before)

    def test_shell_comments_ignore_writers_but_quoted_hash_and_newline_do_not(self):
        actual = '/third-party/cc-status --agent codex'
        substitution = '"$('+actual+')"'
        bodies = (
            ('/third-party/record-event # '+substitution, False),
            ('/third-party/record-event # ; '+actual, False),
            ('/third-party/record-event # "$('+actual, False),
            ('/third-party/record-event # '+substitution+'\n/third-party/record-event', False),
            ('/third-party/record-event # ignored\n/third-party/record-event '+substitution, True),
            ('/third-party/record-event "#" '+substitution, True),
            ("/third-party/record-event '#' "+substitution, True),
            ('/third-party/record-event '+chr(92)+'# '+substitution, True),
            ('/third-party/record-event value#'+substitution, True),
            ('/third-party/record-event escaped'+chr(92)+' #'+substitution, True),
        )
        for body, executing in bodies:
            for wrapped in (False, True):
                command = 'sh -c '+shlex.quote(body) if wrapped else body
                for complete in (False, True):
                    with self.subTest(body=body, wrapped=wrapped, complete=complete), Fixture() as f:
                        paths = resolve_paths()
                        hooks = self.hooks(f.app) if complete else {}
                        hooks.setdefault('Stop', []).append({'hooks': [{'type': 'command', 'command': command}]})
                        self.write_hooks(paths, hooks)
                        before = f.snapshot()
                        expected = 'conflict' if executing else ('complete' if complete else 'absent')
                        self.assertEqual(discovery.native_codex_hook_state(paths, f.app), expected)
                        self.assertEqual(f.snapshot(), before)

    def test_backtick_comments_do_not_consume_substitution_boundary(self):
        actual = '/third-party/cc-status --agent codex'
        bodies = (
            ('/third-party/record-event `printf ordinary # ignored`', False),
            ('/third-party/record-event "`printf ordinary # ignored`"', False),
            ('/third-party/record-event `printf ordinary # '+actual+'`', False),
            ('/third-party/record-event `printf ordinary # '+chr(92)+'` ignored`', False),
            ('/third-party/record-event `printf ordinary # ignored\nprintf more`', False),
            ('/third-party/record-event `'+actual+' # ignored`', True),
            ('/third-party/record-event `printf ordinary # ignored\n'+actual+'`', True),
            ('/third-party/record-event `printf ordinary # ignored` "$('+actual+')"', True),
            ('/third-party/record-event "$(printf ordinary # ) '+actual+'\n)"', False),
        )
        for body, executing in bodies:
            for wrapped in (False, True):
                command = 'sh -c '+shlex.quote(body) if wrapped else body
                for complete in (False, True):
                    with self.subTest(body=body, wrapped=wrapped, complete=complete), Fixture() as f:
                        paths = resolve_paths()
                        hooks = self.hooks(f.app) if complete else {}
                        hooks.setdefault('Stop', []).append(
                            {'hooks': [{'type': 'command', 'command': command}]})
                        self.write_hooks(paths, hooks)
                        before = f.snapshot()
                        expected = 'conflict' if executing else ('complete' if complete else 'absent')
                        self.assertEqual(discovery.native_codex_hook_state(paths, f.app), expected)
                        self.assertEqual(f.snapshot(), before)
