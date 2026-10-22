"""Latest interactive invocation owns each pane until explicitly superseded."""
import math
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from . import store, transcripts
from .models import Pane, Paths, Registration, Session


def normalize_terminal(terminal: str) -> str:
    if not isinstance(terminal, str):
        raise ValueError("expected terminal UUID")
    return transcripts.normalize_uuid(terminal.rsplit(":", 1)[-1])


def _session_dict(session: Optional[Session]) -> Optional[dict]:
    if session is None:
        return None
    return {"session_id": session.session_id, "cwd": str(session.cwd),
            "transcript": str(session.transcript), "codex_home": str(session.codex_home)}


def _encode(reg: Registration) -> dict:
    return {"token": reg.token, "terminal": reg.terminal, "shell_pid": reg.shell_pid,
            "shell_started": reg.shell_started, "started_at": reg.started_at,
            "launch": reg.launch, "active": reg.active,
            "session": _session_dict(reg.session), "request": reg.request}


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("expected nonempty string")
    return value


def _decode(value: dict, paths: Paths) -> Registration:
    if not isinstance(value, dict):
        raise ValueError("invalid registration")
    try:
        token = transcripts.normalize_uuid(value["token"])
        terminal = normalize_terminal(value["terminal"])
        pid = value["shell_pid"]
        if type(pid) is not int or pid <= 0:
            raise ValueError("invalid shell PID")
        started = _required_string(value["shell_started"])
        timestamp = value["started_at"]
        if type(timestamp) not in (int, float) or not math.isfinite(timestamp):
            raise ValueError("invalid registration timestamp")
        launch = _required_string(value["launch"])
        if type(value["active"]) is not bool:
            raise ValueError("invalid active state")
        request = value["request"]
        if request is not None:
            _required_string(request)
        raw_session = value["session"]
        session = None
        if raw_session is not None:
            sid = transcripts.normalize_uuid(raw_session["session_id"])
            cwd, transcript, home = [Path(_required_string(raw_session[key]))
                                     for key in ("cwd", "transcript", "codex_home")]
            if not all(path.is_absolute() for path in (cwd, transcript, home)) or home != paths.codex_home:
                raise ValueError("invalid session paths")
            session = Session(sid, cwd, transcript, home)
        return Registration(token, terminal, pid, started, float(timestamp), launch,
                            value["active"], session, request)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("invalid registration schema") from exc


def _load(paths: Paths) -> list[Registration]:
    state = store.read(paths, "registry.json")
    if state is None:
        return []
    if not isinstance(state.get("registrations"), list):
        raise ValueError("invalid registry schema")
    entries = [_decode(item, paths) for item in state["registrations"]]
    if len({reg.terminal for reg in entries}) != len(entries):
        raise ValueError("duplicate pane owners")
    return entries


def _save(paths: Paths, entries: list[Registration]) -> None:
    store.write(paths, "registry.json", {"version": 1, "registrations": [_encode(reg) for reg in entries]})


def _owns_request(reg: Registration, entry: dict) -> bool:
    return (reg.request == entry["request"] and reg.terminal == entry["target"]
            and reg.launch == entry["launch"])


def register(paths: Paths, terminal: str, shell_pid: int, shell_started: str,
             launch: str, now: float, request: Optional[str] = None) -> Registration:
    reg = Registration(str(uuid4()), normalize_terminal(terminal), shell_pid,
                       shell_started, now, launch, True, None, request)
    # Use the same validation for newly created and persisted records.
    reg = _decode(_encode(reg), paths)
    with store.lock(paths, "state.lock"):
        old_entries = _load(paths)
        pending = store.pending(paths)
        pending = [entry for entry in pending if entry["request"] == request
                   or not any(old.terminal == reg.terminal and _owns_request(old, entry)
                              for old in old_entries)]
        for entry in pending:
            if (entry["request"] == request and entry["target"] == reg.terminal
                    and entry["launch"] == launch and entry["status"] in ("reserved", "sent")):
                value = entry["session"]
                session = transcripts.validate(Path(value["transcript"]), value["session_id"],
                                               paths.codex_home, Path(value["cwd"]))
                if session is not None and session.cwd.is_dir():
                    reg.session = session
                    entry["status"] = "acknowledged"
                    entry["token"] = reg.token
        if pending or (paths.state_dir / "pending.json").exists():
            store.save_pending(paths, pending)
        entries = [old for old in old_entries if old.terminal != reg.terminal]
        entries.append(reg)
        _save(paths, entries)
    return reg


def finish(paths: Paths, token: str) -> None:
    with store.lock(paths, "state.lock"):
        entries = _load(paths)
        for reg in entries:
            if reg.token == token:
                reg.active = False
                _save(paths, entries)
                pending = store.pending(paths)
                remaining = [entry for entry in pending if not _owns_request(reg, entry)]
                if remaining != pending:
                    store.save_pending(paths, remaining)
                break


def accept_event(paths: Paths, token: str, terminal: str, event: dict,
                 identity: Callable[[int], Optional[str]], now: float) -> bool:
    if not isinstance(event, dict) or event.get("hook_event_name") not in ("SessionStart", "UserPromptSubmit", "Stop"):
        return False
    try:
        terminal = normalize_terminal(terminal)
        session = transcripts.validate(Path(event["transcript_path"]), event["session_id"],
                                       paths.codex_home, Path(event["cwd"]))
    except (KeyError, ValueError, TypeError):
        return False
    if session is None:
        return False
    with store.lock(paths, "state.lock"):
        entries = _load(paths)
        for reg in entries:
            if reg.token != token or reg.terminal != terminal or not reg.active:
                continue
            if identity(reg.shell_pid) != reg.shell_started or now < reg.started_at:
                return False
            if reg.session is not None and reg.session.session_id != session.session_id:
                return False
            reg.session = session
            _save(paths, entries)
            return True
    return False


def live(paths: Paths, panes: list[Pane], identity: Callable[[int], Optional[str]]) -> list[Registration]:
    terminals = {normalize_terminal(pane.terminal) for pane in panes}
    with store.lock(paths, "state.lock"):
        return [reg for reg in _load(paths)
                if reg.active and reg.session is not None and reg.terminal in terminals
                and identity(reg.shell_pid) == reg.shell_started]
