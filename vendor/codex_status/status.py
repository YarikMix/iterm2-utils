#!/usr/bin/env python3
"""Report Codex lifecycle events to iTerm2 without influencing agent decisions."""

import fcntl
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unicodedata

# Also support importlib-based embedding by the installer and test tools.
# Local adaptation: transport/settings/notification dispatch lives in runtime/hook.py.
# transition() remains testable without external plugin configuration.


EVENTS = (
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest",
    "PostToolUse", "PreCompact", "PostCompact", "SubagentStart",
    "SubagentStop", "Stop", "Interrupt", "SessionEnd",
)
COLORS = {"working": "#e5a950", "waiting": "#e06c75", "idle": "#98c379", "": ""}
INPUT_TOOLS = {"request_user_input", "request_user_input_async"}


def terminal_id(value):
    """Accept iTerm's w0t0p0:UUID form, but never the implicit active session."""
    candidate = value.rsplit(":", 1)[-1]
    if re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", candidate):
        return candidate.upper()
    return None


def clean(value, limit=80):
    value = "".join(c for c in str(value or "") if unicodedata.category(c) not in {"Cc", "Cf"} or c in "\n\r\t")
    return " ".join(value.split())[:limit]


def tool_key(event):
    # Local adapter supplies an opaque canonical identity computed in memory.
    # Keep neither prompts nor tool arguments in the status cache.
    if isinstance(event.get("tool_key"), str):
        return event["tool_key"]
    tool = event.get("tool_name")
    payload = event.get("tool_input")
    # PermissionRequest adds a description that PostToolUse omits. The shell or
    # patch command is the stable identifier across those two event shapes.
    if tool in {"Bash", "apply_patch", "Edit", "Write"} and isinstance(payload, dict) and "command" in payload:
        payload = {"command": payload["command"]}
    raw = json.dumps([tool, payload], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def transition(previous, event):
    """Return new state, or None for an event that does not own this terminal."""
    name = event.get("hook_event_name")
    sid = event.get("session_id")
    if name not in EVENTS or not isinstance(sid, str) or not sid:
        return None
    state = dict(previous)
    if state.get("session_id") == sid and state.get("event") == "SessionEnd" and name not in {"SessionStart", "UserPromptSubmit"}:
        return None
    if state.get("session_id") != sid:
        if state and name not in {"SessionStart", "UserPromptSubmit"}:
            return None
        state = {"session_id": sid, "working": False, "agents": [], "waiting": {}}
    if name == "SessionStart" and event.get("source") != "compact":
        state.update(working=False, agents=[], waiting={}, turn_id=None)
    turn = event.get("turn_id")
    if name == "UserPromptSubmit" and isinstance(turn, str):
        state["turn_id"] = turn
    elif name in {"Stop", "Interrupt", "PreCompact", "PostCompact"} and turn and state.get("turn_id") and turn != state["turn_id"]:
        return None
    state["agents"] = list(state.get("agents", []))
    state["waiting"] = dict(state.get("waiting", {}))
    state["project"] = clean(Path(event.get("cwd") or ".").name)
    state["event"] = name
    state["updated_at"] = time.time()
    agent = event.get("agent_id")
    tool = clean(event.get("tool_name"), 50)

    if name == "UserPromptSubmit":
        state.update(working=True, waiting={})
    elif name in {"PreCompact", "PostCompact"}:
        state["working"] = True
    elif name == "SessionStart" and event.get("source") == "compact":
        state["working"] = True
    elif name == "PreToolUse":
        state["working"] = True
        if tool in INPUT_TOOLS:
            add_waiting(state, event, "Input needed")
    elif name == "PermissionRequest":
        add_waiting(state, event, "Approval needed" + (f" ({tool})" if tool else ""))
    elif name == "PostToolUse":
        key = tool_key(event)
        pending = state["waiting"].get(key)
        if isinstance(pending, dict) and pending.get("count", 1) > 1:
            state["waiting"][key] = dict(pending, count=pending["count"] - 1)
        else:
            state["waiting"].pop(key, None)
    elif name == "SubagentStart" and isinstance(agent, str) and agent not in state["agents"]:
        state["agents"].append(agent)
    elif name == "SubagentStop" and agent in state["agents"]:
        state["agents"].remove(agent)
    elif name == "Stop":
        state.update(working=False, waiting={})
    elif name in {"Interrupt", "SessionEnd"}:
        state.update(working=False, waiting={}, agents=[])

    if name == "SessionEnd":
        status, detail = "", ""
    elif state["waiting"]:
        pending = next(iter(state["waiting"].values()))
        description = pending["detail"] if isinstance(pending, dict) else pending
        status, detail = "waiting", "Codex · " + description
    elif state["working"] or state["agents"]:
        status, detail = "working", "Codex · " + state["project"]
        if state["agents"]:
            detail += f" · {len(state['agents'])} subagent(s)"
    else:
        status, detail = "idle", "Codex · " + state["project"]
    state.update(status=status, detail=detail)
    return state


def add_waiting(state, event, detail):
    key = tool_key(event)
    previous = state["waiting"].get(key)
    count = previous.get("count", 1) if isinstance(previous, dict) else (1 if previous else 0)
    state["waiting"][key] = {"detail": detail, "count": count + 1}


@contextmanager
def locked(path, timeout):
    with os.fdopen(os.open(path, os.O_CREAT | os.O_RDWR, 0o600), "w") as lock:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Status lock is busy")
                time.sleep(0.01)
        yield


def read_state(path):
    try:
        state = json.loads(path.read_text())
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(path, state):
    fd, tmp = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(state, output)
            output.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

