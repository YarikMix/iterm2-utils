"""Private, atomic state files; callers serialize their own versioned schemas."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Optional

from .models import Paths
from . import transcripts


def paths(codex_home: Path, cache_root: Path) -> Paths:
    home = codex_home.expanduser().resolve()
    partition = hashlib.sha256(os.fsencode(home)).hexdigest()
    return Paths(home, cache_root.expanduser().resolve() / partition)


def _directory(paths: Paths) -> None:
    paths.state_dir.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    paths.state_dir.parent.chmod(0o700)
    paths.state_dir.mkdir(mode=0o700, exist_ok=True)
    paths.state_dir.chmod(0o700)


def _file(paths: Paths, name: str) -> Path:
    if not name or Path(name).name != name or name in (".", ".."):
        raise ValueError("state filename must be a basename")
    return paths.state_dir / name


@contextmanager
def lock(paths: Paths, name: str):
    """Serialize state mutations with at most one second of contention wait."""
    _directory(paths)
    fd = os.open(_file(paths, name), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(fd, 0o600)
        deadline = time.monotonic() + 1.0
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("timed out waiting for state lock")
                time.sleep(0.01)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _validate(value: object) -> dict:
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
        raise ValueError("unsupported state schema")
    return value


def read(paths: Paths, name: str) -> Optional[dict]:
    try:
        with _file(paths, name).open(encoding="utf-8") as stream:
            return _validate(json.load(stream))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("invalid state JSON") from exc


def write(paths: Paths, name: str, value: dict) -> None:
    _validate(value)
    target = _file(paths, name)
    _directory(paths)
    fd, temporary = tempfile.mkstemp(prefix="." + name + "-", dir=paths.state_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, ensure_ascii=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def pending(paths: Paths) -> list[dict]:
    """Read shared reservation wire data. Caller holds state.lock."""
    value = read(paths, "pending.json")
    if value is None:
        return []
    entries = value.get("pending")
    if not isinstance(entries, list):
        raise ValueError("invalid pending schema")
    requests, sessions = set(), set()
    for entry in entries:
        try:
            request = transcripts.normalize_uuid(entry["request"])
            session = entry["session"]
            sid = transcripts.normalize_uuid(session["session_id"])
            for key in ("source", "target"):
                if entry[key] is not None:
                    transcripts.normalize_uuid(entry[key])
            if (request in requests or sid in sessions or entry["status"] not in
                    ("reserved", "sent", "acknowledged") or not isinstance(entry["launch"], str)
                    or not entry["launch"] or entry["source"] is None
                    or any(not isinstance(session[key], str) or not Path(session[key]).is_absolute()
                           for key in ("cwd", "transcript", "codex_home"))
                    or Path(session["codex_home"]) != paths.codex_home):
                raise ValueError("invalid pending entry")
            requests.add(request)
            sessions.add(sid)
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("invalid pending entry") from exc
    return entries


def save_pending(paths: Paths, entries: list[dict]) -> None:
    """Publish reservations while holding state.lock."""
    write(paths, "pending.json", {"version": 1, "pending": entries})
