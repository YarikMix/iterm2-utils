"""Command boundary; lifecycle hooks always return the observational response."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import sys
import time
from typing import Iterator

from . import registry, restore, snapshots, store, transcripts
from .iterm import ITerm
from .models import Paths


def _paths() -> Paths:
    return store.paths(Path(os.environ.get("CODEX_HOME", "~/.codex")),
                       Path(os.environ.get("CODEX_RESTORE_CACHE_DIR", "~/.cache/codex-resume")))


@contextmanager
def _deadline(seconds: float) -> Iterator[float]:
    deadline = time.monotonic() + seconds
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    def expired(signum, frame):
        raise TimeoutError("hook deadline exceeded")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield deadline
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            remaining = max(0.000001, previous_timer[0] - seconds + max(0, deadline - time.monotonic()))
            signal.setitimer(signal.ITIMER_REAL, remaining, previous_timer[1])


def _hook() -> int:
    try:
        with _deadline(2.0) as deadline:
            event = json.load(sys.stdin)
            if not isinstance(event, dict) or event.get("hook_event_name") not in ("SessionStart", "UserPromptSubmit", "Stop"):
                return 0
            token = os.environ.get("CODEX_RESTORE_TOKEN", "")
            terminal = registry.normalize_terminal(os.environ.get("ITERM_SESSION_ID", ""))
            paths, client = _paths(), ITerm()
            client.deadline = deadline
            now = time.time()
            if registry.accept_event(paths, token, terminal, event, client.identity, now):
                snapshots.capture(paths, client, now, required_terminal=terminal, required_token=token)
    except Exception:
        pass
    finally:
        print("{}")
    return 0


def main(argv: list[str]) -> int:
    # Hook dispatch precedes parser and all setup, so even broken state is harmless.
    if argv == ["hook"]:
        return _hook()
    parser = argparse.ArgumentParser(prog="codex-sessions")
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register")
    register.add_argument("--terminal", required=True)
    register.add_argument("--shell-pid", required=True, type=int)
    register.add_argument("--request")
    finish = commands.add_parser("finish")
    finish.add_argument("token")
    listing = commands.add_parser("restore-list")
    listing.add_argument("--auto", action="store_true")
    commands.add_parser("restore-open")
    cancel = commands.add_parser("restore-cancel")
    cancel.add_argument("request")
    args = parser.parse_args(argv)
    try:
        paths = _paths()
        if args.command == "register":
            client = ITerm()
            started = client.identity(args.shell_pid)
            if not started:
                raise ValueError("cannot identify the calling shell")
            request = transcripts.normalize_uuid(args.request) if args.request is not None else None
            registration = registry.register(paths, args.terminal, args.shell_pid, started,
                                             client.launch_id(), time.time(), request)
            print(registration.token)
        elif args.command == "finish":
            registry.finish(paths, args.token)
        elif args.command == "restore-list":
            choices, notes = restore.choices(paths, ITerm(), args.auto, time.time())
            for note in notes:
                print(note, file=sys.stderr)
            for row in restore.rows(choices):
                print(row)
        elif args.command == "restore-open":
            selected = [line.rstrip("\n") for line in sys.stdin if line.rstrip("\n")]
            first = restore.prepare(paths, ITerm(), selected, os.environ.get("ITERM_SESSION_ID", ""), time.time())
            if first is not None:
                fields = (first.request, first.session.session_id, str(first.session.cwd),
                          str(first.session.codex_home), str(paths.state_dir.parent))
                sys.stdout.write("\0".join(fields) + "\0")
        elif args.command == "restore-cancel":
            restore.cancel(paths, args.request)
        return 0
    except Exception as exc:
        print("codex-sessions: %s" % exc, file=sys.stderr)
        return 1
