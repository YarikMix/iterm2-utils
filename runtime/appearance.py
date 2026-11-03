"""Repository appearance rules, usable without the optional iTerm2 API."""

import argparse
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager, redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
import time

try:
    from .events import terminal_from_environment, terminal_id
except ImportError:
    from events import terminal_from_environment, terminal_id


BUILTIN_ICONS = frozenset({
    'ios', 'android', 'kotlett', 'ios-mail', 'ios-cloud',
    'android-mail', 'android-cloud', 'chrome-mail', 'chrome-cloud',
})


def load_rules(path: Path) -> list[dict[str, str]]:
    """Validate rules and normalize physical roots without requiring mounted disks."""
    document = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(document, dict) or set(document) != {'projects'}:
        raise ValueError('Appearance configuration must contain only projects')
    if not isinstance(document['projects'], list) or not document['projects']:
        raise ValueError('Appearance projects must be a nonempty list')
    rules = []
    roots = set()
    identities = set()
    for project in document['projects']:
        if not isinstance(project, dict) or set(project) != {'root', 'color', 'icon'}:
            raise ValueError('Appearance project must contain root, color and icon')
        if any(not isinstance(value, str) or '\x00' in value for value in project.values()):
            raise ValueError('Appearance project values must be strings without NUL')
        root = Path(project['root'])
        if not root.is_absolute():
            raise ValueError('Appearance root must be an absolute path')
        if re.fullmatch(r'#[0-9a-fA-F]{6}', project['color']) is None:
            raise ValueError('Appearance color must be #RRGGBB')
        icon = project['icon']
        if icon not in BUILTIN_ICONS and not (Path(icon).is_absolute() and Path(icon).suffix.lower() == '.png'):
            raise ValueError('Appearance icon must be a builtin name or absolute PNG path')
        try:
            root = root.resolve()
        except (OSError, RuntimeError):
            # Preserve unavailable rules; selection retries when the disk is available.
            pass
        identity = _directory_identity(root)
        if root in roots or identity is not None and identity in identities:
            raise ValueError('Appearance roots must be physically unique')
        roots.add(root)
        if identity is not None:
            identities.add(identity)
        rules.append({'root': str(root), 'color': project['color'].upper(), 'icon': icon})
    return rules


def _directory_identity(path: Path) -> tuple[int, int] | None:
    try:
        info = path.stat()
        return (info.st_dev, info.st_ino) if stat.S_ISDIR(info.st_mode) else None
    except (OSError, RuntimeError):
        return None


def select_rule(rules: list[dict[str, str]], cwd: Path) -> dict[str, str] | None:
    """Select the most specific available physical root containing cwd."""
    try:
        physical_cwd = cwd.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if _directory_identity(physical_cwd) is None:
        return None
    ancestors = {_directory_identity(path): index
                 for index, path in enumerate((physical_cwd, *physical_cwd.parents))}
    selected, distance = None, len(physical_cwd.parts)
    for rule in rules:
        identity = _directory_identity(Path(rule['root']))
        if identity is not None and ancestors.get(identity, distance) < distance:
            selected = rule
            distance = ancestors[identity]
    return selected


_HARD_SECONDS = 2.8
_API_TIMEOUT = 2.2
_WATCH_SECONDS = 1.5
_SNAPSHOT_VARIABLE = 'user.iterm2_utils_appearance_snapshot'
_APPEARANCE_KEYS = frozenset({
    'Tab Color', 'Tab Color (Light)', 'Tab Color (Dark)', 'Use Tab Color',
    'Use Tab Color (Light)', 'Use Tab Color (Dark)', 'Icon', 'Custom Icon Path',
})


def _tty_device(path: str) -> int | None:
    """Compare terminal aliases by character-device identity inside the worker."""
    if not isinstance(path, str) or not path.startswith('/') or '\x00' in path:
        return None
    try:
        info = os.stat(path)
        return info.st_rdev if stat.S_ISCHR(info.st_mode) else None
    except (OSError, ValueError):
        return None


class _TerminalMismatch(Exception):
    pass


class _API:
    """Optional official SDK; importing the rules module never imports it."""

    def __init__(self):
        import iterm2
        self.sdk = iterm2
        self.connection = None

    async def connect(self):
        self.connection = await self.sdk.Connection.async_create()

    async def find(self, terminal):
        app = await self.sdk.async_get_app(self.connection)
        return app.get_session_by_id(terminal)

    async def owns_terminal(self, session, device: int) -> bool:
        return session is not None and device is not None and _tty_device(
            await session.async_get_variable('tty')) == device

    async def job_name(self, session):
        return await session.async_get_variable('jobName')

    async def write(self, session, color, icon):
        profile = self.sdk.LocalWriteOnlyProfile()
        rgb = self.sdk.Color(*(int(color[index:index + 2], 16) for index in (1, 3, 5)))
        # These variants preserve the profile's separate light/dark preference.
        profile.set_tab_color(rgb)
        profile.set_tab_color_light(rgb)
        profile.set_tab_color_dark(rgb)
        profile.set_use_tab_color(True)
        profile.set_use_tab_color_light(True)
        profile.set_use_tab_color_dark(True)
        profile.set_icon_mode(self.sdk.IconMode.CUSTOM)
        profile.set_custom_icon_path(icon)
        await session.async_set_profile_properties(profile)

    async def reset(self, session):
        profile = self.sdk.LocalWriteOnlyProfile()
        profile.set_use_tab_color(False)
        profile.set_use_tab_color_light(False)
        profile.set_use_tab_color_dark(False)
        profile.set_icon_mode(self.sdk.IconMode.NONE)
        profile.set_custom_icon_path('')
        await session.async_set_profile_properties(profile)

    async def snapshot(self, session):
        profile = await session.async_get_profile()
        values = profile.local_write_only_copy.values
        return {key: json.loads(values.get(key, 'null')) for key in _APPEARANCE_KEYS}

    async def save_snapshot(self, session, properties, launch_id):
        await session.async_set_variable(_SNAPSHOT_VARIABLE, json.dumps(
            {'launch_id': launch_id, 'properties': properties}))

    async def invalidate_snapshot(self, session):
        await session.async_set_variable(_SNAPSHOT_VARIABLE, None)

    async def _read_snapshot_record(self, session, launch_id):
        value = await session.async_get_variable(_SNAPSHOT_VARIABLE)
        try:
            record = json.loads(value)
            if not isinstance(record, dict) or set(record) != {'launch_id', 'properties'} or record['launch_id'] != launch_id:
                return None
        except (ValueError, TypeError):
            return None
        return record

    async def take_snapshot(self, session, launch_id):
        # Keep ownership until the return observer has finished using its snapshot.
        record = await self._read_snapshot_record(session, launch_id)
        properties = None if record is None else record['properties']
        if not isinstance(properties, dict) or set(properties) != _APPEARANCE_KEYS:
            return None
        return properties

    async def clear_snapshot(self, session, launch_id):
        async with self.sdk.Transaction(self.connection):
            if await self._read_snapshot_record(session, launch_id) is not None:
                await session.async_set_variable(_SNAPSHOT_VARIABLE, None)

    async def restore(self, session, properties, launch_id):
        async with self.sdk.Transaction(self.connection):
            if await self.take_snapshot(session, launch_id) is None:
                return False
            await session.async_set_profile_properties(self.sdk.LocalWriteOnlyProfile(properties))
            return True

    async def write_if_current(self, session, color, icon, launch_id):
        async with self.sdk.Transaction(self.connection):
            if await self._read_snapshot_record(session, launch_id) is None:
                return False
            await self.write(session, color, icon)
            return True

    @asynccontextmanager
    async def watch(self, terminal):
        events = asyncio.Queue()
        tasks = []

        async def forward(monitor):
            while True:
                await monitor.async_get()
                events.put_nowait(None)

        async with AsyncExitStack() as stack:
            try:
                for name in ('jobName', 'profileName'):
                    monitor = await stack.enter_async_context(self.sdk.VariableMonitor(
                        self.connection, self.sdk.VariableScopes.SESSION, name, terminal))
                    tasks.append(asyncio.create_task(forward(monitor)))
                yield events
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self):
        if self.connection is not None:
            await self.connection.websocket.close()


async def _operate(request):
    api = None
    try:
        terminal = request['terminal']
        phase = request['phase']
        if terminal_id(terminal) != terminal or phase not in {'shell', 'launch', 'return', 'probe'}:
            return 'unavailable'
        async with asyncio.timeout(_API_TIMEOUT):
            api = _API()
            await api.connect()
            session = await api.find(terminal)
            if session is None:
                return 'unavailable'
            if phase == 'probe':
                return 'ready'

            device = request.get('device')
            owned = False

            async def require_ownership():
                nonlocal owned
                # A failed ownership read must also suppress snapshot cleanup.
                owned = False
                if device is None or not await api.owns_terminal(session, device):
                    raise _TerminalMismatch()
                owned = True

            await require_ownership()
            preserved = None
            async def write():
                await require_ownership()
                if request.get('preserve'):
                    return await api.restore(session, preserved, request.get('launch_id'))
                if phase != 'shell':
                    return await api.write_if_current(session, request['color'], request['icon'], request.get('launch_id'))
                if request.get('reset'):
                    await api.reset(session)
                else:
                    await api.write(session, request['color'], request['icon'])
                return True

            if phase == 'shell':
                # A nested shell may share the session with a parent's return observer.
                await api.invalidate_snapshot(session)
                await write()
                return 'applied'
            # The dispatcher must terminate AND reap the previous helper first.
            async with api.watch(terminal) as events:
                try:
                    applied = False
                    if phase == 'launch':
                        if request.get('preserve'):
                            preserved = await api.snapshot(session)
                        # A matched launch also invalidates an older preserved snapshot.
                        await require_ownership()
                        await api.save_snapshot(session, preserved, request.get('launch_id'))
                    elif request.get('preserve'):
                        preserved = await api.take_snapshot(session, request.get('launch_id'))
                        if preserved is None:
                            return 'ignored'
                    job = await api.job_name(session)
                    if (phase == 'launch' and not request.get('preserve')) or (phase == 'return' and job != 'codex'):
                        applied = await write()
                    if 'ready_fd' in request:
                        # Release native Codex only after the snapshot and subscriptions exist.
                        ready_fd = request.pop('ready_fd')
                        try:
                            os.write(ready_fd, b'ready\n')
                        finally:
                            os.close(ready_fd)
                    stop = asyncio.get_running_loop().time() + _WATCH_SECONDS
                    while True:
                        remaining = stop - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            break
                        try:
                            async with asyncio.timeout(remaining):
                                await events.get()
                        except TimeoutError:
                            break
                        # Read current state, not a possibly queued obsolete event.
                        job = await api.job_name(session)
                        if (job == 'codex') == (phase == 'launch'):
                            applied = await write() or applied
                    return 'applied' if applied else 'ignored' if request.get('preserve') else 'timeout'
                finally:
                    if phase == 'return' and owned:
                        await require_ownership()
                        await api.clear_snapshot(session, request.get('launch_id'))
    except _TerminalMismatch:
        return 'ignored'
    except TimeoutError:
        return 'timeout'
    except Exception:
        return 'unavailable'
    finally:
        if api is not None:
            try:
                async with asyncio.timeout(0.15):
                    await api.close()
            except Exception:
                pass


class _Cancelled(BaseException):
    pass


def _supervise(request, environment):
    """Bound SDK import/auth too; SIGTERM + wait is the launcher's cancel fence."""
    if threading.current_thread() is not threading.main_thread():
        return 'unavailable'
    started = time.monotonic()
    child = None
    ready_fd = None
    cancelled = False
    interrupted = False
    handlers = {}

    def cancel(_signum, _frame):
        nonlocal cancelled
        cancelled = True
        if child is not None:
            raise _Cancelled()

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            handlers[signum] = signal.signal(signum, cancel)
        if 'ready_fd' in request:
            # Only a readiness duplicate reaches the worker; supervisor owns lifetime.
            ready_fd = os.dup(request['ready_fd'])
            request = {**request, 'ready_fd': ready_fd}
        child = subprocess.Popen(
            [sys.executable, str(Path(__file__).absolute()), '--worker'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=environment, start_new_session=True, text=True,
            pass_fds=() if ready_fd is None else (ready_fd,))
        if ready_fd is not None:
            mask = signal.pthread_sigmask(signal.SIG_BLOCK, (signal.SIGTERM, signal.SIGINT))
            try:
                os.close(ready_fd)
                ready_fd = None
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        if cancelled:
            raise _Cancelled()
        output, _ = child.communicate(
            input=json.dumps(request), timeout=max(0, _HARD_SECONDS - (time.monotonic() - started)))
        allowed = {'ready', 'unavailable', 'timeout'} if request['phase'] == 'probe' else {'applied', 'ignored', 'unavailable', 'timeout'}
        result = output.strip()
        return result if child.returncode == 0 and result in allowed else 'unavailable'
    except subprocess.TimeoutExpired:
        interrupted = True
        return 'timeout'
    except (_Cancelled, OSError):
        interrupted = True
        return 'unavailable'
    finally:
        for signum in handlers:
            signal.signal(signum, signal.SIG_IGN)
        if ready_fd is not None:
            os.close(ready_fd)
        if child is not None:
            if interrupted or child.returncode is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
            for stream in (child.stdin, child.stdout):
                if stream is not None:
                    stream.close()
        for signum, handler in handlers.items():
            signal.signal(signum, handler)


def apply(config: Path, cwd: Path, phase: str, *, environment: dict[str, str],
          ready_fd: int | None = None, launch_id: str | None = None,
          tty: str | None = None) -> str:
    """Apply this physical directory's rule to its explicit iTerm2 session."""
    terminal = terminal_from_environment(environment)
    if terminal is None or environment.get('TMUX'):
        return 'ignored'
    if phase not in {'shell', 'launch', 'return'}:
        return 'unavailable'
    request = {'terminal': terminal, 'phase': phase, 'config': str(config), 'cwd': str(cwd), 'tty': tty}
    if launch_id is not None:
        if not isinstance(launch_id, str) or re.fullmatch(r'[0-9]{1,20}-[0-9]{1,20}', launch_id) is None:
            return 'unavailable'
        request['launch_id'] = launch_id
    if ready_fd is not None:
        if phase != 'launch' or type(ready_fd) is not int or ready_fd < 3:
            return 'unavailable'
        request['ready_fd'] = ready_fd
    return _supervise(request, environment)


def _run_request(request):
    """Filesystem checks also run within the supervisor's hard deadline."""
    try:
        if request['phase'] != 'probe':
            device = _tty_device(request.get('tty'))
            if device is None:
                return 'ignored'
            request = {**request, 'device': device}
            rule = select_rule(load_rules(Path(request['config'])), Path(request['cwd']))
            if rule is None:
                if request['phase'] == 'shell':
                    request = {**request, 'reset': True}
                else:
                    request = {**request, 'preserve': True}
            else:
                icon = (Path(__file__).parent / 'assets' / 'appearance' / (rule['icon'] + '.png')
                        if rule['icon'] in BUILTIN_ICONS else Path(rule['icon']))
                if not icon.is_file():
                    return 'unavailable'
                request = {**request, 'color': rule['color'], 'icon': str(icon)}
        return asyncio.run(_operate(request))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        return 'unavailable'


def probe(*, environment: dict[str, str]) -> str:
    """Read-only connectivity check of the explicitly identified session."""
    terminal = terminal_from_environment(environment)
    if terminal is None or environment.get('TMUX'):
        return 'unavailable'
    return _supervise({'terminal': terminal, 'phase': 'probe'}, environment)


def _main():
    result = 'unavailable'
    try:
        if sys.argv[1:] == ['--worker']:
            request = json.loads(sys.stdin.read())
            # SDK diagnostics may include private details; emit only our status.
            with open(os.devnull, 'w') as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
                result = _run_request(request)
        else:
            parser = argparse.ArgumentParser(exit_on_error=False, add_help=False)
            parser.add_argument('--probe', action='store_true')
            parser.add_argument('--config', type=Path)
            parser.add_argument('--cwd', type=Path)
            parser.add_argument('--phase', choices=('shell', 'launch', 'return'))
            parser.add_argument('--ready-fd', type=int)
            parser.add_argument('--launch-id')
            parser.add_argument('--tty')
            with open(os.devnull, 'w') as quiet, redirect_stderr(quiet):
                args = parser.parse_args()
            if args.probe:
                result = probe(environment=dict(os.environ))
            elif args.config is not None and args.cwd is not None and args.phase:
                result = apply(args.config, args.cwd, args.phase, environment=dict(os.environ),
                               ready_fd=args.ready_fd, launch_id=args.launch_id, tty=args.tty)
    except (Exception, SystemExit):
        pass
    print(result)


if __name__ == '__main__':
    _main()
