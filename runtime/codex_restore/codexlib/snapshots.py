"""Publish only complete inventories built from an unchanged registry version."""
import math
from pathlib import Path
from typing import Optional

from . import registry, store, transcripts
from .iterm import ITerm
from .models import Paths, SavedTab, Session, Snapshot


def _encode(snapshot: Snapshot) -> dict:
    return {"version": snapshot.version, "launch": snapshot.launch, "saved_at": snapshot.saved_at,
            "tabs": [{"order": list(tab.order), "session": {
                "session_id": tab.session.session_id, "cwd": str(tab.session.cwd),
                "transcript": str(tab.session.transcript), "codex_home": str(tab.session.codex_home)}}
                     for tab in snapshot.tabs]}


def _decode(value: dict, paths: Paths) -> Snapshot:
    try:
        launch, timestamp, tabs = value["launch"], value["saved_at"], value["tabs"]
        if (not isinstance(launch, str) or not launch or type(timestamp) not in (int, float)
                or not math.isfinite(timestamp) or not isinstance(tabs, list)):
            raise ValueError("invalid snapshot metadata")
        result = []
        for tab in tabs:
            order, session = tab["order"], tab["session"]
            if (not isinstance(order, list) or len(order) != 2
                    or any(type(number) is not int or number < 1 for number in order)):
                raise ValueError("invalid tab order")
            sid = transcripts.normalize_uuid(session["session_id"])
            directories = [Path(session[key]) for key in ("cwd", "transcript", "codex_home")]
            if not all(directory.is_absolute() for directory in directories) or directories[2] != paths.codex_home:
                raise ValueError("invalid snapshot paths")
            result.append(SavedTab(tuple(order), Session(sid, *directories)))
        if [tab.order for tab in result] != sorted({tab.order for tab in result}):
            raise ValueError("duplicate or unordered tabs")
        return Snapshot(launch, float(timestamp), result)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("invalid snapshot schema") from exc


def capture(paths: Paths, client: ITerm, now: float,
            required_terminal: Optional[str] = None,
            required_token: Optional[str] = None) -> bool:
    """A hook requires its source registration to remain a live pane owner."""
    try:
        if type(now) not in (int, float) or not math.isfinite(now):
            return False
        launch = client.launch_id()
        if not launch:
            return False
        panes = client.panes()
        if required_terminal is not None and registry.normalize_terminal(required_terminal) not in {
                registry.normalize_terminal(pane.terminal) for pane in panes}:
            return False
        with store.lock(paths, "state.lock"):
            version = (paths.state_dir / "registry.json").read_bytes()
        owners = registry.live(paths, panes, client.identity)
        if required_terminal is not None or required_token is not None:
            if not any(owner.launch == launch
                       and (required_terminal is None or owner.terminal == registry.normalize_terminal(required_terminal))
                       and (required_token is None or owner.token == required_token)
                       for owner in owners):
                return False
        leaders = {}
        positions = {registry.normalize_terminal(pane.terminal): pane for pane in panes}
        for owner in owners:
            if owner.launch != launch:
                continue
            pane = positions[owner.terminal]
            key = (pane.window_no, pane.tab_no)
            if key not in leaders or owner.started_at < leaders[key].started_at:
                leaders[key] = owner
        snapshot = Snapshot(launch, now, [SavedTab(order, leaders[order].session)
                                         for order in sorted(leaders)])
        if client.launch_id() != launch:
            return False
        with store.lock(paths, "state.lock"):
            # No public registry API may be called while this lock is held.
            if (paths.state_dir / "registry.json").read_bytes() != version:
                return False
            current = store.read(paths, "tabs.json")
            if current is not None:
                old = _decode(current, paths)
                if old.saved_at > now:
                    return False
                if old.launch != launch:
                    store.write(paths, "tabs-prev.json", current)
            store.write(paths, "tabs.json", _encode(snapshot))
        return True
    except Exception:
        # A broken external adapter must never destroy the last good snapshot.
        return False


def candidate(paths: Paths, current_launch: str) -> Optional[Snapshot]:
    for name in ("tabs.json", "tabs-prev.json"):
        try:
            value = store.read(paths, name)
            if value is not None:
                snapshot = _decode(value, paths)
                if snapshot.launch != current_launch:
                    return snapshot
        except (OSError, ValueError, TypeError):
            continue
    return None
