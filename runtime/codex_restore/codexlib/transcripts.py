"""Validate only transcript headers; read conversation text only for display."""
import json
from pathlib import Path
from typing import Optional
from uuid import UUID

from .models import Session


def normalize_uuid(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("expected UUID string")
    return str(UUID(value))


def validate(path: Path, session_id: str, codex_home: Path, cwd: Path) -> Optional[Session]:
    try:
        sid = normalize_uuid(session_id)
        home = codex_home.resolve()
        if not path.is_absolute() or not cwd.is_absolute():
            return None
        resolved = path.resolve()
        resolved.relative_to((home / "sessions").resolve())
        # Also require the resolved sessions directory to stay in CODEX_HOME.
        resolved.relative_to(home / "sessions")
        with resolved.open(encoding="utf-8") as stream:
            header = json.loads(stream.readline())
        if not isinstance(header, dict) or header.get("type") != "session_meta":
            return None
        payload = header.get("payload")
        if not isinstance(payload, dict):
            return None
        ids = [payload[key] for key in ("id", "session_id") if key in payload]
        if not ids or any(normalize_uuid(value) != sid for value in ids):
            return None
        if payload.get("source") != "cli" or payload.get("originator") != "codex-tui":
            return None
        header_cwd = Path(payload["cwd"])
        if not header_cwd.is_absolute():
            return None
        # The header describes the original launch; resume -C may change cwd.
        return Session(sid, cwd.resolve(), resolved, home)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        return None


def _text(payload: dict) -> str:
    content = payload.get("content")
    metadata = payload.get("internal_chat_message_metadata_passthrough")
    kinds = metadata.get("content_item_kinds") if isinstance(metadata, dict) else None
    has_metadata = "internal_chat_message_metadata_passthrough" in payload
    if isinstance(content, str):
        blocks = [{"type": "input_text", "text": content}]
    elif isinstance(content, list):
        blocks = content
    else:
        return ""
    accepted = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or block.get("type") != "input_text":
            continue
        text = block.get("text")
        if not isinstance(text, str):
            continue
        if has_metadata:
            if not isinstance(kinds, list) or index >= len(kinds) or kinds[index] != "user.text":
                continue
        elif text.lstrip().startswith(("# AGENTS.md instructions", "<environment_context>", "<skill>")):
            continue
        accepted.append(text)
    return " ".join(" ".join(accepted).split())


def title(session: Session) -> str:
    try:
        with session.transcript.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(item, dict) or item.get("type") != "response_item":
                    continue
                payload = item.get("payload")
                if not isinstance(payload, dict) or payload.get("type") != "message" or payload.get("role") != "user":
                    continue
                text = _text(payload)
                if text:
                    return text[:120]
    except (OSError, UnicodeError):
        pass
    return session.session_id[:8]
