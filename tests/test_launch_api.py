"""SDK fixtures run in a private HOME and never contact iTerm2."""
import asyncio
from contextlib import redirect_stdout
import io
from dataclasses import FrozenInstanceError
import importlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from iterm2_utils import launch_api


SDK = r'''
import asyncio, json, os, time
from pathlib import Path
from types import SimpleNamespace
SCENARIO = SCENARIO_VALUE
LOG = Path(os.environ['FAKE_SDK_LOG'])
LAST_PROFILE = None
def record(kind, value=None):
    with LOG.open('a') as stream: stream.write(json.dumps([kind, value])+'\n')
print('PRIVATE_SDK_DIAGNOSTIC')
if SCENARIO == 'import_error': raise ImportError('PRIVATE_SDK_DETAIL')
class Socket:
    async def close(self):
        record('close')
        if LAST_PROFILE is not None:
            record('profile_state', [LAST_PROFILE.name, LAST_PROFILE.guid, LAST_PROFILE.command])
class Connection:
    websocket = Socket()
    @staticmethod
    async def async_create():
        if SCENARIO == 'sync_auth': time.sleep(60)
        if SCENARIO == 'system_exit': raise SystemExit('PRIVATE_SDK_DETAIL')
        if SCENARIO == 'connect_denied': raise PermissionError('PRIVATE_SDK_DETAIL')
        if SCENARIO == 'connect_timeout': await asyncio.sleep(60)
        return Connection()
class Profile:
    name = 'Codex fixture'
    guid = 'profile-one'
    command = 'codex PROFILE_DEFAULT'
    @staticmethod
    async def async_get(connection):
        global LAST_PROFILE
        if SCENARIO == 'profile_timeout': await asyncio.sleep(60)
        p = Profile()
        LAST_PROFILE = p
        if SCENARIO == 'guid_changed': p.guid = 'another-guid'
        if SCENARIO == 'name_changed': p.name = 'another-name'
        return [p, p] if SCENARIO == 'duplicate_profile' else [p]
class Tab:
    tab_id = 'T-created'
    @property
    def all_sessions(self):
        if SCENARIO == 'partial': raise ConnectionError('PRIVATE_SDK_DETAIL')
        return [SimpleNamespace(session_id='S-created')]
class Window:
    window_id = 'W-explicit'
    async def async_create_tab(self, profile=None, command=None, select=True):
        record('create', [self.window_id, profile, command, select])
        record('profile_command', Profile.command)
        if SCENARIO == 'create_pending': await asyncio.sleep(60)
        if SCENARIO == 'disconnect': raise ConnectionError('PRIVATE_SDK_DETAIL')
        if SCENARIO == 'create_timeout': raise TimeoutError('PRIVATE_SDK_DETAIL')
        if SCENARIO == 'malformed': return None
        return Tab()
    async def async_send_text(self, text): record('send', text)
    async def async_close(self): record('cleanup_tab')
class App:
    current_terminal_window = SimpleNamespace(window_id='W-now-active')
    def get_window_by_id(self, window_id):
        record('lookup', window_id)
        return None if SCENARIO == 'window_gone' else Window()
async def async_get_app(connection):
    if SCENARIO == 'app_timeout': await asyncio.sleep(60)
    return App()
if SCENARIO == 'missing_api': del Profile
'''


class LaunchAPITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root/'sdk.jsonl'

    async def run_sdk(self, scenario='ok', timeout=None):
        (self.root/'iterm2.py').write_text(SDK.replace('SCENARIO_VALUE', repr(scenario)))
        environment = {'HOME': str(self.root), 'PYTHONPATH': str(self.root),
                       'FAKE_SDK_LOG': str(self.log), 'PYTHONDONTWRITEBYTECODE': '1'}
        with patch.dict(os.environ, environment), patch.object(launch_api, '_PREFLIGHT_SECONDS', timeout or 10):
            return await launch_api.create_tab('W-explicit', 'Codex fixture', 'profile-one', 'CUSTOM_COMMAND')

    def calls(self, kind):
        rows = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return [value for key, value in rows if key == kind]

    async def test_custom_command_overrides_profile_at_creation(self):
        result = await self.run_sdk()
        self.assertEqual(result.status, 'created_unverified')
        self.assertEqual((result.window_id, result.tab_id, result.session_id),
                         ('W-explicit', 'T-created', 'S-created'))
        self.assertEqual(self.calls('create'), [['W-explicit', 'Codex fixture', 'CUSTOM_COMMAND', True]])
        self.assertEqual(self.calls('profile_command'), ['codex PROFILE_DEFAULT'])
        self.assertEqual(self.calls('profile_state'), [['Codex fixture', 'profile-one', 'codex PROFILE_DEFAULT']])
        self.assertEqual(self.calls('send'), [])
        self.assertEqual(self.calls('cleanup_tab'), [])
        self.assertEqual(self.calls('close'), [None])
        self.assertGreater(result.deadline, time.monotonic())
        with self.assertRaises(FrozenInstanceError): result.status = 'launched'

    async def test_missing_sdk_api_or_permission_blocks(self):
        for scenario in ('import_error', 'missing_api', 'connect_denied', 'system_exit', 'connect_timeout',
                         'app_timeout', 'profile_timeout', 'sync_auth'):
            with self.subTest(scenario=scenario):
                self.log.unlink(missing_ok=True)
                started = time.monotonic()
                result = await self.run_sdk(scenario, timeout=.25)
                self.assertEqual(result.status, 'blocked')
                self.assertIsNone(result.deadline)
                self.assertEqual(self.calls('create'), [])
                self.assertLess(time.monotonic()-started, 2)
                self.assertNotIn('PRIVATE', repr(result))

    async def test_target_changes_before_create(self):
        for scenario in ('window_gone', 'guid_changed', 'name_changed', 'duplicate_profile'):
            with self.subTest(scenario=scenario):
                self.log.unlink(missing_ok=True)
                result = await self.run_sdk(scenario)
                self.assertEqual(result.status, 'blocked')
                self.assertEqual(self.calls('create'), [])
        self.log.unlink(missing_ok=True)
        result = await self.run_sdk('active_changed')
        self.assertEqual(result.window_id, 'W-explicit')
        self.assertEqual(self.calls('lookup'), ['W-explicit'])

    async def test_disconnect_after_create_never_retries(self):
        for scenario in ('disconnect', 'create_timeout', 'malformed'):
            with self.subTest(scenario=scenario):
                self.log.unlink(missing_ok=True)
                result = await self.run_sdk(scenario)
                self.assertEqual(result.status, 'unknown')
                self.assertEqual(result.window_id, 'W-explicit')
                self.assertIsNotNone(result.deadline)
                self.assertEqual(len(self.calls('create')), 1)
                self.assertEqual(self.calls('cleanup_tab'), [])
                self.assertEqual(self.calls('close'), [None])

    async def test_partial_create_preserves_ids(self):
        result = await self.run_sdk('partial')
        self.assertEqual(result.status, 'unknown')
        self.assertEqual((result.window_id, result.tab_id, result.session_id), ('W-explicit', 'T-created', None))
        self.assertEqual(len(self.calls('create')), 1)

    async def test_creation_deadline_is_thirty_seconds_from_send(self):
        frames = []
        fake_sdk = importlib.util.module_from_spec(importlib.machinery.ModuleSpec('iterm2', None))
        with patch.dict(os.environ, {'FAKE_SDK_LOG': str(self.log)}):
            with redirect_stdout(io.StringIO()):
                exec(SDK.replace('SCENARIO_VALUE', repr('ok')), fake_sdk.__dict__)
        with patch.dict(sys.modules, {'iterm2': fake_sdk}), patch.object(launch_api.time, 'monotonic', return_value=123.0):
            await launch_api._operate(dict(window_id='W-explicit', profile='Codex fixture',
                                          profile_guid='profile-one', command='CUSTOM_COMMAND'), frames.append)
        self.assertIn({'phase': 'create', 'window_id': 'W-explicit', 'deadline': 153.0}, frames)

    async def test_expired_worker_budget_never_calls_create(self):
        frames = []
        fake_sdk = importlib.util.module_from_spec(importlib.machinery.ModuleSpec('iterm2', None))
        with patch.dict(os.environ, {'FAKE_SDK_LOG': str(self.log)}), redirect_stdout(io.StringIO()):
            exec(SDK.replace('SCENARIO_VALUE', repr('ok')), fake_sdk.__dict__)
        ticks = iter((123.0, 154.0))
        with patch.dict(sys.modules, {'iterm2': fake_sdk}), \
                patch.object(launch_api, 'time', SimpleNamespace(monotonic=lambda: next(ticks))):
            status = await launch_api._operate(dict(window_id='W-explicit', profile='Codex fixture',
                profile_guid='profile-one', command='CUSTOM_COMMAND'), frames.append)
        self.assertEqual(status, 'blocked')
        self.assertEqual(self.calls('create'), [])

    async def test_worker_rejects_malformed_oversized_or_repeated_progress(self):
        cases = ["print('not json')", "print('x'*5000)",
                 "print('{\"phase\":\"connect\"}'); print('{\"phase\":\"connect\"}')"]
        real_spawn = asyncio.create_subprocess_exec
        for script in cases:
            with self.subTest(script=script):
                async def spawn(*args, **kwargs):
                    return await real_spawn(sys.executable, '-c', script, **kwargs)
                with patch.object(launch_api.asyncio, 'create_subprocess_exec', side_effect=spawn):
                    result = await launch_api.create_tab('W-explicit', 'Codex fixture', 'profile-one', 'CUSTOM_COMMAND')
                self.assertEqual(result.status, 'blocked')
                self.assertNotIn('not json', repr(result))

    async def test_worker_request_delivery_is_bounded(self):
        real_spawn = asyncio.create_subprocess_exec
        async def spawn(*args, **kwargs):
            return await real_spawn(sys.executable, '-c', 'import time; time.sleep(60)', **kwargs)
        started = time.monotonic()
        with patch.object(launch_api.asyncio, 'create_subprocess_exec', side_effect=spawn), \
                patch.object(launch_api, '_PREFLIGHT_SECONDS', .1):
            async with asyncio.timeout(.6):
                result = await launch_api.create_tab('W-explicit', 'Codex fixture', 'profile-one', 'x'*1000000)
        self.assertEqual(result.status, 'blocked')
        self.assertLess(time.monotonic()-started, .4)

    async def test_no_ack_means_no_sdk_create(self):
        (self.root/'iterm2.py').write_text(SDK.replace('SCENARIO_VALUE', repr('ok')))
        environment = dict(os.environ, HOME=str(self.root), PYTHONPATH=str(self.root),
                           FAKE_SDK_LOG=str(self.log), PYTHONDONTWRITEBYTECODE='1')
        child = await asyncio.create_subprocess_exec(sys.executable, '-m', 'iterm2_utils.launch_api',
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env=environment)
        try:
            request = dict(window_id='W-explicit', profile='Codex fixture',
                           profile_guid='profile-one', command='CUSTOM_COMMAND')
            child.stdin.write(json.dumps(request).encode()+b'\n')
            await child.stdin.drain()
            async with asyncio.timeout(2):
                frames = [json.loads(await child.stdout.readline()) for _ in range(4)]
                self.assertEqual(frames[-1]['phase'], 'create')
                self.assertEqual(self.calls('create'), [])
                child.stdin.close()
                self.assertEqual(json.loads(await child.stdout.readline()), {'result': 'blocked'})
                self.assertEqual(await child.wait(), 0)
            self.assertEqual(self.calls('create'), [])
            self.assertEqual(self.calls('close'), [None])
        finally:
            if child.returncode is None:
                child.kill()
                await child.wait()

    async def test_cancellation_after_ack_preserves_uncertainty(self):
        task = asyncio.create_task(self.run_sdk('create_pending'))
        try:
            async with asyncio.timeout(2):
                while not self.calls('create'):
                    await asyncio.sleep(.01)
            task.cancel()
            result = await task
            self.assertEqual(result.status, 'unknown')
            self.assertEqual(result.window_id, 'W-explicit')
            self.assertEqual(len(self.calls('create')), 1)
            self.assertEqual(self.calls('cleanup_tab'), [])
        finally:
            if not task.done():
                task.cancel()
                await task

    async def test_expired_create_deadline_is_not_acknowledged(self):
        real_spawn = asyncio.create_subprocess_exec
        script = r'''import json, sys, time
sys.stdin.readline()
for phase in ('connect', 'app', 'profiles'):
    print(json.dumps({'phase': phase}), flush=True)
print(json.dumps({'phase': 'create', 'window_id': 'W-explicit', 'deadline': time.monotonic()-1}), flush=True)
assert sys.stdin.readline() == ''
'''
        async def spawn(*args, **kwargs):
            return await real_spawn(sys.executable, '-c', script, **kwargs)
        with patch.object(launch_api.asyncio, 'create_subprocess_exec', side_effect=spawn):
            result = await launch_api.create_tab('W-explicit', 'Codex fixture', 'profile-one', 'CUSTOM_COMMAND')
        self.assertEqual(result.status, 'blocked')
        self.assertIsNone(result.deadline)
        self.assertIsNone(result.tab_id)

    async def test_malformed_create_frame_is_not_acknowledged(self):
        real_spawn = asyncio.create_subprocess_exec
        writes = []

        class CaptureInput:
            def __init__(self, writer):
                self.writer = writer

            def write(self, data):
                writes.append(data)
                self.writer.write(data)

            def __getattr__(self, name):
                return getattr(self.writer, name)

        for frame in ({'phase': 'create', 'window_id': 'W-other', 'deadline': time.monotonic()+30},
                      {'phase': 'create', 'window_id': 'W-explicit', 'deadline': 'invalid'}):
            with self.subTest(frame=frame):
                writes.clear()
                script = "import json, sys\nsys.stdin.readline()\n"
                script += "for phase in ('connect', 'app', 'profiles'):\n    print(json.dumps({'phase': phase}), flush=True)\n"
                script += 'print('+repr(json.dumps(frame))+', flush=True)\nsys.stdin.readline()\n'

                async def spawn(*args, **kwargs):
                    child = await real_spawn(sys.executable, '-c', script, **kwargs)
                    child.stdin = CaptureInput(child.stdin)
                    return child

                with patch.object(launch_api.asyncio, 'create_subprocess_exec', side_effect=spawn):
                    result = await launch_api.create_tab('W-explicit', 'Codex fixture', 'profile-one', 'CUSTOM_COMMAND')
                self.assertEqual(result.status, 'blocked')
                self.assertIsNone(result.deadline)
                self.assertNotIn(b'create\n', writes)

    async def test_malformed_output_after_ack_preserves_tab_id(self):
        real_spawn = asyncio.create_subprocess_exec
        script = r'''import json, sys, time
sys.stdin.readline()
for phase in ('connect', 'app', 'profiles'):
    print(json.dumps({'phase': phase}), flush=True)
print(json.dumps({'phase': 'create', 'window_id': 'W-explicit', 'deadline': time.monotonic()+30}), flush=True)
assert sys.stdin.readline() == 'create\n'
print(json.dumps({'tab_id': 'T-known'}), flush=True)
print('x'*5000, flush=True)
'''
        async def spawn(*args, **kwargs):
            return await real_spawn(sys.executable, '-c', script, **kwargs)
        with patch.object(launch_api.asyncio, 'create_subprocess_exec', side_effect=spawn):
            result = await launch_api.create_tab('W-explicit', 'Codex fixture', 'profile-one', 'CUSTOM_COMMAND')
        self.assertEqual(result.status, 'unknown')
        self.assertEqual((result.window_id, result.tab_id, result.session_id), ('W-explicit', 'T-known', None))

    def test_module_import_does_not_require_sdk(self):
        with patch.dict(sys.modules, {'iterm2': None}):
            importlib.reload(launch_api)


if __name__ == '__main__':
    unittest.main()
