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
