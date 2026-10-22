"""Shared runtime models (Python 3.9+)."""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Paths:
    codex_home: Path
    state_dir: Path


@dataclass
class Session:
    session_id: str
    cwd: Path
    transcript: Path
    codex_home: Path


@dataclass
class Registration:
    token: str
    terminal: str
    shell_pid: int
    shell_started: str
    started_at: float
    launch: str
    active: bool
    session: Optional[Session]
    request: Optional[str]


@dataclass
class Pane:
    terminal: str
    tab_id: str
    window_id: str
    window_no: int
    tab_no: int


@dataclass
class SavedTab:
    order: tuple[int, int]
    session: Session


@dataclass
class Snapshot:
    launch: str
    saved_at: float
    tabs: list[SavedTab]
    version: int = 1


@dataclass
class Choice:
    order: tuple[int, int]
    session: Session
    title: str
    age: str


@dataclass
class FirstResume:
    request: str
    session: Session
