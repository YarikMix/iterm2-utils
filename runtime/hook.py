"""Installed observational dispatcher. Success and every failure emit only {}."""
from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import threading


class HookBudgetExpired(BaseException):
    """Overall deadline must bypass ordinary per-handler error isolation."""


class HookCancelled(BaseException):
    """Controlled termination must unwind native process-group ownership."""


@contextmanager
def _defer_spawn_signals():
    """Retain cancellation until Popen has published its child PID.

    A signal mask would also be inherited by the executable. Temporarily queue
    callable Python handlers instead; exec resets those handlers in the child.
    Python delivers signals only on the main thread.
    """
    pending = []
    try:
        with ExitStack() as restore:
            if threading.current_thread() is threading.main_thread():
                for number in (signal.SIGALRM, signal.SIGINT, signal.SIGTERM):
                    previous = signal.getsignal(number)
                    if callable(previous):
                        def defer(signum, frame, handler=previous):
                            pending.append((handler, signum, frame))
                        signal.signal(number, defer)
                        restore.callback(signal.signal, number, previous)
            yield
    finally:
        for handler, number, frame in pending:
            handler(number, frame)


class Runner:
    def run(self, argv: list[str], *, timeout: float,
            stdin: str | None = None, env: dict[str, str] | None = None
            ) -> subprocess.CompletedProcess:
        # Own the object before __init__: even a constructor exception after
        # spawning leaves a reference from which cleanup can obtain the PID.
        child = subprocess.Popen.__new__(subprocess.Popen)
        try:
            with _defer_spawn_signals():
                child.__init__(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, env=env,
                               start_new_session=True)
            stdout, stderr = child.communicate(input=stdin, timeout=timeout)
        except BaseException:
            if getattr(child, 'pid', None) is not None:
                # Remove native and its it2 child even on constructor cancellation.
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                finally:
                    try:
                        child.communicate()
                    except (OSError, ValueError):
                        # Popen closes pipes if its constructor raises. The direct
                        # child still belongs to us and must be reaped.
                        child.wait()
            raise
        return subprocess.CompletedProcess(argv, child.returncode, stdout, stderr)


def dispatch(event, settings: dict, runner: Runner, *, restore_metadata=None,
             raw_event: dict | None = None, environment: dict[str, str] | None = None,
             deadline: float | None = None) -> None:
    try:
        from events import terminal_id
    except ImportError:
        from .events import terminal_id
    if not terminal_id(event.terminal_uuid):
        return
    if deadline is None:
        deadline = time.monotonic()+2.7

    def check_budget():
        if time.monotonic() >= deadline:
            raise HookBudgetExpired('hook budget')

    check_budget()
    if settings.get('status') and event.agent == 'codex':
        try:
            try:
                from native_status import forward
            except ImportError:
                from .native_status import forward
            forward(event, raw_event if raw_event is not None else {}, settings, runner,
                    environment=dict(os.environ) if environment is None else environment,
                    deadline=deadline)
        except Exception:
            pass
    check_budget()
    if settings.get('notifications') and event.agent in settings.get('notification_agents', ['codex','claude']):
        try:
            try:
                from notifier import handle
            except ImportError:
                from .notifier import handle
            handle(event, settings, runner)
        except Exception:
            pass
    check_budget()
    if settings.get('restore') and event.agent == 'codex':
        try:
            try:
                from codex_restore.registry import handle
            except ImportError:
                from .codex_restore.registry import handle
            handle(event, settings, runner, restore_metadata)
        except Exception:
            pass


def main(argv: list[str]) -> int:
    # This deadline includes settings/stdin reads, locks and every handler.
    deadline = time.monotonic()+2.7
    def expired(*_):
        raise HookBudgetExpired('hook budget')
    def cancelled(*_):
        raise HookCancelled('hook cancelled')
    old = {}
    try:
        for number, handler in ((signal.SIGALRM, expired), (signal.SIGTERM, cancelled)):
            old[number] = signal.signal(number, handler)
        signal.setitimer(signal.ITIMER_REAL, max(0.000001, deadline-time.monotonic()))
        args = dict(zip(argv[::2], argv[1::2]))
        try:
            from events import normalize, terminal_from_environment
        except ImportError:
            from .events import normalize, terminal_from_environment
        settings = json.loads(Path(args['--settings']).read_text())
        encoded = sys.stdin.read(2*1024*1024+1)
        if len(encoded) > 2*1024*1024:
            raise ValueError('oversize event')
        raw = json.loads(encoded)
        environment = dict(os.environ)
        event = normalize(raw, args.get('--agent', 'codex'), terminal_from_environment(environment))
        if event:
            restore_metadata = {key: raw[key] for key in ('session_id', 'cwd', 'transcript_path', 'hook_event_name') if key in raw}
            dispatch(event, settings, Runner(), restore_metadata=restore_metadata,
                     raw_event=raw, environment=environment, deadline=deadline)
    except (Exception, HookBudgetExpired, HookCancelled):
        pass
    finally:
        if signal.SIGALRM in old:
            signal.setitimer(signal.ITIMER_REAL, 0)
        for number, handler in old.items():
            signal.signal(number, handler)
    print('{}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
