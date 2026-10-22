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
    agent_features: dict[str, list[str]] | None = None
    agent_shortcuts: dict[str, list[str]] | None = None
    coexist_notifications: bool = False
    notification_coexist_agents: list[str] | None = None

    def coexist_for(self, agent):
        return (agent in self.notification_coexist_agents if self.notification_coexist_agents is not None
                else self.coexist_notifications and agent in self.agents)

    def features_for(self, agent):
        values = self.features if self.agent_features is None else self.agent_features.get(agent, ())
        return frozenset(values) & self.features if agent in self.agents else frozenset()

    def shortcuts_for(self, agent):
        values = self.shortcuts if self.agent_shortcuts is None else self.agent_shortcuts.get(agent, ())
        return frozenset(values) & self.shortcuts if 'shortcuts' in self.features_for(agent) else frozenset()

    def agents_for(self, feature):
        return frozenset(a for a in self.agents if feature in self.features_for(a)
                         and (feature not in {'clipboard', 'restore'} or a == 'codex'))

    @property
    def pairs(self):
        return frozenset(a+':'+f for f in self.features for a in self.agents_for(f))

    def explicit(self):
        from dataclasses import replace
        features = {a: sorted(f for f in self.features_for(a)
                    if f not in {'clipboard', 'restore'} or a == 'codex') for a in self.agents}
        shortcuts = {a: sorted(self.shortcuts_for(a)) for a in self.agents}
        return replace(self, agent_features=features, agent_shortcuts=shortcuts)

    def merge(self, other, features):
        from dataclasses import replace
        own, new = self.explicit(), other.explicit()
        agents = own.agents | new.agents
        pairs = {a: sorted(own.features_for(a) | (new.features_for(a) & features)) for a in agents}
        keys = {a: sorted(own.shortcuts_for(a) | (new.shortcuts_for(a) if 'shortcuts' in features else set())) for a in agents}
        return replace(other, agents=agents, features=frozenset(f for fs in pairs.values() for f in fs),
                       shortcuts=frozenset(k for ks in keys.values() for k in ks),
                       agent_features=pairs, agent_shortcuts=keys,
                       coexist_notifications=self.coexist_notifications or other.coexist_notifications,
                       notification_coexist_agents=sorted(a for a in agents if own.coexist_for(a) or
                           ('notifications' in features and a in new.agents_for('notifications') and new.coexist_for(a))))

    def without(self, features, agents):
        from dataclasses import replace
        own = self.explicit()
        pairs = {a: sorted(own.features_for(a) - (features if a in agents else set())) for a in own.agents}
        keys = {a: sorted(own.shortcuts_for(a)) if 'shortcuts' in pairs[a] else [] for a in own.agents}
        return replace(own, features=frozenset(f for fs in pairs.values() for f in fs),
                       shortcuts=frozenset(k for ks in keys.values() for k in ks),
                       agent_features=pairs, agent_shortcuts=keys,
                       notification_coexist_agents=sorted(a for a in own.agents if own.coexist_for(a) and 'notifications' in pairs[a]))


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
    ui_snapshots: dict[str, list[dict]] = field(default_factory=dict)


@dataclass
class Outcome:
    receipt: Receipt
    findings: list[Finding]


def resource_pairs(selection, feature, target, context, shared=None):
    """Resolve legacy feature ownership to its actual consumers, never new agents."""
    agents = selection.agents_for(feature)
    target = str(Path(target).resolve()) if target and Path(target).is_absolute() else str(target)
    if target == 'claude' or target == str(context.paths.claude_settings.resolve()):
        agents &= {'claude'}
    elif target == 'codex' or target in {str((context.paths.codex_home/name).resolve()) for name in ('config.toml','hooks.json')} or feature in {'clipboard','restore'}:
        agents &= {'codex'}
    elif shared == 'shared:shell' and feature != 'shell':
        agents &= {'codex'}
    elif shared in {'shared:hooks', 'shared:codex-hooks'}:
        agents &= {'codex','claude'} if feature == 'notifications' else {'codex'}
    return frozenset(a+':'+feature for a in agents)
