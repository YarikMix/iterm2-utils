"""Normalize an event in memory. No transcript reads or raw event persistence."""
from dataclasses import dataclass
import re
import hashlib
import json
try:
    from vendor.codex_status.status import EVENTS, terminal_id
except ImportError:
    from .vendor.codex_status.status import EVENTS, terminal_id

@dataclass(frozen=True)
class Event:
    agent: str
    name: str
    session_id: str
    terminal_uuid: str
    turn_key: str | None
    tool_name: str | None
    notification_type: str | None
    background_running: bool
    tool_key: str | None = None
    source: str | None = None
    agent_id: str | None = None
    stop_hook_active: bool = False
    notification_key: str | None = None


def identifier(value):
    return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,200}',value) else None


def normalize(raw: dict, agent: str, terminal_env: str | None) -> Event | None:
    if not isinstance(raw,dict) or agent not in {'codex','claude'}:
        return None
    terminal=terminal_id(terminal_env or '')
    supplied=raw.get('terminal_uuid')
    if not terminal or (supplied is not None and terminal_id(str(supplied)) != terminal):
        return None
    sid=identifier(raw.get('session_id'))
    name=raw.get('hook_event_name')
    if not sid or name not in (*EVENTS,'Notification','StopFailure','PostToolUseFailure'):
        return None
    source=raw.get('source')
    if source not in {'startup','resume','clear','compact'}:
        source=None
    # Preserve upstream pairing when permission events omit tool IDs; raw payload
    # exists only in this stack frame. Command-only canonicalization intentionally
    # ignores the permission-only description field.
    tool=raw.get('tool_name'); payload=raw.get('tool_input')
    if tool in {'Bash','apply_patch','Edit','Write'} and isinstance(payload,dict) and 'command' in payload:
        payload={'command':payload['command']}
    digest=hashlib.sha256(json.dumps([tool,payload],sort_keys=True).encode()).hexdigest()
    # Notification schema has message/title/type but no per-request ID. Keep
    # only its opaque identity, never presentation strings, beyond this frame.
    notification_key=None
    if agent=='claude' and name=='Notification':
        values=[raw.get(key) if isinstance(raw.get(key),str) else '' for key in ('notification_type','title','message')]
        notification_key=hashlib.sha256(json.dumps(values).encode()).hexdigest()
    # Official SDK: the list contains in-flight work, irrespective of its free
    # status string. Unknown nonempty shapes conservatively suppress completion.
    return Event(agent,name,sid,terminal,identifier(raw.get('prompt_id') if agent == 'claude' else raw.get('turn_id')),identifier(raw.get('tool_name')),
                 identifier(raw.get('notification_type')),(raw.get('background_running') is True or bool(raw.get('background_tasks'))),
                 digest,source,
                 identifier(raw.get('agent_id')), raw.get('stop_hook_active') is True, notification_key)
