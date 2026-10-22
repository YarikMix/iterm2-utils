"""Select a previous launch and coordinate explicitly reserved resume requests."""
from pathlib import Path
import re
import shlex
import sys
import time
import unicodedata
from typing import Optional
from uuid import uuid4

from . import registry, snapshots, store, transcripts
from .iterm import ITerm, UnknownTabOutcome
from .models import Choice, FirstResume, Paths, Session


def _prune(paths, entries, panes, launch):
    terminals = {registry.normalize_terminal(pane.terminal) for pane in panes}
    return [entry for entry in entries if entry["launch"] == launch
            and (entry["target"] or entry["source"]) in terminals]


def _claim(paths, current, previous, processed=False):
    state = store.read(paths, "auto.json") or {"version": 1, "claims": []}
    claims = state.get("claims")
    if (not isinstance(claims, list) or any(not isinstance(claim, list) or len(claim) != 2
            or any(not isinstance(value, str) or not value for value in claim) for claim in claims)):
        raise ValueError("invalid auto claims")
    key = [current, previous]
    available = not any(claim[0] == current or claim[1] == previous for claim in claims)
    if (available or processed) and key not in claims:
        store.write(paths, "auto.json", {"version": 1, "claims": claims + [key]})
    return available


def choices(paths: Paths, client: ITerm, auto: bool, now: float) -> tuple[list[Choice], list[str]]:
    with store.lock(paths, "state.lock"):
        before_inventory = store.pending(paths)
    launch, panes = client.launch_id(), client.panes()
    snapshot = snapshots.candidate(paths, launch)
    if snapshot is None:
        return [], []
    opened = {reg.session.session_id for reg in registry.live(paths, panes, client.identity)}
    with store.lock(paths, "state.lock"):
        pending = store.pending(paths)
        # A coordinator may create a target after this inventory was observed.
        # Only unchanged reservations can be cleaned using that observation.
        remaining = _prune(paths, pending, panes, launch) if pending == before_inventory else pending
        if pending != remaining:
            store.save_pending(paths, remaining)
        opened.update(entry["session"]["session_id"] for entry in remaining)
        if auto and not _claim(paths, launch, snapshot.launch):
            return [], []
    result, notes, seen = [], [], set()
    for tab in snapshot.tabs:
        session = tab.session
        if session.session_id in opened or session.session_id in seen:
            continue
        seen.add(session.session_id)
        validated = transcripts.validate(session.transcript, session.session_id, paths.codex_home, session.cwd)
        if validated is None or not validated.cwd.is_dir():
            notes.append("Пропущена недоступная сессия " + session.session_id)
            continue
        try:
            minutes = max(0, int((now - validated.transcript.stat().st_mtime) // 60))
        except OSError:
            notes.append("Пропущен недоступный журнал " + session.session_id)
            continue
        age = "%s мин" % minutes if minutes < 60 else "%s ч" % (minutes // 60) if minutes < 1440 else "%s д" % (minutes // 1440)
        result.append(Choice(tab.order, validated, transcripts.title(validated), age))
    return result, notes


def _visible(value):
    value = re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))", "", value)
    return " ".join("".join(character if not unicodedata.category(character).startswith("C") else " "
                             for character in value).split())


def rows(choices: list[Choice]) -> list[str]:
    return ["\t".join([str(index), transcripts.normalize_uuid(choice.session.session_id),
                       "%s.%s" % choice.order, _visible(choice.title),
                       _visible(choice.session.cwd.name), _visible(choice.age)])
            for index, choice in enumerate(choices, 1)]


def command(session: Session, request: str, cache_root: Path) -> str:
    sid, request = transcripts.normalize_uuid(session.session_id), transcripts.normalize_uuid(request)
    return "cd -- %s && CODEX_HOME=%s CODEX_RESTORE_CACHE_DIR=%s CODEX_RESTORE_REQUEST=%s codex resume %s" % (
        shlex.quote(str(session.cwd)), shlex.quote(str(session.codex_home)), shlex.quote(str(cache_root)),
        shlex.quote(request), shlex.quote(sid))


def cancel(paths: Paths, request: str) -> None:
    request = transcripts.normalize_uuid(request)
    with store.lock(paths, "state.lock"):
        pending = store.pending(paths)
        remaining = [entry for entry in pending if entry["request"] != request or entry["status"] != "reserved"]
        if remaining != pending:
            store.save_pending(paths, remaining)


def _update(paths, request, target, status):
    with store.lock(paths, "state.lock"):
        entries = store.pending(paths)
        for entry in entries:
            if entry["request"] == request and entry["status"] != "acknowledged":
                entry.update(target=target, status=status)
        store.save_pending(paths, entries)


def _acknowledged(paths, request):
    with store.lock(paths, "state.lock"):
        return any(entry["request"] == request and entry["status"] == "acknowledged"
                   for entry in store.pending(paths))


def prepare(paths: Paths, client: ITerm, selected_ids: list[str], caller_terminal: str,
            now: float) -> Optional[FirstResume]:
    if not selected_ids:
        return None
    selected = [transcripts.normalize_uuid(sid) for sid in selected_ids]
    if len(set(selected)) != len(selected):
        raise ValueError("duplicate selected UUID")
    caller = registry.normalize_terminal(caller_terminal)
    with store.lock(paths, "restore.lock"):
        launch = client.launch_id()
        panes = client.panes()
        sources = [pane for pane in panes if registry.normalize_terminal(pane.terminal) == caller]
        if len(sources) != 1:
            raise ValueError("Не найдено окно исходной панели iTerm2")
        snapshot = snapshots.candidate(paths, launch)
        if snapshot is None:
            return None
        known = {tab.session.session_id for tab in snapshot.tabs}
        if not set(selected).issubset(known):
            raise ValueError("selected UUID is absent from the snapshot")
        available, notes = choices(paths, client, False, now)
        for note in notes:
            print(note, file=sys.stderr)
        chosen = [choice.session for choice in available if choice.session.session_id in selected]
        if not chosen:
            return None
        if client.launch_id() != launch:
            raise ValueError("iTerm2 launch changed")
        with store.lock(paths, "state.lock"):
            pending = store.pending(paths)
            # Registry's public live() owns this lock. Read its wire under the
            # already held lock to make the final check and reservation atomic.
            terminals = {registry.normalize_terminal(pane.terminal) for pane in panes}
            busy = {reg.session.session_id for reg in registry._load(paths)
                    if reg.active and reg.session is not None and reg.terminal in terminals
                    and client.identity(reg.shell_pid) == reg.shell_started}
            busy.update(entry["session"]["session_id"] for entry in pending)
            chosen = [session for session in chosen if session.session_id not in busy]
            if not chosen:
                return None
            reservations = [{"request": str(uuid4()), "session": registry._session_dict(session),
                             "source": caller, "target": caller if index == 0 else None,
                             "launch": launch, "status": "reserved"}
                            for index, session in enumerate(chosen)]
            store.save_pending(paths, pending + reservations)
            _claim(paths, launch, snapshot.launch, processed=True)
        try:
            for session, entry in zip(chosen[1:], reservations[1:]):
                request = entry["request"]
                try:
                    target = client.new_tab(sources[0].window_id)
                except UnknownTabOutcome:
                    # Retain source-bound reservation: never create another tab
                    # automatically after a request whose outcome is unknown.
                    print("Исход открытия неизвестен: %s. Проверьте вкладки iTerm2; автоматический повтор запрещён." % session.session_id, file=sys.stderr)
                    continue
                except Exception as exc:
                    cancel(paths, request)
                    print("Не удалось открыть вкладку %s: %s. Вручную: %s" % (
                        session.session_id, exc, command(session, request, paths.state_dir.parent)), file=sys.stderr)
                    continue
                # Persist before sending: even a lost reply cannot cause a duplicate launch.
                _update(paths, request, registry.normalize_terminal(target), "sent")
                try:
                    client.run(target, command(session, request, paths.state_dir.parent))
                except Exception:
                    pass
                deadline = time.monotonic() + 3.0
                while not _acknowledged(paths, request) and time.monotonic() < deadline:
                    time.sleep(min(0.1, max(0, deadline - time.monotonic())))
                if not _acknowledged(paths, request):
                    print("Запуск не подтверждён: %s. Проверьте вкладку; вручную: %s" % (
                        session.session_id, command(session, request, paths.state_dir.parent)), file=sys.stderr)
        finally:
            try:
                client.focus(caller)
            except Exception as exc:
                print("Не удалось вернуть фокус: %s" % exc, file=sys.stderr)
        return FirstResume(reservations[0]["request"], chosen[0])
