import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.support import Fixture
from iterm2_utils.discovery import discover, resolve_paths


class DiscoveryTests(unittest.TestCase):
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
