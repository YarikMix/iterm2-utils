"""Installed observational dispatcher. Success and every failure emit only {}."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


class HookBudgetExpired(BaseException):
    """Overall deadline must bypass ordinary per-handler error isolation."""


class Runner:
    def run(self, argv: list[str], *, timeout: float,
            stdin: str | None = None, env: dict[str, str] | None = None
            ) -> subprocess.CompletedProcess:
        child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, env=env,
                                 start_new_session=True)
        try:
            stdout, stderr = child.communicate(input=stdin, timeout=timeout)
        except BaseException:
            # Also covers the overall alarm while communicate is waiting. Killing
            # the whole group removes native's it2 child as well as native itself.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            finally:
                child.communicate()
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
    old = None
    try:
        old = signal.signal(signal.SIGALRM, expired)
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
    except (Exception, HookBudgetExpired):
        pass
    finally:
        if old is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
    print('{}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
