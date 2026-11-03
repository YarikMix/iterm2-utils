"""Native adapter contracts use synthetic inventories and a fake SDK only."""
import asyncio
import copy
import json
import io
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import redirect_stdout

from iterm2_utils.config import iterm
from iterm2_utils import profile_api
from tests.support import FakeRunner, Fixture
from iterm2_utils.discovery import discover, resolve_paths


BEFORE = {'Show Status Bar': False, 'Status Bar Layout': {'components': [], 'advanced': {'margin': 1}}}
AFTER = dict(BEFORE, **{'Show Status Bar': True})


def inventory():
    return dict(complete=True, profiles=[dict(guid='parent-guid', name='Default', bar=copy.deepcopy(BEFORE),
        working_directory='/fixture/project-a', references=[])], sessions=[], default_guid='parent-guid', position=0)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture().__enter__()
        self.addCleanup(self.fixture.__exit__, None, None, None)
        self.context = discover(resolve_paths(), self.fixture.runner)
        self.runner = FakeRunner()
        self.runner.responses['python3'] = json.dumps({'status': 'ok', 'value': inventory()})

    def respond(self, value):
        self.runner.responses['python3'] = json.dumps(value)

    def test_inspect_uses_selected_python_bounded_stdin_protocol(self):
        self.assertEqual(iterm.inspect(self.context, self.runner), inventory())
        argv, timeout, stdin = self.runner.calls[0]
        self.assertEqual(argv[0], str(self.context.executables['python3']))
        self.assertEqual(timeout, 10)
        self.assertEqual(json.loads(stdin), {'operation': 'inspect'})
        self.assertNotIn('parent-guid', ' '.join(argv))

    def test_grouped_bar_and_position_are_existing_typed_values(self):
        for value in (None, {}, {'Show Status Bar': 1, 'Status Bar Layout': {}},
                      {'Show Status Bar': True, 'Status Bar Layout': None},
                      dict(BEFORE, foreign=1)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                iterm.write_bar('parent-guid', value, self.context, self.runner, expected={'exists': True, 'value': BEFORE})
        for value in (None, True, '1', 2):
            with self.subTest(value=value), self.assertRaises(ValueError):
                iterm.write_position(value, self.context, self.runner, expected={'exists': True, 'value': 0})
        self.assertEqual(self.runner.calls, [])

    def test_expected_absence_or_wrong_type_rejected_before_sdk(self):
        for expected in ({'exists': False, 'value': None}, {'exists': True, 'value': None},
                         {'exists': 1, 'value': BEFORE}):
            with self.assertRaises(ValueError):
                iterm.write_bar('parent-guid', AFTER, self.context, self.runner, expected=expected)
        with self.assertRaises(ValueError):
            iterm.write_position(1, self.context, self.runner, expected={'exists': True, 'value': False})
        self.assertEqual(self.runner.calls, [])

    def test_write_timeout_and_unknown_or_malformed_reply_never_retry(self):
        for failure in ('timeout', 'garbage', '{"status":"unknown"}', '{"status":"ok","value":null}'):
            with self.subTest(failure=failure):
                self.runner.calls.clear()
                self.respond({'status': 'ok', 'value': AFTER})
                original = self.runner.run
                if failure == 'timeout':
                    def run(*args, **kwargs):
                        original(*args, **kwargs)
                        raise subprocess.TimeoutExpired(['fixture'], 10, output='PRIVATE', stderr='PRIVATE')
                else:
                    self.runner.responses['python3'] = failure
                    run = original
                with patch.object(self.runner, 'run', side_effect=run):
                    with self.assertRaises(iterm.MutationUnknown) as error:
                        iterm.write_bar('parent-guid', AFTER, self.context, self.runner,
                                        expected={'exists': True, 'value': BEFORE})
                self.assertNotIn('PRIVATE', str(error.exception))
                self.assertEqual(len(self.runner.calls), 1)

    def test_read_and_write_exact_guid_with_readback(self):
        self.respond({'status': 'ok', 'value': {'exists': True, 'value': BEFORE}})
        self.assertEqual(iterm.read_bar('parent-guid', self.context, self.runner)['value'], BEFORE)
        self.respond({'status': 'ok', 'value': {'exists': True, 'value': AFTER}})
        iterm.write_bar('parent-guid', AFTER, self.context, self.runner, expected={'exists': True, 'value': BEFORE})
        request = json.loads(self.runner.calls[-1][2])
        self.assertEqual(request['guid'], 'parent-guid')
        self.assertEqual(request['expected'], {'exists': True, 'value': BEFORE})
        self.assertEqual(request['value'], AFTER)
        self.respond({'status': 'ok', 'value': {'exists': True, 'value': BEFORE}})
        with self.assertRaises(iterm.MutationUnknown):
            iterm.write_bar('parent-guid', AFTER, self.context, self.runner, expected={'exists': True, 'value': BEFORE})

    def test_reference_guard_checks_external_profiles_sessions_and_completeness(self):
        for mutate in (lambda x:x['profiles'][0]['references'].append('removed-guid'),
                       lambda x:x['sessions'].append(dict(id='session-one', profile_guid='removed-guid', bar=BEFORE,
                           references=[], provenance=True)),
                       lambda x:x.update(complete=False),
                       lambda x:x.pop('sessions'),
                       lambda x:x['profiles'].append(copy.deepcopy(x['profiles'][0]))):
            data = inventory(); mutate(data); self.respond({'status': 'ok', 'value': data})
            with self.assertRaises(ValueError):
                iterm.ensure_unreferenced({'removed-guid'}, {'removed-guid'}, self.context, self.runner)
        data = inventory()
        data['profiles'].extend([dict(guid=g, name=g, bar=BEFORE, working_directory=None,
            references=['removed-guid','other-removed']) for g in ('removed-guid','other-removed')])
        self.respond({'status': 'ok', 'value': data})
        iterm.ensure_unreferenced({'removed-guid','other-removed'}, {'removed-guid','other-removed'}, self.context, self.runner)
        data['sessions'] = [dict(id='new-session', profile_guid='parent-guid', bar=BEFORE,
                                references=[], provenance=False)]
        self.respond({'status': 'ok', 'value': data})
        with self.assertRaises(ValueError):
            iterm.ensure_unreferenced({'removed-guid'}, {'removed-guid'}, self.context, self.runner)


class NativeSdkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.properties = {'Guid': 'parent-guid', 'Name': 'Default', 'Working Directory': '/fixture/project-a',
                           'Foreign': {'preserve': True}, **copy.deepcopy(BEFORE)}
        self.sessions = []
        self.writes = []
        self.position = 0
        self.closed = []
        async def close(): self.closed.append(True)
        self.connection = SimpleNamespace(websocket=SimpleNamespace(close=close))
        async def connect(): return self.connection
        async def profiles(connection): return [SimpleNamespace(all_properties=copy.deepcopy(self.properties))]
        async def default(connection): return SimpleNamespace(guid='parent-guid')
        async def app(connection):
            return SimpleNamespace(terminal_windows=[SimpleNamespace(tabs=[SimpleNamespace(all_sessions=self.sessions)])], buried_sessions=[])
        async def get_preference(connection, key): return self.position
        async def set_preference(connection, key, value):
            self.position = value; self.writes.append(('position', key, value))
        async def set_properties(connection, session_id, assignments, guids=None):
            self.writes.append((session_id, assignments, guids))
            self.properties.update({k: json.loads(v) for k,v in assignments})
        self.sdk = SimpleNamespace(Connection=SimpleNamespace(async_create=connect),
            Profile=SimpleNamespace(async_get=profiles, async_get_default=default), async_get_app=app,
            preferences=SimpleNamespace(PreferenceKey=SimpleNamespace(STATUS_BAR_POSITION=SimpleNamespace(value='StatusBarPosition')),
                async_get_preference=get_preference, async_set_preference=set_preference),
            rpc=SimpleNamespace(async_set_profile_properties_json=set_properties))
        self.patch = patch.dict(sys.modules, {'iterm2': self.sdk}); self.patch.start(); self.addCleanup(self.patch.stop)

    async def operate(self, **request):
        return await profile_api._operate(request)

    async def test_group_write_only_two_fields_and_exact_guid(self):
        result = await self.operate(operation='write_bar', guid='parent-guid', value=AFTER, expected={'exists': True, 'value': BEFORE})
        self.assertEqual(result, {'status': 'ok', 'value': {'exists': True, 'value': AFTER}})
        session, assignments, guids = self.writes[0]
        self.assertIsNone(session)
        self.assertEqual(guids, ['parent-guid'])
        self.assertEqual({k:json.loads(v) for k,v in assignments}, AFTER)
        self.assertEqual(self.properties['Foreign'], {'preserve': True})
        self.assertEqual(self.closed, [True])

    async def test_divergent_session_or_unknown_provenance_blocks_parent(self):
        for extra in ({'Guid': 'parent-guid', **AFTER}, {'Guid': 'unknown-guid', **BEFORE}):
            async def get_profile(): return SimpleNamespace(all_properties=extra)
            self.sessions = [SimpleNamespace(session_id='session-one', async_get_profile=get_profile)]
            result = await self.operate(operation='write_bar', guid='parent-guid', value=AFTER, expected={'exists': True, 'value': BEFORE})
            self.assertEqual(result, {'status': 'conflict'})
            self.assertEqual(self.writes, [])

    async def test_typed_cas_and_malformed_input_never_write(self):
        for before in (dict(BEFORE, **{'Show Status Bar': 0}), None):
            result = await self.operate(operation='write_bar', guid='parent-guid', value=AFTER, expected={'exists': True, 'value': before})
            self.assertEqual(result, {'status': 'conflict'})
            self.assertEqual(self.writes, [])

    async def test_inventory_captures_hidden_references_and_buried_session_bindings(self):
        self.properties['hidden'] = {'disabled': json.dumps({'parameter': 'parent-guid'})}
        async def get_profile(): return SimpleNamespace(all_properties={'Guid':'local-guid','Original Guid':'parent-guid', **BEFORE})
        self.sessions = [SimpleNamespace(session_id='session-one', async_get_profile=get_profile)]
        result = await self.operate(operation='inspect')
        self.assertEqual(result['value']['profiles'][0]['references'], ['parent-guid'])
        self.assertEqual(result['value']['sessions'][0]['profile_guid'], 'parent-guid')
        self.assertTrue(result['value']['sessions'][0]['provenance'])

    async def test_position_typed_restore(self):
        result = await self.operate(operation='write_position', value=1, expected={'exists': True, 'value': 0})
        self.assertEqual(result, {'status':'ok','value':{'exists':True,'value':1}})
        result = await self.operate(operation='write_position', value=0, expected={'exists': True, 'value': 1})
        self.assertEqual(result['value']['value'], 0)
        result = await self.operate(operation='write_position', value=1, expected={'exists': True, 'value': False})
        self.assertEqual(result, {'status':'conflict'})
        self.assertEqual(len(self.writes), 2)

    async def test_reference_guard_sees_guid_even_after_target_disappears(self):
        removed = '11111111-1111-4111-8111-111111111111'
        self.properties['hidden'] = {'action':27, 'parameter':removed}
        result = await self.operate(operation='inspect', reference_guids=[removed])
        self.assertEqual(result['status'], 'ok')
        self.assertIn(removed, result['value']['profiles'][0]['references'])

    async def test_buried_sessions_are_included(self):
        async def get_profile(): return SimpleNamespace(all_properties={'Guid':'parent-guid', **BEFORE})
        buried = SimpleNamespace(session_id='buried-session', async_get_profile=get_profile)
        async def app(connection): return SimpleNamespace(terminal_windows=[], buried_sessions=[buried])
        self.sdk.async_get_app = app
        result = await self.operate(operation='inspect')
        self.assertEqual(result['value']['sessions'][0]['id'], 'buried-session')

    async def test_new_divergent_session_between_reads_blocks_dispatch(self):
        calls = []
        async def get_profile(): return SimpleNamespace(all_properties={'Guid':'parent-guid', **AFTER})
        async def app(connection):
            calls.append(True)
            sessions = [] if len(calls)==1 else [SimpleNamespace(session_id='new-session', async_get_profile=get_profile)]
            return SimpleNamespace(terminal_windows=[SimpleNamespace(tabs=[SimpleNamespace(all_sessions=sessions)])], buried_sessions=[])
        self.sdk.async_get_app = app
        result = await self.operate(operation='write_bar', guid='parent-guid', value=AFTER, expected={'exists':True,'value':BEFORE})
        self.assertEqual(result, {'status':'conflict'})
        self.assertEqual(self.writes, [])

    async def test_failure_after_dispatch_is_unknown(self):
        async def set_properties(*args, **kwargs): raise TimeoutError('PRIVATE')
        self.sdk.rpc.async_set_profile_properties_json = set_properties
        result = await self.operate(operation='write_bar', guid='parent-guid', value=AFTER, expected={'exists':True,'value':BEFORE})
        self.assertEqual(result, {'status':'unknown'})
        self.assertNotIn('PRIVATE', repr(result))

    async def test_unchanged_bound_session_after_parent_write_is_not_success(self):
        async def get_profile(): return SimpleNamespace(all_properties={'Guid':'parent-guid', **BEFORE})
        self.sessions = [SimpleNamespace(session_id='session-one', async_get_profile=get_profile)]
        result = await self.operate(operation='write_bar', guid='parent-guid', value=AFTER, expected={'exists':True,'value':BEFORE})
        self.assertEqual(result, {'status':'unknown'})
        self.assertEqual(len(self.writes), 1)

    async def test_foreign_profile_bar_malformed_or_duplicate_names_fails_closed(self):
        self.properties['Show Status Bar'] = 0
        result = await self.operate(operation='inspect')
        self.assertEqual(result, {'status':'conflict'})

    async def test_reference_scan_decodes_json_escaped_guids_in_hidden_fields(self):
        self.properties['hidden'] = '{"parameter":"parent\\u002dguid"}'
        result = await self.operate(operation='inspect')
        self.assertIn('parent-guid', result['value']['profiles'][0]['references'])

    async def test_malformed_request_is_rejected_before_connect(self):
        from unittest.mock import AsyncMock
        connect = AsyncMock()
        self.sdk.Connection.async_create = connect
        result = await self.operate(operation='write_bar', guid='parent-guid', value=None,
                                    expected={'exists':True,'value':BEFORE})
        self.assertEqual(result, {'status':'conflict'})
        connect.assert_not_called()


class WorkerProtocolTests(unittest.TestCase):
    def test_main_only_emits_validated_response_and_discards_sdk_noise(self):
        async def noisy(request):
            print('PRIVATE SDK BODY')
            print('PRIVATE SDK STDERR', file=sys.stderr)
            return {'status':'ok','value':{'exists':True,'value':0}}
        output = io.StringIO()
        with patch.object(profile_api, '_operate', side_effect=noisy), \
                patch.object(sys, 'stdin', io.StringIO('{"operation":"read_position"}')), redirect_stdout(output):
            profile_api.main()
        self.assertEqual(json.loads(output.getvalue()), {'status':'ok','value':{'exists':True,'value':0}})
        self.assertNotIn('PRIVATE', output.getvalue())

    def test_malformed_or_oversized_request_never_reaches_sdk(self):
        for raw in ('PRIVATE MALFORMED', 'x'*1048577):
            with self.subTest(length=len(raw)):
                output = io.StringIO()
                with patch.object(profile_api, '_operate') as operate, \
                        patch.object(sys, 'stdin', io.StringIO(raw)), redirect_stdout(output):
                    profile_api.main()
                self.assertEqual(json.loads(output.getvalue()), {'status':'conflict'})
                operate.assert_not_called()


class NamedReferenceTests(unittest.IsolatedAsyncioTestCase):
    setUp = NativeSdkTests.setUp
    operate = NativeSdkTests.operate

    async def test_dynamic_parent_name_is_resolved_and_unknown_parent_blocks_coverage(self):
        self.properties['Dynamic Profile Parent Name'] = 'Default'
        result = await self.operate(operation='inspect')
        self.assertIn('parent-guid', result['value']['profiles'][0]['references'])
        self.properties['Dynamic Profile Parent Name'] = 'Unknown'
        result = await self.operate(operation='inspect')
        self.assertEqual(result, {'status':'conflict'})


class ReplacementProofTests(unittest.IsolatedAsyncioTestCase):
    setUp = NativeSdkTests.setUp
    operate = NativeSdkTests.operate

    async def test_only_matching_replaced_bar_is_excluded_hidden_and_session_refs_survive(self):
        removed='removed-guid'
        bar=copy.deepcopy(BEFORE)
        bar['Status Bar Layout']['components']=[{'hidden':removed}]
        self.properties.update(bar)
        self.properties['hidden-reference']=removed
        async def get_profile():
            return SimpleNamespace(all_properties={'Guid':'parent-guid',**bar})
        self.sessions=[SimpleNamespace(session_id='s',async_get_profile=get_profile)]
        result=await self.operate(operation='inspect',reference_guids=[removed],
            replaced_bars=[{'guid':'parent-guid','bar':bar}])
        self.assertEqual(result['status'],'ok')
        self.assertIn(removed,result['value']['profiles'][0]['references'])
        self.assertIn(removed,result['value']['sessions'][0]['references'])
        del self.properties['hidden-reference']
        result=await self.operate(operation='inspect',reference_guids=[removed],
            replaced_bars=[{'guid':'parent-guid','bar':bar}])
        self.assertNotIn(removed,result['value']['profiles'][0]['references'])
        self.assertIn(removed,result['value']['sessions'][0]['references'])
        for proof in ([{'guid':'parent-guid','bar':BEFORE}], [{'guid':'absent','bar':bar}],
                      [{'guid':'parent-guid','bar':None}], [{'guid':'parent-guid','bar':bar}]*2):
            result=await self.operate(operation='inspect',reference_guids=[removed],replaced_bars=proof)
            self.assertEqual(result,{'status':'conflict'})


class ReplacementChildTests(unittest.TestCase):
    def test_real_child_protocol_uses_only_fake_sdk_and_checks_replacement_proof(self):
        import os
        from tempfile import TemporaryDirectory
        from iterm2_utils.commands import Runner
        from iterm2_utils.models import Context, Paths
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            # This module shadows the external SDK only in the bounded child.
            (root/'iterm2.py').write_text('''from types import SimpleNamespace
properties={'Guid':'parent-guid','Name':'Default','Show Status Bar':True,
    'Status Bar Layout':{'components':[{'parameter':'removed-guid'}]},
    'hidden':{'parameter':'removed-guid'}}
async def close(): pass
class Connection:
    @staticmethod
    async def async_create(): return SimpleNamespace(websocket=SimpleNamespace(close=close))
class Profile:
    @staticmethod
    async def async_get(connection): return [SimpleNamespace(all_properties=properties)]
    @staticmethod
    async def async_get_default(connection): return SimpleNamespace(guid='parent-guid')
async def async_get_app(connection): return SimpleNamespace(terminal_windows=[],buried_sessions=[])
class preferences:
    class PreferenceKey: STATUS_BAR_POSITION=1
    @staticmethod
    async def async_get_preference(connection,key): return 1
''')
            paths=Paths(root,root/'zshrc',root/'codex',root/'claude.json',root/'config',root/'cache',root/'data',root/'profiles',Path(__file__).resolve().parents[1])
            context=Context(paths,{'python3':Path(sys.executable)},{'python3':'3.11.9'},frozenset(),{}, {})
            proof={'guid':'parent-guid','bar':{'Show Status Bar':True,'Status Bar Layout':{'components':[{'parameter':'removed-guid'}]}}}
            with patch.dict(os.environ,PYTHONPATH=str(root)):
                value=iterm._request(context,Runner(),{'operation':'inspect','reference_guids':['removed-guid'],'replaced_bars':[proof]})
                self.assertIn('removed-guid',value['profiles'][0]['references'])
                with self.assertRaises(ValueError):
                    iterm.ensure_unreferenced({'removed-guid'},{'parent-guid','removed-guid'},context,Runner(),replaced_bars=[proof])
                proof['bar']['Show Status Bar']=False
                with self.assertRaises(ValueError):
                    iterm._request(context,Runner(),{'operation':'inspect','reference_guids':['removed-guid'],'replaced_bars':[proof]})
