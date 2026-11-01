"""One SDK create, supervised across synchronous SDK import and authorization."""
import asyncio
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import json
import math
import os
import sys
import time

from .models import Finding


_PREFLIGHT_SECONDS = 10
_CREATE_SECONDS = 30


@dataclass(frozen=True)
class LaunchCreation:
    status: str
    window_id: str | None
    tab_id: str | None
    session_id: str | None
    deadline: float | None
    findings: tuple[Finding, ...]


def _identifier(value):
    if not isinstance(value, str) or not value or len(value) > 256 or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid SDK identifier')
    return value


async def _operate(request, emit):
    connection = None
    sent = False
    try:
        emit({'phase': 'connect'})
        import iterm2
        async with asyncio.timeout(_PREFLIGHT_SECONDS):
            connection = await iterm2.Connection.async_create()
        emit({'phase': 'app'})
        async with asyncio.timeout(_PREFLIGHT_SECONDS):
            app = await iterm2.async_get_app(connection)
        emit({'phase': 'profiles'})
        async with asyncio.timeout(_PREFLIGHT_SECONDS):
            profiles = await iterm2.Profile.async_get(connection)
        matches = [p for p in profiles if p.name == request['profile']]
        if len(matches) != 1 or matches[0].guid != request['profile_guid']:
            return 'blocked'
        window = app.get_window_by_id(request['window_id'])
        if window is None or window.window_id != request['window_id']:
            return 'blocked'
        deadline = time.monotonic() + _CREATE_SECONDS
        # Publish uncertainty before the one possible mutation; cancellation is no rollback.
        emit({'phase': 'create', 'window_id': _identifier(window.window_id), 'deadline': deadline})
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            return 'blocked'
        sent = True
        async with asyncio.timeout(remaining):
            tab = await window.async_create_tab(profile=request['profile'], command=request['command'], select=True)
            emit({'tab_id': _identifier(tab.tab_id)})
            sessions = tab.all_sessions
            if len(sessions) != 1:
                return 'unknown'
            emit({'session_id': _identifier(sessions[0].session_id)})
        return 'created_unverified'
    except (Exception, SystemExit, asyncio.CancelledError):
        return 'unknown' if sent else 'blocked'
    finally:
        if connection is not None:
            try:
                async with asyncio.timeout(.2):
                    await connection.websocket.close()
            except (Exception, SystemExit, asyncio.CancelledError):
                pass


def _result(status, window_id=None, tab_id=None, session_id=None, deadline=None):
    message = ('The iTerm2 SDK or selected launch target is unavailable.' if status == 'blocked' else
               'Launch observations are incomplete. Inspect the known tab before taking further action.')
    findings = () if status == 'created_unverified' else (
        Finding('launch', 'codex', 'launch_'+status, 'unavailable', message),)
    return LaunchCreation(status, window_id, tab_id, session_id, deadline, findings)


async def create_tab(window_id: str, profile: str, profile_guid: str, command: str) -> LaunchCreation:
    """Bound SDK auth in a same-Python helper; no retries or terminal cleanup."""
    child = None
    status = 'blocked'
    completed = False
    known_window = tab_id = session_id = deadline = None
    try:
        async with asyncio.timeout(_PREFLIGHT_SECONDS):
            child = await asyncio.create_subprocess_exec(
                sys.executable, '-m', 'iterm2_utils.launch_api',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, limit=4096)
            child.stdin.write(json.dumps(dict(window_id=window_id, profile=profile,
                                             profile_guid=profile_guid, command=command)).encode()+b'\n')
            await child.stdin.drain()

        async def read(seconds):
            async with asyncio.timeout(max(0, seconds)):
                line = await child.stdout.readline()
            if len(line) > 4096 or not line.endswith(b'\n'):
                raise ValueError('Invalid helper frame')
            frame = json.loads(line)
            if not isinstance(frame, dict):
                raise ValueError('Invalid helper frame')
            return frame

        for phase in ('connect', 'app', 'profiles', 'create'):
            frame = await read(_PREFLIGHT_SECONDS)
            if frame == {'result': 'blocked'}:
                completed = True
                return _result('blocked')
            if phase != 'create':
                if frame != {'phase': phase}:
                    raise ValueError('Invalid helper phase')
                continue
            if frame.get('phase') != 'create':
                raise ValueError('Invalid helper phase')
            creation_deadline = frame.get('deadline')
            if (set(frame) != {'phase', 'window_id', 'deadline'} or frame['window_id'] != window_id or
                    isinstance(creation_deadline, bool) or not isinstance(creation_deadline, (float, int)) or
                    not math.isfinite(creation_deadline) or
                    not time.monotonic() < creation_deadline <= time.monotonic()+_CREATE_SECONDS):
                raise ValueError('Invalid creation frame')
            known_window = window_id
            deadline = creation_deadline
            status = 'unknown'
            child.stdin.write(b'create\n')
            await child.stdin.drain()
            child.stdin.close()

        for field in ('tab_id', 'session_id', 'result'):
            frame = await read(deadline-time.monotonic())
            if frame == {'result': 'unknown'}:
                completed = True
                break
            if field == 'result':
                if frame != {'result': 'created_unverified'}:
                    raise ValueError('Invalid helper result')
                status = 'created_unverified'
                completed = True
            elif set(frame) != {field}:
                raise ValueError('Invalid helper identifier')
            elif field == 'tab_id':
                tab_id = _identifier(frame[field])
            else:
                session_id = _identifier(frame[field])
    except (Exception, asyncio.CancelledError):
        # Exceptions may contain SDK settings or command text; expose fixed findings only.
        pass
    finally:
        if child is not None:
            if not child.stdin.is_closing():
                child.stdin.close()
            if child.returncode is None:
                try:
                    if not completed:
                        try:
                            child.kill()
                        except ProcessLookupError:
                            pass
                    async with asyncio.timeout(.3):
                        await child.wait()
                except TimeoutError:
                    try:
                        child.kill()  # Only this SDK helper, never the created terminal/process.
                    except ProcessLookupError:
                        pass
                    await child.wait()
    return _result(status, known_window, tab_id, session_id, deadline)


def _worker():
    protocol = sys.stdout
    with open(os.devnull, 'w') as sink, redirect_stdout(sink), redirect_stderr(sink):
        def emit(frame):
            protocol.write(json.dumps(frame)+'\n')
            protocol.flush()
            if frame.get('phase') == 'create' and sys.stdin.readline() != 'create\n':
                raise ValueError('Creation was not acknowledged')
        try:
            request = json.loads(sys.stdin.readline())
            status = asyncio.run(_operate(request, emit))
        except (Exception, SystemExit):
            status = 'blocked'
        emit({'result': status})


if __name__ == '__main__':
    _worker()
