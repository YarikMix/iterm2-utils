import contextlib
import io
import json
import unittest
from unittest.mock import patch
from tests.support import Fixture
from iterm2_utils.cli import main


class CliTests(unittest.TestCase):
    def invoke(self, f, args):
        out, err = io.StringIO(), io.StringIO()
        with patch('iterm2_utils.cli.Runner', return_value=f.runner), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = main(args)
        return result, out.getvalue(), err.getvalue()

    def test_macos_fixture_is_independent_of_host_platform(self):
        from iterm2_utils.discovery import discover, resolve_paths
        for host in ('Linux', 'Darwin'):
            with self.subTest(host=host), patch('platform.system', return_value=host):
                with Fixture() as f:
                    context = discover(resolve_paths(), f.runner)
                    self.assertIn('macos', context.capabilities)
                    code, _, err = self.invoke(f, ['plan', '--agent', 'claude', '--features', 'shell'])
                    self.assertEqual(code, 0, err)

    def test_fixture_restores_nested_platform_and_home_after_exception(self):
        import os
        import platform
        with patch('platform.system', return_value='HostOS'), patch.dict(os.environ, {'HOME': '/fixture-host-home'}):
            with Fixture() as outer:
                self.assertEqual(platform.system(), 'Darwin')
                with self.assertRaisesRegex(RuntimeError, 'fixture failure'):
                    with Fixture(platform='Linux') as inner:
                        inner_home = inner.home
                        self.assertEqual(platform.system(), 'Linux')
                        self.assertEqual(os.environ['HOME'], str(inner.home))
                        raise RuntimeError('fixture failure')
                self.assertFalse(inner_home.exists())
                self.assertEqual(platform.system(), 'Darwin')
                self.assertEqual(os.environ['HOME'], str(outer.home))
            self.assertFalse(outer.home.exists())
            self.assertEqual(platform.system(), 'HostOS')
            self.assertEqual(os.environ['HOME'], '/fixture-host-home')

    def test_linux_fixture_rejects_plan_and_install_without_writes(self):
        with Fixture(platform='Linux') as f:
            before = f.snapshot()
            for command in ('plan', 'install'):
                with self.subTest(command=command):
                    code, out, err = self.invoke(f, [command, '--agent', 'claude', '--features', 'shell', '--json'])
                    self.assertEqual(code, 2, err)
                    self.assertTrue(any(item['code'] == 'unsupported_platform' and item['state'] == 'unavailable'
                                        for item in json.loads(out)['findings']))
                    self.assertEqual(f.snapshot(), before)

    def test_empty_choice_writes_nothing(self):
        with Fixture() as f:
            before = f.snapshot()
            code, _, _ = self.invoke(f, ['plan', '--agent', 'claude', '--features', ''])
            self.assertEqual(code, 2)
            self.assertEqual(f.snapshot(), before)
            self.assertEqual(f.runner.calls, [])

    def test_doctor_redacts_other_mcp_env(self):
        with Fixture() as f:
            folder = f.home / '.claude'
            folder.mkdir()
            (folder / 'settings.json').write_text(json.dumps({'mcpServers': {'other': {'env': {'TOKEN': 'UNRELATED_SECRET_MARKER'}}}}))
            before = f.snapshot()
            code, out, err = self.invoke(f, ['doctor', '--json'])
            self.assertNotIn('UNRELATED_SECRET_MARKER', out + err)
            self.assertIn(code, (0, 2, 3))
            json.loads(out)
            self.assertEqual(f.snapshot(), before)

    def test_plan_read_only_and_scoped(self):
        with Fixture() as f:
            before = f.snapshot()
            code, out, err = self.invoke(f, ['plan', '--agent', 'claude', '--features', 'shell', '--json'])
            self.assertEqual(code, 0, err)
            self.assertEqual(f.snapshot(), before)
            self.assertFalse(any('codex' in call[0][0] for call in f.runner.calls))
            self.assertEqual(json.loads(out)['selection']['features'], ['shell'])

    def test_mcp_reports_pending_ui(self):
        with Fixture() as f:
            uvx=f.bin/'uvx'
            uvx.write_text('#!/bin/sh\nexit 0\n')
            uvx.chmod(0o755)
            code, out, _ = self.invoke(f, ['plan', '--agent', 'claude', '--features', 'mcp', '--json'])
            self.assertEqual(code, 3)
            self.assertIn('mcp-server-iterm2==0.1.1', out)
            self.assertIn('mcp<2', out)

    def test_unknown_feature_returns_selection_error(self):
        with Fixture() as f:
            code, _, _ = self.invoke(f, ['plan', '--agent', 'codex', '--features', 'bogus'])
            self.assertEqual(code, 2)

    def test_install_missing_mcp_runtime_and_dry_run_write_nothing(self):
        with Fixture() as f:
            before = f.snapshot()
            for extra in ([], ['--dry-run']):
                code,out,err = self.invoke(f,['install','--agent','codex','--features','mcp','--json',*extra])
                self.assertEqual(code,2,err)
                self.assertEqual(f.snapshot(),before)
                self.assertEqual(json.loads(out)['findings'][-1]['code'],'uvx_missing')

    def test_uninstall_missing_receipt_writes_nothing(self):
        with Fixture() as f:
            before = f.snapshot()
            code,out,err = self.invoke(f,['uninstall','--features','shell','--json'])
            self.assertEqual(code,2,err)
            self.assertEqual(f.snapshot(),before)
            self.assertEqual(json.loads(out)['findings'][0]['code'],'ownership_unavailable')

    def test_update_missing_receipt_is_structured_and_read_only(self):
        with Fixture() as f:
            before=f.snapshot()
            code,out,err=self.invoke(f,['update','--json'])
            self.assertEqual(code,2);self.assertEqual(f.snapshot(),before)
            data=json.loads(out);self.assertEqual(data['selection']['features'],[])
            self.assertEqual(data['findings'][0]['code'],'ownership_unavailable')

    def test_reconcile_requires_known_pending_step(self):
        with Fixture() as f:
            before=f.snapshot()
            code,out,err=self.invoke(f,['reconcile','--step','claude-native-status','--json'])
            self.assertEqual(code,2)
            self.assertEqual(json.loads(out)['findings'][0]['code'],'ownership_unavailable')
            self.assertEqual(f.snapshot(),before)

    def test_doctor_reports_corrupt_receipt_without_mutation(self):
        from iterm2_utils.discovery import resolve_paths
        with Fixture() as f:
            code,out,err=self.invoke(f,['install','--agent','codex','--features','shell','--json'])
            self.assertEqual(code,0,err)
            path=resolve_paths().data/'receipt.json';path.write_text('{PRIVATE_CORRUPT_RECEIPT')
            before=f.snapshot()
            code,out,err=self.invoke(f,['doctor','--json'])
            self.assertEqual(code,2)
            self.assertTrue(any(item['code']=='ownership_unavailable' and item['state']=='conflict' for item in json.loads(out)['findings']))
            self.assertNotIn('PRIVATE_CORRUPT_RECEIPT',out+err)
            self.assertEqual(f.snapshot(),before)
