"""Deliver allowlisted Codex events to the selected bundle's native status writer."""
import copy
import os
from pathlib import Path
import subprocess
import time

try:
    from events import CODEX_EVENTS, Event, identifier, terminal_from_environment, terminal_id
except ImportError:
    from .events import CODEX_EVENTS, Event, identifier, terminal_from_environment, terminal_id
from vendor.codex_status import status


PHASE_SECONDS = 1.8
LOCK_SECONDS = 0.4
CLEANUP_SECONDS = 0.15


def prepare_payload(event: Event, raw: dict) -> dict | None:
    if event.agent != 'codex' or event.name not in CODEX_EVENTS:
        return None
    if event.name == 'PreToolUse' and event.tool_name in {'request_user_input', 'request_user_input_async'}:
        return {'hook_event_name': 'Notification',
                'notification_type': 'elicitation_dialog', 'message': 'Input needed'}
    if event.name in {'PreCompact', 'PostCompact'}:
        return {'hook_event_name': 'PreToolUse' if event.name == 'PreCompact' else 'PostToolUse'}
    if event.name == 'SessionStart' and event.source == 'compact':
        return {'hook_event_name': 'PreToolUse'}
    payload = {'hook_event_name': event.name}
    if event.tool_name:
        payload['tool_name'] = event.tool_name
    if event.agent_id:
        payload['agent_id'] = event.agent_id
    for key in ('notification_type', 'message'):
        if isinstance(raw.get(key), str):
            payload[key] = raw[key]
    if event.name == 'PermissionRequest' and isinstance(raw.get('tool_input'), dict):
        payload['tool_input'] = copy.deepcopy(raw['tool_input'])
    if event.name == 'Stop' and isinstance(raw.get('last_assistant_message'), str):
        payload['last_assistant_message'] = raw['last_assistant_message']
    if isinstance(raw.get('background_tasks'), list):
        payload['background_tasks'] = [
            {key: task[key] for key in ('id', 'status') if isinstance(task.get(key), str)}
            for task in raw['background_tasks'] if isinstance(task, dict)]
    return payload


def prepare_environment(event: Event, environment: dict[str, str]) -> dict[str, str] | None:
    terminal = terminal_from_environment(environment)
    if not terminal or terminal != event.terminal_uuid or environment.get('TMUX'):
        return None
    result = dict(environment)
    result['TERM_SESSION_ID'] = result['ITERM_SESSION_ID'] = 'w0t0p0:'+terminal
    return result


def _admit(event: Event, previous: dict, *, exists: bool) -> dict | None:
    """Identity only: no native status, waiting queue or background counters."""
    compact = event.name in {'PreCompact', 'PostCompact'} or (
        event.name == 'SessionStart' and event.source == 'compact')
    boundary = event.name == 'UserPromptSubmit' or (event.name == 'SessionStart' and not compact)
    valid = (set(previous) == {'session_id', 'turn_id', 'ended'}
             and identifier(previous['session_id']) is not None
             and (previous['turn_id'] is None or identifier(previous['turn_id']) is not None)
             and type(previous['ended']) is bool)
    if exists and not valid and not boundary:
        # Corrupt ownership is not permission to end an arbitrary native session.
        return None
    if valid and not boundary:
        if previous['session_id'] != event.session_id or previous['ended']:
            return None
        if (compact or event.name in {'Stop', 'Interrupt'}) and (
                event.turn_key and previous['turn_id'] and event.turn_key != previous['turn_id']):
            return None
    if boundary or not valid:
        identity = {'session_id': event.session_id, 'turn_id': event.turn_key, 'ended': False}
    else:
        identity = dict(previous)
    if event.name == 'SessionEnd':
        identity['ended'] = True
    return identity


def forward(event: Event, raw: dict, settings: dict, runner,
            *, environment: dict[str, str], deadline: float) -> str:
    import json
    phase_deadline = min(deadline, time.monotonic()+PHASE_SECONDS)
    if not settings.get('status') or settings.get('status_backend') != 'cc-status':
        return 'ignored'
    payload = prepare_payload(event, raw)
    env = prepare_environment(event, environment)
    if payload is None or env is None:
        return 'ignored'
    if 'terminal_uuid' in raw and terminal_id(raw['terminal_uuid']) != event.terminal_uuid:
        return 'ignored'
    try:
        app = Path(settings['iterm2_app'])
        cache = Path(settings['native_identity_cache'])
        if not app.is_absolute() or not cache.is_absolute():
            return 'unavailable'
        utilities = app/'Contents/Resources/utilities'
        native = utilities/'cc-status'
        if not all(path.is_file() and os.access(path, os.X_OK)
                   for path in (native, utilities/'it2')):
            return 'unavailable'
        if phase_deadline-time.monotonic() <= CLEANUP_SECONDS:
            return 'timeout'
        cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = cache/(event.terminal_uuid+'.json')
        lock_timeout = min(LOCK_SECONDS, phase_deadline-time.monotonic()-CLEANUP_SECONDS)
        if lock_timeout <= 0:
            return 'timeout'
        with status.locked(cache/(event.terminal_uuid+'.lock'), lock_timeout):
            previous = status.read_state(path)
            identity = _admit(event, previous, exists=path.exists())
            if identity is None:
                return 'ignored'
            if phase_deadline-time.monotonic() <= CLEANUP_SECONDS:
                return 'timeout'
            status.write_state(path, identity)
            remaining = phase_deadline-time.monotonic()-CLEANUP_SECONDS
            if remaining <= 0:
                return 'timeout'
            result = runner.run([str(native), '--agent', 'codex'], timeout=remaining,
                                stdin=json.dumps(payload), env=env)
            return 'sent' if result.returncode == 0 else 'failed'
    except (TimeoutError, subprocess.TimeoutExpired):
        return 'timeout'
    except (OSError, KeyError, TypeError, ValueError):
        return 'failed'
