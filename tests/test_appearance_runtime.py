import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import signal
import select
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from runtime import appearance


UUID = '12345678-1234-1234-1234-123456789ABC'
ENV = {'ITERM_SESSION_ID': 'w0t1p0:' + UUID}


class AppearanceEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.config = self.repo / 'appearance.json'
        self.config.write_text(json.dumps({'projects': [
            {'root': str(self.repo), 'color': '#65A85A', 'icon': 'android-mail'}]}))

    def test_public_entrypoints_exist(self):
        self.assertTrue(callable(getattr(appearance, 'apply', None)))
        self.assertTrue(callable(getattr(appearance, 'probe', None)))

    def test_bad_or_conflicting_ids_do_not_start_worker(self):
        with patch.object(appearance, '_supervise') as worker:
            for env in ({}, {'ITERM_SESSION_ID': 'active'},
                        {**ENV, 'TERM_SESSION_ID': '00000000-0000-0000-0000-000000000000'}):
                self.assertEqual(appearance.apply(self.config, self.repo, 'shell', environment=env), 'ignored')
            worker.assert_not_called()

    def test_tmux_rejects_inherited_session_before_apply_or_probe(self):
        env = {**ENV, 'TERM_SESSION_ID': UUID, 'TMUX': '/fixture/tmux,42,0'}
        for call, expected in ((lambda: appearance.apply(self.config, self.repo, 'launch', environment=env), 'ignored'),
                               (lambda: appearance.probe(environment=env), 'unavailable')):
            with self.subTest(expected=expected), patch.object(appearance, '_supervise', return_value='wrong-session-worker') as worker:
                self.assertEqual(call(), expected)
                worker.assert_not_called()

    def test_absent_or_empty_tmux_keeps_explicit_session_available(self):
        for env in (ENV, {**ENV, 'TMUX': ''}):
            with self.subTest(env=env), patch.object(appearance, '_supervise', return_value='applied'):
                self.assertEqual(appearance.apply(self.config, self.repo, 'shell', environment=env), 'applied')
            with patch.object(appearance, '_supervise', return_value='ready'):
                self.assertEqual(appearance.probe(environment=env), 'ready')

    def test_invalid_readiness_and_launch_identity_do_not_start_worker(self):
        for arguments in ({'ready_fd': 0}, {'ready_fd': '3'}, {'launch_id': '../foreign'},
                          {'launch_id': '42-1\nprivate'}, {'launch_id': 1}):
            with self.subTest(arguments=arguments), patch.object(appearance, '_supervise') as worker:
                self.assertEqual(appearance.apply(self.config, self.repo, 'launch', environment=ENV, **arguments), 'unavailable')
                worker.assert_not_called()

    def test_no_match_does_not_connect(self):
        with patch.object(appearance, '_supervise', side_effect=lambda request, env: appearance._run_request(request)), \
             patch.object(appearance, '_API') as api:
            self.assertEqual(appearance.apply(self.config, Path('/'), 'shell', environment=ENV), 'ignored')
            api.assert_not_called()

    def test_no_match_launch_and_return_reach_preservation_observer(self):
        with patch.object(appearance, '_supervise', side_effect=lambda request, env: appearance._run_request(request)), \
             patch.object(appearance, '_operate', new=AsyncMock(return_value='applied')) as operation:
            for phase in ('launch', 'return'):
                self.assertEqual(appearance.apply(self.config, Path('/'), phase, environment=ENV), 'applied')
                self.assertTrue(operation.call_args.args[0]['preserve'])

    def test_valid_rule_passes_explicit_uuid_and_builtin_path(self):
        with patch.object(appearance, '_supervise', side_effect=lambda request, env: appearance._run_request(request)), \
             patch.object(appearance, '_operate', new=AsyncMock(return_value='applied')) as operation:
            self.assertEqual(appearance.apply(self.config, self.repo, 'shell', environment=ENV), 'applied')
        request = operation.call_args.args[0]
        self.assertEqual(request['terminal'], UUID)
        self.assertEqual(request['icon'], str(Path(appearance.__file__).parent / 'assets/appearance/android-mail.png'))

    def test_filesystem_work_is_inside_supervised_worker(self):
        with patch.object(appearance, '_supervise', return_value='timeout') as worker, \
             patch.object(appearance, 'load_rules') as load:
            self.assertEqual(appearance.apply(self.config, self.repo, 'shell', environment=ENV), 'timeout')
        load.assert_not_called()
        self.assertEqual(worker.call_args.args, ({'terminal': UUID, 'phase': 'shell',
                         'config': str(self.config), 'cwd': str(self.repo)}, ENV))

    def test_missing_custom_icon_is_unavailable_without_connecting(self):
        self.config.write_text(json.dumps({'projects': [
            {'root': str(self.repo), 'color': '#65A85A', 'icon': str(self.repo / 'lost.png')}]}))
        with patch.object(appearance, '_supervise', side_effect=lambda request, env: appearance._run_request(request)), \
             patch.object(appearance, '_API') as api:
            self.assertEqual(appearance.apply(self.config, self.repo, 'shell', environment=ENV), 'unavailable')
            api.assert_not_called()

    def test_custom_icon_and_probe(self):
        icon = self.repo / 'custom.png'
        icon.write_bytes(b'png')
        self.config.write_text(json.dumps({'projects': [
            {'root': str(self.repo), 'color': '#65A85A', 'icon': str(icon)}]}))
        with patch.object(appearance, '_supervise', side_effect=lambda request, env: appearance._run_request(request)), \
             patch.object(appearance, '_operate', new=AsyncMock(return_value='applied')) as operation:
            appearance.apply(self.config, self.repo, 'return', environment=ENV)
            self.assertEqual(operation.call_args.args[0]['icon'], str(icon))
        with patch.object(appearance, '_supervise', return_value='ready') as worker:
            self.assertEqual(appearance.probe(environment=ENV), 'ready')
            self.assertEqual(worker.call_args.args[0], {'terminal': UUID, 'phase': 'probe'})

    def test_invalid_config_and_phase_are_quiet_unavailable(self):
        self.config.write_text('private invalid contents')
        self.assertEqual(appearance.apply(self.config, self.repo, 'shell', environment=ENV), 'unavailable')
        self.assertEqual(appearance.apply(self.config, self.repo, 'other', environment=ENV), 'unavailable')

    def test_cli_invalid_input_has_only_status(self):
        result = subprocess.run([sys.executable, appearance.__file__, '--config', str(self.config),
                                 '--cwd', str(self.repo), '--phase', 'shell'],
                                env={}, capture_output=True, text=True, check=False)
        self.assertEqual(result.stdout, 'ignored\n')
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.returncode, 0)

    def test_cli_rejects_arguments_without_leaking_them(self):
        result = subprocess.run([sys.executable, appearance.__file__, '--secret-fixture=/private/path'],
                                env={}, capture_output=True, text=True, check=False)
        self.assertEqual((result.stdout, result.stderr, result.returncode), ('unavailable\n', '', 0))


class FakeAPI:
    def __init__(self):
        self.session = object()
        self.connect = AsyncMock()
        self.find = AsyncMock(return_value=self.session)
        self.write = AsyncMock()
        self.close = AsyncMock()
        self.job = 'zsh'
        self.events = asyncio.Queue()
        self.watching = False
        self.current = {'Tab Color': {'Red Component': .4}, 'Use Tab Color': True,
                        'Custom Icon Path': '/fixture/manual.png', 'Icon': 2}
        self.saved = None
        self.snapshot = AsyncMock(side_effect=lambda session: dict(self.current))
        self.save_snapshot = AsyncMock(side_effect=self._save_snapshot)
        self.take_snapshot = AsyncMock(side_effect=self._take_snapshot)
        self.clear_snapshot = AsyncMock(side_effect=self._clear_snapshot)
        self.restore = AsyncMock(side_effect=self._restore)

    async def _save_snapshot(self, session, properties, launch_id=None):
        self.saved = (launch_id, None if properties is None else dict(properties))

    async def _take_snapshot(self, session, launch_id=None):
        if self.saved is None or self.saved[0] != launch_id:
            return None
        return self.saved[1]

    async def _clear_snapshot(self, session, launch_id=None):
        if self.saved is not None and self.saved[0] == launch_id:
            self.saved = None

    async def _restore(self, session, properties, launch_id=None):
        if self.saved is None or self.saved[0] != launch_id:
            return False
        self.current = dict(properties)
        return True

    async def job_name(self, session):
        return self.job

    @asynccontextmanager
    async def watch(self, terminal):
        self.watching = True
        try:
            yield self.events
        finally:
            self.watching = False


class AppearanceOperationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = FakeAPI()
        self.request = {'terminal': UUID, 'phase': 'shell', 'color': '#65A85A', 'icon': '/fixture/a.png'}
        self.factory = patch.object(appearance, '_API', return_value=self.api)
        self.factory.start()
        self.addCleanup(self.factory.stop)

    async def test_explicit_session_only_and_cleanup(self):
        self.assertEqual(await appearance._operate(self.request), 'applied')
        self.api.find.assert_awaited_once_with(UUID)
        self.api.write.assert_awaited_once_with(self.api.session, '#65A85A', '/fixture/a.png')
        self.api.close.assert_awaited_once()

    async def test_probe_never_writes(self):
        self.request['phase'] = 'probe'
        self.assertEqual(await appearance._operate(self.request), 'ready')
        self.api.write.assert_not_called()

    async def test_missing_session_and_denial(self):
        self.api.find.return_value = None
        self.assertEqual(await appearance._operate(self.request), 'unavailable')
        self.api.write.assert_not_called()
        self.api.find.return_value = self.api.session
        self.api.write.side_effect = RuntimeError('private details')
        self.assertEqual(await appearance._operate(self.request), 'unavailable')
        self.assertEqual(self.api.close.await_count, 2)

    async def test_absent_sdk_is_unavailable(self):
        with patch.object(appearance, '_API', side_effect=ImportError):
            self.assertEqual(await appearance._operate(self.request), 'unavailable')

    async def test_connect_deadline_and_cleanup(self):
        async def blocked():
            await asyncio.Future()
        self.api.connect.side_effect = blocked
        with patch.object(appearance, '_API_TIMEOUT', 0.01):
            self.assertEqual(await appearance._operate(self.request), 'timeout')
        self.api.close.assert_awaited_once()

    async def run_event_case(self, phase, initial_job, events):
        self.request['phase'] = phase
        self.api.job = initial_job
        async def drive():
            while not self.api.watching:
                await asyncio.sleep(0)
            for job in events:
                self.api.job = job
                await self.api.events.put(None)
                # Wait for the event handler to observe the current job.
                await asyncio.sleep(0)
                await asyncio.sleep(0)
        driver = asyncio.create_task(drive())
        with patch.object(appearance, '_WATCH_SECONDS', 0.02):
            result = await appearance._operate(self.request)
        await driver
        self.assertFalse(self.api.watching)
        self.api.close.assert_awaited_once()
        return result

    async def test_launch_reapplies_after_aps_profile_change(self):
        self.assertEqual(await self.run_event_case('launch', 'zsh', ['codex']), 'applied')
        self.assertEqual(self.api.write.await_count, 2)

    async def test_return_observes_shell_aps_reversal(self):
        self.assertEqual(await self.run_event_case('return', 'codex', ['zsh', 'zsh']), 'applied')
        self.assertEqual(self.api.write.await_count, 2)

    async def test_early_exit_stale_event_does_not_write(self):
        self.assertEqual(await self.run_event_case('launch', 'zsh', ['zsh']), 'applied')
        self.assertEqual(self.api.write.await_count, 1)

    async def test_no_match_preserves_manual_snapshot_across_launch_and_return(self):
        expected = dict(self.api.current)
        self.request = {'terminal': UUID, 'phase': 'launch', 'preserve': True}
        async def launch():
            while self.api.saved is None:
                await asyncio.sleep(0)
            self.api.current = {'Use Tab Color': False, 'Custom Icon Path': ''}
            self.api.job = 'codex'
            await self.api.events.put(None)
        driver = asyncio.create_task(launch())
        try:
            with patch.object(appearance, '_WATCH_SECONDS', .02):
                self.assertEqual(await appearance._operate(self.request), 'applied')
            await driver
            self.assertEqual(self.api.current, expected)
            self.api.current = {'Use Tab Color': False, 'Custom Icon Path': ''}
            self.api.job = 'zsh'
            with patch.object(appearance, '_WATCH_SECONDS', .02):
                self.assertEqual(await appearance._operate({**self.request, 'phase': 'return'}), 'applied')
            self.assertEqual(self.api.current, expected)
            self.assertIsNone(self.api.saved)
            self.api.write.assert_not_called()
        finally:
            driver.cancel()
            await asyncio.gather(driver, return_exceptions=True)

    async def test_no_match_without_transition_does_not_reassign_manual_style(self):
        expected = dict(self.api.current)
        self.request = {'terminal': UUID, 'phase': 'launch', 'preserve': True}
        with patch.object(appearance, '_WATCH_SECONDS', .01):
            self.assertEqual(await appearance._operate(self.request), 'ignored')
        self.assertEqual(self.api.current, expected)
        self.api.restore.assert_not_called()

    async def test_no_match_return_without_snapshot_leaves_session_untouched(self):
        self.request = {'terminal': UUID, 'phase': 'return', 'preserve': True}
        self.assertEqual(await appearance._operate(self.request), 'ignored')
        self.api.restore.assert_not_called()

    async def test_failed_new_launch_cannot_restore_an_older_snapshot(self):
        request = {'terminal': UUID, 'phase': 'launch', 'preserve': True, 'launch_id': '42-1'}
        with patch.object(appearance, '_WATCH_SECONDS', .001):
            await appearance._operate(request)
            self.api.current = {'Use Tab Color': False, 'Custom Icon Path': '/fixture/new-manual.png'}
            self.assertEqual(await appearance._operate({**request, 'phase': 'return', 'launch_id': '42-2'}), 'ignored')
        self.assertEqual(self.api.current, {'Use Tab Color': False, 'Custom Icon Path': '/fixture/new-manual.png'})

    async def test_newer_snapshot_or_matched_claim_after_read_blocks_old_return(self):
        old_properties = dict(self.api.current)
        newer_properties = {'Use Tab Color': False, 'Custom Icon Path': '/fixture/newer.png'}
        for snapshot in (newer_properties, None):
            with self.subTest(snapshot=snapshot):
                self.api.saved = ('42-1', old_properties)
                async def take_then_replace(session, launch_id):
                    properties = await self.api._take_snapshot(session, launch_id)
                    self.api.saved = ('43-1', snapshot)
                    self.api.current = dict(newer_properties)
                    return properties
                self.api.take_snapshot.side_effect = take_then_replace
                request = {'terminal': UUID, 'phase': 'return', 'preserve': True, 'launch_id': '42-1'}
                with patch.object(appearance, '_WATCH_SECONDS', .001):
                    self.assertEqual(await appearance._operate(request), 'ignored')
                self.assertEqual(self.api.current, newer_properties)
                self.assertEqual(self.api.saved, ('43-1', snapshot))

    async def test_matched_launch_claims_before_write_and_return_clears_its_claim(self):
        self.api.saved = ('42-1', dict(self.api.current))
        ownership_at_write = []
        self.api.write.side_effect = lambda *args: ownership_at_write.append(self.api.saved)
        request = {**self.request, 'phase': 'launch', 'launch_id': '43-1'}
        with patch.object(appearance, '_WATCH_SECONDS', .001):
            self.assertEqual(await appearance._operate(request), 'applied')
            self.assertEqual(ownership_at_write, [('43-1', None)])
            self.assertEqual(await appearance._operate({**request, 'phase': 'return'}), 'applied')
        self.api.save_snapshot.assert_awaited_once_with(self.api.session, None, '43-1')
        self.assertIsNone(self.api.saved)

    async def test_cancelled_return_clears_only_its_reserved_snapshot(self):
        self.api.saved = ('42-1', dict(self.api.current))
        self.api.job = 'codex'
        request = {'terminal': UUID, 'phase': 'return', 'preserve': True, 'launch_id': '42-1'}
        observer = asyncio.create_task(appearance._operate(request))
        try:
            while not self.api.take_snapshot.await_count:
                await asyncio.sleep(0)
            self.assertIsNotNone(self.api.saved)
        finally:
            observer.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await observer
        self.api.clear_snapshot.assert_awaited_once_with(self.api.session, '42-1')
        self.assertIsNone(self.api.saved)
        self.assertFalse(self.api.watching)
        self.api.close.assert_awaited_once()

    async def test_relaunch_cancels_old_observer_before_new_write(self):
        self.request['phase'] = 'launch'
        old = asyncio.create_task(appearance._operate(self.request))
        while not self.api.watching:
            await asyncio.sleep(0)
        old.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await old
        self.assertFalse(self.api.watching)
        writes = self.api.write.await_count
        self.api.job = 'codex'
        await self.api.events.put(None)
        await asyncio.sleep(0)
        self.assertEqual(self.api.write.await_count, writes)
        self.api.close.assert_awaited_once()
        newer = FakeAPI()
        with patch.object(appearance, '_API', return_value=newer):
            self.assertEqual(await appearance._operate({**self.request, 'phase': 'shell', 'color': '#112233'}), 'applied')
        newer.write.assert_awaited_once_with(newer.session, '#112233', '/fixture/a.png')
        self.assertEqual(self.api.write.await_count, writes)


class SnapshotSession:
    """Model another connection replacing state before a read reply arrives."""

    def __init__(self, record):
        self.record = record
        self.current = record['properties']
        self.replacement_after_read = None
        self.deferred_replacement = None
        self.in_transaction = False

    def replace(self, record):
        if self.in_transaction:
            self.deferred_replacement = record
        else:
            self.record = record
            if record['properties'] is not None:
                self.current = record['properties']

    @asynccontextmanager
    async def transaction(self, connection):
        self.in_transaction = True
        try:
            yield
        finally:
            self.in_transaction = False
            if self.deferred_replacement is not None:
                self.replace(self.deferred_replacement)
                self.deferred_replacement = None

    async def async_get_variable(self, name):
        value = json.dumps(self.record)
        if self.replacement_after_read is not None:
            self.replace(self.replacement_after_read)
            self.replacement_after_read = None
        return value

    async def async_set_variable(self, name, value):
        self.record = None if value is None else json.loads(value)

    async def async_set_profile_properties(self, profile):
        self.current = profile


class NativeAdapterTests(unittest.IsolatedAsyncioTestCase):
    def snapshot_fixture(self):
        properties = {key: None for key in appearance._APPEARANCE_KEYS}
        record = {'launch_id': '42-1', 'properties': properties}
        newer = {'launch_id': '43-1', 'properties': {**properties, 'Custom Icon Path': '/fixture/newer.png'}}
        session = SnapshotSession(record)
        sdk = Mock(Transaction=session.transaction, LocalWriteOnlyProfile=lambda value: dict(value))
        with patch.dict(sys.modules, {'iterm2': sdk}):
            api = appearance._API()
        return api, session, record, newer

    async def test_read_reply_cannot_clear_a_newer_snapshot(self):
        api, session, record, newer = self.snapshot_fixture()
        session.replacement_after_read = newer
        self.assertEqual(await api.take_snapshot(session, '42-1'), record['properties'])
        self.assertEqual(session.record, newer)

    async def test_cached_restore_rejects_newer_snapshot_and_matched_claim(self):
        for marker in (False, True):
            with self.subTest(marker=marker):
                api, session, record, newer = self.snapshot_fixture()
                properties = await api.take_snapshot(session, '42-1')
                session.replace(newer)
                if marker:
                    session.record = {**newer, 'properties': None}
                self.assertFalse(await api.restore(session, properties, '42-1'))
                self.assertEqual(session.current, newer['properties'])
                self.assertEqual(session.record['launch_id'], '43-1')

    async def test_restore_check_and_write_cannot_overwrite_a_queued_new_launch(self):
        api, session, record, newer = self.snapshot_fixture()
        session.replacement_after_read = newer
        self.assertTrue(await api.restore(session, record['properties'], '42-1'))
        self.assertEqual(session.record, newer)
        self.assertEqual(session.current, newer['properties'])
        self.assertFalse(session.in_transaction)

    async def test_clear_check_and_write_cannot_erase_a_queued_new_launch(self):
        api, session, record, newer = self.snapshot_fixture()
        session.replacement_after_read = newer
        await api.clear_snapshot(session, '42-1')
        self.assertEqual(session.record, newer)
        self.assertFalse(session.in_transaction)

    async def test_clear_preserves_newer_record_and_removes_own_matched_claim(self):
        api, session, record, newer = self.snapshot_fixture()
        session.replace(newer)
        await api.clear_snapshot(session, '42-1')
        self.assertEqual(session.record, newer)
        session.record = {**record, 'properties': None}
        await api.clear_snapshot(session, '42-1')
        self.assertIsNone(session.record)

    async def test_snapshot_roundtrip_is_session_local_and_allowlisted(self):
        keys = ('Tab Color', 'Tab Color (Light)', 'Tab Color (Dark)', 'Use Tab Color',
                'Use Tab Color (Light)', 'Use Tab Color (Dark)', 'Icon', 'Custom Icon Path')
        expected = dict(zip(keys, ({'Red Component': .4}, None, {'Red Component': .9},
                                  True, None, False, 2, '/fixture/manual.png')))
        values = {key: json.dumps(value) for key, value in {**expected, 'Name': 'do not restore'}.items()}
        sdk = Mock()
        sdk.Transaction.return_value = AsyncMock()
        record = {'launch_id': '42-1', 'properties': expected}
        session = Mock(async_get_profile=AsyncMock(return_value=Mock(local_write_only_copy=Mock(values=values))),
                       async_get_variable=AsyncMock(return_value=json.dumps(record)),
                       async_set_variable=AsyncMock(), async_set_profile_properties=AsyncMock())
        with patch.dict(sys.modules, {'iterm2': sdk}):
            api = appearance._API()
        snapshot = await api.snapshot(session)
        self.assertEqual(snapshot, expected)
        await api.save_snapshot(session, snapshot, '42-1')
        saved = session.async_set_variable.call_args
        self.assertTrue(saved.args[0].startswith('user.'))
        self.assertEqual(json.loads(saved.args[1]), record)
        self.assertEqual(await api.take_snapshot(session, '42-1'), expected)
        self.assertEqual(session.async_set_variable.await_count, 1)
        self.assertTrue(await api.restore(session, snapshot, '42-1'))
        sdk.LocalWriteOnlyProfile.assert_called_once_with(expected)
        session.async_set_profile_properties.assert_awaited_once_with(sdk.LocalWriteOnlyProfile.return_value)
        await api.clear_snapshot(session, '42-1')
        session.async_set_variable.assert_awaited_with(saved.args[0], None)

    async def test_corrupt_or_foreign_snapshot_cannot_restore_other_properties(self):
        with patch.dict(sys.modules, {'iterm2': Mock()}):
            api = appearance._API()
        for value in (None, 'invalid', '[]', '{"Name":"foreign"}', '{}'):
            session = Mock(async_get_variable=AsyncMock(return_value=value), async_set_variable=AsyncMock())
            with self.subTest(value=value):
                self.assertIsNone(await api.take_snapshot(session, '42-1'))

    async def test_snapshot_from_a_different_launch_cannot_overwrite_or_clear_current_state(self):
        with patch.dict(sys.modules, {'iterm2': Mock()}):
            api = appearance._API()
        record = {'launch_id': '42-1', 'properties': {key: None for key in
                  ('Tab Color', 'Tab Color (Light)', 'Tab Color (Dark)', 'Use Tab Color',
                   'Use Tab Color (Light)', 'Use Tab Color (Dark)', 'Icon', 'Custom Icon Path')}}
        session = Mock(async_get_variable=AsyncMock(return_value=json.dumps(record)), async_set_variable=AsyncMock())
        self.assertIsNone(await api.take_snapshot(session, '42-2'))
        session.async_set_variable.assert_not_called()

    async def test_subscription_uses_both_variables_and_explicit_id_and_cleans_up(self):
        sdk = Mock()
        monitors = []

        class Monitor:
            def __init__(self, connection, scope, name, terminal):
                self.args = (connection, scope, name, terminal)
                self.queue = asyncio.Queue()
                self.closed = False
                monitors.append(self)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                self.closed = True

            async def async_get(self):
                return await self.queue.get()

        sdk.VariableMonitor = Monitor
        with patch.dict(sys.modules, {'iterm2': sdk}):
            api = appearance._API()
        api.connection = object()
        async with api.watch(UUID) as events:
            await monitors[1].queue.put('Codex')
            await asyncio.wait_for(events.get(), .1)
        self.assertEqual([monitor.args for monitor in monitors], [
            (api.connection, sdk.VariableScopes.SESSION, 'jobName', UUID),
            (api.connection, sdk.VariableScopes.SESSION, 'profileName', UUID)])
        self.assertTrue(all(monitor.closed for monitor in monitors))

    async def test_only_color_and_icon_properties_including_light_dark(self):
        sdk = Mock()
        sdk.LocalWriteOnlyProfile.return_value = profile = Mock()
        sdk.Color.return_value = color = object()
        with patch.dict(sys.modules, {'iterm2': sdk}):
            api = appearance._API()
        session = Mock(async_set_profile_properties=AsyncMock())
        await api.write(session, '#65A85A', '/fixture/icon.png')
        sdk.Color.assert_called_once_with(101, 168, 90)
        expected = {'set_tab_color': color, 'set_tab_color_light': color, 'set_tab_color_dark': color,
                    'set_use_tab_color': True, 'set_use_tab_color_light': True, 'set_use_tab_color_dark': True,
                    'set_icon_mode': sdk.IconMode.CUSTOM, 'set_custom_icon_path': '/fixture/icon.png'}
        self.assertEqual({call[0]: call.args[0] for call in profile.mock_calls}, expected)
        self.assertEqual(len(profile.mock_calls), 8)
        session.async_set_profile_properties.assert_awaited_once_with(profile)


class SupervisorTests(unittest.TestCase):
    def test_signal_around_ready_duplicate_close_still_reaps_and_restores_handlers(self):
        for signum, timing in ((sig, when) for sig in (signal.SIGTERM, signal.SIGINT)
                               for when in ('before', 'after')):
            with self.subTest(signum=signum, timing=timing):
                child = Mock(pid=12345, returncode=None)
                handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
                mask = signal.pthread_sigmask(signal.SIG_BLOCK, ())
                closed = []
                def close(fd):
                    if timing == 'before':
                        signal.raise_signal(signum)
                    if fd in closed:
                        raise OSError(9, 'duplicate already closed')
                    closed.append(fd)
                    if timing == 'after':
                        signal.raise_signal(signum)
                try:
                    with patch.object(appearance.os, 'dup', return_value=42), \
                         patch.object(appearance.os, 'close', side_effect=close), \
                         patch.object(appearance.subprocess, 'Popen', return_value=child), \
                         patch.object(appearance.os, 'killpg') as kill:
                        self.assertEqual(appearance._supervise(
                            {'terminal': UUID, 'phase': 'launch', 'ready_fd': 3}, ENV), 'unavailable')
                    self.assertEqual(closed, [42])
                    kill.assert_called_once_with(12345, signal.SIGKILL)
                    child.wait.assert_called_once()
                    child.stdin.close.assert_called_once()
                    child.stdout.close.assert_called_once()
                    for sig, handler in handlers.items():
                        self.assertEqual(signal.getsignal(sig), handler)
                    self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, ()), mask)
                finally:
                    for sig, handler in handlers.items():
                        signal.signal(sig, handler)
                    signal.pthread_sigmask(signal.SIG_SETMASK, mask)

    def test_real_worker_readiness_follows_write_and_keeps_cancel_fence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'iterm2.py').write_text('''
import asyncio, os, pathlib
class Profile:
    def __getattr__(self, name): return lambda *args: None
LocalWriteOnlyProfile = Profile
Color = lambda *args: None
class IconMode: CUSTOM = 2
class VariableScopes: SESSION = 1
class VariableMonitor:
    def __init__(self, *args): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def async_get(self): await asyncio.Future()
class Session:
    async def async_get_variable(self, name): return 'zsh'
    async def async_set_variable(self, name, value): pass
    async def async_set_profile_properties(self, profile):
        await asyncio.sleep(.05)
        pathlib.Path(os.environ['APPEARANCE_TEST_WRITE']).touch()
class App:
    def get_session_by_id(self, terminal): return Session()
async def async_get_app(connection): return App()
class Connection:
    @staticmethod
    async def async_create(): return Connection()
    @property
    def websocket(self): return self
    async def close(self): pass
''')
            config = root / 'rules.json'
            config.write_text(json.dumps({'projects': [{'root': str(root), 'color': '#65A85A', 'icon': 'android-mail'}]}))
            marker = root / 'written'
            read_fd, write_fd = os.pipe()
            try:
                with subprocess.Popen([sys.executable, appearance.__file__, '--config', str(config),
                        '--cwd', str(root), '--phase', 'launch', '--ready-fd', str(write_fd)],
                        env={**ENV, 'PYTHONPATH': str(root), 'APPEARANCE_TEST_WRITE': str(marker)},
                        pass_fds=(write_fd,), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as child:
                    os.close(write_fd)
                    write_fd = None
                    try:
                        self.assertTrue(select.select([read_fd], [], [], 2)[0], 'no readiness or EOF')
                        self.assertEqual(os.read(read_fd, 64), b'ready\n')
                        self.assertTrue(marker.exists())
                        self.assertIsNone(child.poll(), 'observer must remain alive after readiness')
                        child.terminate()
                        self.assertEqual(child.communicate(timeout=1), ('unavailable\n', ''))
                        self.assertEqual(os.read(read_fd, 64), b'')
                    finally:
                        if child.poll() is None:
                            child.terminate()
                            child.communicate(timeout=3)
            finally:
                os.close(read_fd)
                if write_fd is not None:
                    os.close(write_fd)

    def test_worker_missing_sdk_and_sdk_diagnostics_stay_private(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / 'iterm2.py').write_text("print('private SDK detail'); raise ImportError('private path')")
            self.assertEqual(appearance.probe(environment={**ENV, 'PYTHONPATH': str(root)}), 'unavailable')

    def test_real_supervisor_sigterm_reaps_auth_descendant(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / 'iterm2.py').write_text('''
import os, pathlib, subprocess, sys
class Connection:
    @staticmethod
    async def async_create():
        child = subprocess.Popen([sys.executable, '-c', 'import signal; signal.pause()'])
        pathlib.Path(os.environ['APPEARANCE_TEST_PID']).write_text(str(child.pid))
        child.wait()
''')
            marker = root / 'child.pid'
            with subprocess.Popen([sys.executable, appearance.__file__, '--probe'],
                    env={**ENV, 'PYTHONPATH': str(root), 'APPEARANCE_TEST_PID': str(marker)},
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as supervisor:
                try:
                    deadline = time.monotonic() + 1.5
                    while not marker.exists() and supervisor.poll() is None and time.monotonic() < deadline:
                        time.sleep(.01)
                    self.assertTrue(marker.exists(), 'fake auth never started')
                    supervisor.terminate()
                    output, error = supervisor.communicate(timeout=1)
                    self.assertEqual((output, error, supervisor.returncode), ('unavailable\n', '', 0))
                    self.assert_process_gone(int(marker.read_text()))
                finally:
                    if supervisor.poll() is None:
                        supervisor.terminate()
                        supervisor.wait(timeout=3)

    def test_cancel_during_spawn_is_not_lost(self):
        child = Mock(pid=12345, returncode=None)
        def spawning(*args, **kwargs):
            signal.raise_signal(signal.SIGTERM)
            return child
        with patch.object(appearance.subprocess, 'Popen', side_effect=spawning), \
             patch.object(appearance.os, 'killpg') as kill:
            self.assertEqual(appearance._supervise({'terminal': UUID, 'phase': 'probe'}, ENV), 'unavailable')
        child.communicate.assert_not_called()
        kill.assert_called_once_with(12345, signal.SIGKILL)
        child.wait.assert_called_once()

    def test_timeout_kills_descendants_even_when_worker_already_exited(self):
        child = Mock(pid=12345, returncode=1)
        child.communicate.side_effect = subprocess.TimeoutExpired('worker', 1)
        with patch.object(appearance.subprocess, 'Popen', return_value=child), \
             patch.object(appearance.os, 'killpg') as kill:
            self.assertEqual(appearance._supervise({'terminal': UUID, 'phase': 'probe'}, ENV), 'timeout')
        kill.assert_called_once_with(12345, signal.SIGKILL)

    def test_real_sync_auth_timeout_kills_descendant(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / 'iterm2.py').write_text('''
import os, pathlib, subprocess, sys
class Connection:
    @staticmethod
    async def async_create():
        child = subprocess.Popen([sys.executable, '-c', 'import signal; signal.pause()'])
        pathlib.Path(os.environ['APPEARANCE_TEST_PID']).write_text(str(child.pid))
        child.wait()
''')
            marker = root / 'child.pid'
            started = time.monotonic()
            result = appearance._supervise({'terminal': UUID, 'phase': 'probe'},
                {**ENV, 'PYTHONPATH': str(root), 'APPEARANCE_TEST_PID': str(marker)})
            self.assertEqual(result, 'timeout')
            self.assertLess(time.monotonic() - started, 3.1)
            pid = int(marker.read_text())
            self.assert_process_gone(pid)

    def assert_process_gone(self, pid):
        # Allow the OS to reap this test's killed orphan without inspecting others.
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(.01)
        self.fail('fake auth descendant survived cancellation')

    def test_fake_clock_deadline_includes_process_start_and_kills_group(self):
        child = Mock(pid=12345, returncode=None)
        child.communicate.side_effect = subprocess.TimeoutExpired('worker', 1)
        with patch.object(appearance.time, 'monotonic', side_effect=[10, 11]), \
             patch.object(appearance.subprocess, 'Popen', return_value=child), \
             patch.object(appearance.os, 'killpg') as kill:
            self.assertEqual(appearance._supervise({'terminal': UUID, 'phase': 'probe'}, ENV), 'timeout')
        self.assertAlmostEqual(child.communicate.call_args.kwargs['timeout'], appearance._HARD_SECONDS - 1)
        kill.assert_called_once_with(12345, signal.SIGKILL)
        child.wait.assert_called_once()

    def test_signal_cancellation_kills_and_reaps_group(self):
        child = Mock(pid=12345, returncode=None)
        def interrupted(**kwargs):
            signal.raise_signal(signal.SIGTERM)
        child.communicate.side_effect = interrupted
        original = signal.getsignal(signal.SIGTERM)
        with patch.object(appearance.subprocess, 'Popen', return_value=child), \
             patch.object(appearance.os, 'killpg') as kill:
            self.assertEqual(appearance._supervise({'terminal': UUID, 'phase': 'probe'}, ENV), 'unavailable')
        kill.assert_called_once_with(12345, signal.SIGKILL)
        child.wait.assert_called_once()
        self.assertEqual(signal.getsignal(signal.SIGTERM), original)
