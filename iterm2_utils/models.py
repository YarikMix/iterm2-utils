"""Shared data contracts. Builders describe changes without applying them."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Selection:
    agents: frozenset[str]
    features: frozenset[str]
    shortcuts: frozenset[str]
    parent_profile: str
    adopt_legacy: bool = False


@dataclass
class Paths:
    home: Path
    zshrc: Path
    codex_home: Path
    claude_settings: Path
    config: Path
    cache: Path
    data: Path
    profiles: Path
    repo: Path


@dataclass
class Finding:
    feature: str
    agent: str | None
    code: str
    state: str
    message: str


@dataclass
class Context:
    paths: Paths
    executables: dict[str, Path]
    versions: dict[str, str]
    capabilities: frozenset[str]
    profiles: dict[str, dict]
    installed: dict[str, dict]
    preferences: dict[str, dict[str, object]] = field(default_factory=dict)


@dataclass
class FileEdit:
    path: Path
    before: bytes | None
    after: bytes | None
    mode: int
    owner: str


@dataclass
class SymlinkEdit:
    path: Path
    before: str | None
    after: str | None
    owner: str


@dataclass
class PreferenceEdit:
    domain: str
    key: str
    before: object
    after: object
    owner: str


@dataclass
class RegistrationEdit:
    agent: str
    name: str
    before: dict | None
    after: dict | None
    owner: str


@dataclass
class UiStep:
    code: str
    feature: str
    agent: str | None
    instruction: str


@dataclass
class ChangeSet:
    edits: list[FileEdit | SymlinkEdit | PreferenceEdit | RegistrationEdit]
    ui: list[UiStep]
    findings: list[Finding]
    consumers: dict[str, frozenset[str]] = field(default_factory=dict)


@dataclass
class Plan:
    selection: Selection
    changes: ChangeSet
    fingerprint: str


@dataclass
class Receipt:
    version: str
    selection: Selection
    resources: list[dict]
    pending_ui: list[UiStep]


@dataclass
class Outcome:
    receipt: Receipt
    findings: list[Finding]
