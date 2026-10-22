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
