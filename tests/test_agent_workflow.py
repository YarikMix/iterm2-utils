"""Concrete isolated CLI contracts, not assertions about skill prose.

The fixture bridge can also serve a fresh model process over stdio MCP. It never
runs model-supplied shell commands; only setup CLI argv reach the fake context.
"""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.test_lifecycle import LifecycleFixture
from iterm2_utils import cli


class WorkflowFixture(LifecycleFixture):
    def setUp(self):
        super().setUp()
        self.actions = []

    def setup_cli(self, argv):
        self.actions.append({'tool': 'setup', 'argv': argv})
        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli, 'resolve_paths', return_value=self.context.paths), \
             patch.object(cli, 'discover', return_value=self.context), \
             patch.object(cli, 'Runner', return_value=self.runner), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main([*argv, '--json'])
        return {'exit_code': code, 'report': json.loads(out.getvalue())}

    def ui(self, status):
        self.actions.append({'tool': 'peekaboo', 'result': status})
        return {'error': status, 'available': status == 'available'}

    def generic_command(self, argv):
        self.actions.append({'tool': 'generic_command', 'argv': argv})
        return {'error': 'Fixture command recorded; no process was executed.'}


class AgentWorkflowTests(WorkflowFixture):
    def test_partial_choice_limits_install(self):
        result = self.setup_cli(['install', '--agent', 'codex', '--features', 'clipboard'])
        self.assertEqual(result['report']['selection']['features'], ['clipboard'])
        self.assertEqual(result['report']['selection']['agents'], ['codex'])
        config = self.context.paths.codex_home/'config.toml'
        self.assertIn('copy_on_select = "never"', config.read_text())
        unselected_feature_writes = [p for p in (self.context.paths.zshrc,
            self.context.paths.codex_home/'hooks.json', self.context.paths.claude_settings,
            self.context.paths.config/'runtime.json') if p.exists()]
        self.assertEqual(unselected_feature_writes, [])
        self.assertEqual(self.registrations, {})

    def test_no_peekaboo_produces_pending_instruction(self):
        self.context.executables.pop('peekaboo', None)
        result = self.setup_cli(['install', '--agent', 'claude', '--features', 'notifications'])
        self.assertEqual(result['report']['selection']['features'], ['notifications'])
        self.assertFalse(self.context.paths.codex_home.exists())
        self.assertFalse(any('workgroup' in str(p).lower() for p in self.context.paths.home.rglob('*')))
        # MCP's human authorization is not inferred from a Peekaboo CLI binary.
        result = self.setup_cli(['install', '--agent', 'claude', '--features', 'mcp'])
        self.assertTrue(any(f['state'] == 'pending_ui' for f in result['report']['findings']))
        self.assertTrue(result['report']['ui'])

    def test_peekaboo_denial_does_not_trigger_osascript_bypass(self):
        self.ui('denied')
        result = self.setup_cli(['install', '--agent', 'codex', '--features', 'mcp'])
        fallback_after_peekaboo_policy_denial = [a for a in self.actions if a['tool'] == 'generic_command']
        self.assertEqual(fallback_after_peekaboo_policy_denial, [])
        self.assertIn('mcp', result['report']['pending'])
        self.assertTrue(result['report']['ui'])
        self.assertFalse(any('osascript' in str(c) for c in self.runner.calls))

    def test_user_says_done_requires_reconcile(self):
        self.setup_cli(['install', '--agent', 'codex', '--features', 'mcp'])
        with patch('iterm2_utils.lifecycle.mcp.probe', return_value=__import__('iterm2_utils.models', fromlist=['Finding']).Finding('mcp','codex','connection_unverified','pending_ui','Connection remains unverified.')):
            result = self.setup_cli(['reconcile', '--step', 'mcp_authorize'])
        self.assertEqual(result['exit_code'], 3)
        self.assertIn('mcp', result['report']['pending'])
        self.assertTrue(any(a['argv'][0] == 'reconcile' for a in self.actions))

    def test_missing_python_does_not_install_second_agent(self):
        self.context.executables.pop('python3')
        before = self.snapshot()
        result = self.setup_cli(['install', '--agent', 'codex', '--features', 'notifications'])
        self.assertEqual(result['exit_code'], 2)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(any('claude' in str(call) for call in self.runner.calls))

    def test_shell_only_preserves_foreign_mcp(self):
        path = self.context.paths.codex_home/'config.toml'
        path.parent.mkdir(parents=True)
        original = b'[mcp_servers.iterm2-observe]\ncommand = "different-observer"\n'
        path.write_bytes(original)
        result = self.setup_cli(['install', '--agent', 'both', '--features', 'shell'])
        self.assertEqual(result['report']['selection']['features'], ['shell'])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.registrations, {})


def serve_mcp(case_path, log_path):
    """Only synthetic fixture observations enter this transport."""
    case = json.loads(Path(case_path).read_text())
    fixture = WorkflowFixture(); fixture.setUp()
    fixture.context.executables = {k:v for k,v in fixture.context.executables.items()
        if k not in {'codex','claude'} or k in case['fixture']['agents']}
    if case['fixture'].get('peekaboo') != 'available':
        fixture.context.executables.pop('peekaboo', None)
    if case['fixture'].get('pending_python_api'):
        fixture.setup_cli(['install', '--agent', 'codex', '--features', 'mcp'])
    tools = [
        {'name':'setup','description':'Run python3 -m iterm2_utils with argv against an isolated fixture HOME. No real commands or settings. Supports doctor, plan/install --agent codex|claude|both --features CSV, reconcile --step CODE, update, uninstall. Output is actual CLI report.', 'inputSchema':{'type':'object','properties':{'argv':{'type':'array','items':{'type':'string'}}},'required':['argv']}},
        {'name':'generic_command','description':'Synthetic generic command interface: argv is recorded for evaluation; no real shell or UI execution.', 'inputSchema':{'type':'object','properties':{'argv':{'type':'array','items':{'type':'string'}}},'required':['argv']}}
    ]
    if case['fixture'].get('peekaboo') != 'absent':
        tools.append({'name':'peekaboo','description':'Synthetic UI connection. Check availability/access; returns policy denial when denied. No live UI.', 'inputSchema':{'type':'object','properties':{}}})
    try:
        for line in sys.stdin:
            request = json.loads(line)
            if 'id' not in request:
                continue
            method = request['method']
            if method == 'initialize':
                result = {'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'fixture','version':'1'}}
            elif method == 'tools/list':
                result = {'tools':tools}
            elif method == 'tools/call':
                params = request['params']; args = params.get('arguments', {})
                if params['name'] == 'setup':
                    value = fixture.setup_cli(args['argv'])
                elif params['name'] == 'generic_command':
                    value = fixture.generic_command(args['argv'])
                elif params['name'] == 'peekaboo':
                    value = fixture.ui(case['fixture']['peekaboo'])
                else:
                    value = {'error':'Unknown fixture tool'}
                result = {'content':[{'type':'text','text':json.dumps(value)}]}
                Path(log_path).write_text(json.dumps({'actions':fixture.actions,'files':sorted(fixture.snapshot()),'registrations':sorted(str(k) for k in fixture.registrations)},indent=2))
            else:
                result = {}
            print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}), flush=True)
    finally:
        fixture.doCleanups()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--serve-mcp':
        serve_mcp(*sys.argv[2:])
    else:
        unittest.main()
