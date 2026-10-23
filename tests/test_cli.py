import contextlib
import io
import json
import subprocess
import unittest
from unittest.mock import patch
from tests.support import Fixture
from iterm2_utils.cli import main


class CliTests(unittest.TestCase):
    def test_doctor_missing_native_pair_blocks_without_executing_handler(self):
        for name in ('it2','cc-status'):
            with self.subTest(name=name), Fixture() as f:
                code,out,err=self.invoke(f,['install','--agent','codex','--features','status','--json'])
                self.assertEqual(code,0,out+err)
                (f.app/'Contents/Resources/utilities'/name).unlink()
                before=f.snapshot()
                f.runner.calls.clear()
                code,out,err=self.invoke(f,['doctor','--json'])
                self.assertEqual(code,2,out+err)
                self.assertTrue(any(item['code']=='native_status_capability' and item['state']=='unavailable'
                                    for item in json.loads(out)['findings']))
                self.assertFalse(any(call[0][0].endswith('/cc-status') for call in f.runner.calls))
                self.assertEqual(f.snapshot(),before)

    def test_doctor_preserves_pending_trust_and_unknown_error_source(self):
        from iterm2_utils import state
        from iterm2_utils.discovery import resolve_paths
        from iterm2_utils.models import UiStep
        with Fixture() as f:
            f.runner.responses['codex']='codex-cli 0.164.0 --no-daemon'
            code,out,err=self.invoke(f,['install','--agent','codex','--features','status','--json'])
            self.assertEqual(code,0,out+err)
            receipt_path=resolve_paths().data/'receipt.json'
            receipt=state.load(receipt_path)
            receipt.pending_ui.append(UiStep('hook-trust','status','codex','Confirm hook trust and start a new session.'))
            state.save(receipt_path,receipt)
            before=f.snapshot()
            code,out,err=self.invoke(f,['doctor','--json'])
            self.assertEqual(code,3,out+err)
            findings={item['code']:item for item in json.loads(out)['findings']}
            self.assertEqual(findings['hook-trust']['state'],'pending_ui')
            self.assertEqual(findings['codex_error_event']['state'],'limited')
            self.assertIn('unverified',findings['codex_error_event']['message'])
            hooks=json.loads((resolve_paths().codex_home/'hooks.json').read_text())['hooks']
            self.assertEqual(len(hooks),12)
            self.assertFalse({'StopFailure','Notification','PostToolUseFailure'} & hooks.keys())
            self.assertEqual(f.snapshot(),before)

    def test_doctor_native_error_limit_is_nonblocking_and_read_only(self):
        from iterm2_utils.discovery import resolve_paths
        from tests.test_runtime_events import UUID
        with Fixture() as f:
            f.runner.responses['codex']='codex-cli 0.163.0 --no-daemon'
            code,out,err=self.invoke(f,['install','--agent','codex','--features','status','--json'])
            self.assertEqual(code,0,err)
            before=f.snapshot()
            for live in (False,True):
                # Discovery's help response stays separate from the live read.
                original=f.runner.run
                def run(argv,**kwargs):
                    if argv[1:3]==['session','get-status']:
                        f.runner.calls.append((argv,kwargs['timeout'],kwargs.get('stdin')))
                        return subprocess.CompletedProcess(argv,0,'{"status":"done","detail":"PRIVATE"}','')
                    return original(argv,**kwargs)
                f.runner.responses['it2']='session-status set-status --background-tasks --background-tasks-delta --turn-open --if-turn-open --if-background-tasks --json'
                with patch.dict('os.environ',{'TERM_SESSION_ID':UUID}), patch.object(f.runner,'run',side_effect=run):
                    code,out,err=self.invoke(f,['doctor','--json',*(['--live'] if live else [])])
                self.assertEqual(code,0,out+err)
                findings={item['code']:item for item in json.loads(out)['findings']}
                self.assertEqual(findings['codex_error_event']['state'],'limited')
                self.assertIn('0.163.0',findings['codex_error_event']['message'])
                self.assertEqual(findings['status_backend']['state'],'ready')
                if live:self.assertEqual(findings['status_api']['state'],'ready')
                api_calls=[call for call in f.runner.calls if call[0][1:3]==['session','get-status']]
                self.assertEqual(len(api_calls),int(live))
                self.assertFalse(any(call[0][0].endswith('/cc-status') or
                    call[0][1:2]==['set-status'] and call[0][2:]!=['--help'] for call in f.runner.calls))
                self.assertNotIn('PRIVATE',out+err)
                self.assertEqual(f.snapshot(),before)
            settings=resolve_paths().config/'runtime.json'
            settings.write_text('{PRIVATE')
            code,out,err=self.invoke(f,['doctor','--json'])
            self.assertEqual(code,2)
            self.assertNotIn('PRIVATE',out+err)

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
