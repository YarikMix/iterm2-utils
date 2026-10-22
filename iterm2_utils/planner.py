"""Validate explicit choices and produce a read-only readiness preview."""
import hashlib
import json
from dataclasses import replace

from .models import ChangeSet, Context, Finding, Plan, Selection, UiStep

AGENTS = frozenset({'codex', 'claude'})
FEATURES = frozenset({'clipboard', 'status', 'notifications', 'restore', 'mcp', 'shell', 'shortcuts'})
SHORTCUTS = frozenset({'ctrl-v-ru', 'alt-enter', 'ctrl-q', 'resume'})
CODEX_ONLY = frozenset({'clipboard', 'restore'})
DESCRIPTIONS = {
    'clipboard': 'Codex-only profile (&codex); tui.copy_on_select = "never"; shared iTerm2 CopySelection = false.',
    'status': 'Session status for explicit tab UUIDs; Claude uses native cc-status integration.',
    'notifications': 'macOS notifications via terminal-notifier; separate from visible statuses.',
    'restore': 'Codex-only conversation chooser; never launches conversations without selection.',
    'mcp': 'Separate MCP runtime: mcp-server-iterm2==0.1.1, mcp<2. Gives access to terminal text.',
    'shell': 'Official zsh shell integration, restricted to iTerm2.',
    'shortcuts': 'Only explicitly selected shortcuts in agent profiles; ctrl-q can interrupt/exit.',
}


def validate(selection: Selection, context: Context) -> list[Finding]:
    findings = []

    def add(feature, agent, code, state, message):
        findings.append(Finding(feature, agent, code, state, message))

    if not selection.agents or selection.agents - AGENTS:
        add('selection', None, 'invalid_agents', 'conflict', 'Select codex, claude or both.')
    if not selection.features or selection.features - FEATURES:
        add('selection', None, 'invalid_features', 'conflict', 'Choose at least one supported feature explicitly.')
    if (selection.shortcuts - SHORTCUTS or
            (selection.shortcuts and 'shortcuts' not in selection.features) or
            ('shortcuts' in selection.features and not selection.shortcuts)):
        add('shortcuts', None, 'invalid_shortcuts', 'conflict', 'Select supported shortcuts explicitly with the shortcuts feature.')
    if not selection.parent_profile.strip():
        add('selection', None, 'invalid_parent', 'conflict', 'A parent profile name is required.')
    for feature in sorted(selection.features & FEATURES):
        for agent in sorted(selection.agents & AGENTS):
            if feature in CODEX_ONLY and agent != 'codex':
                add(feature, agent, 'codex_only', 'unavailable', 'This feature is supported only for Codex; Claude is unchanged.')
                continue
            dependencies = {'iterm2', 'zsh'}
            if feature != 'shell':
                dependencies.add(agent)
            if feature in {'status', 'notifications', 'restore', 'mcp'}:
                dependencies.add('python3')
            if feature == 'notifications':
                dependencies.add('terminal-notifier')
            missing = sorted(dependencies - context.executables.keys())
            if missing:
                add(feature, agent, 'missing_binary', 'missing_dependency', 'Required executables: ' + ', '.join(missing))
                continue
            if 'macos' not in context.capabilities:
                add(feature, agent, 'unsupported_platform', 'unavailable', 'The first release supports macOS and zsh.')
                continue
            add(feature, agent, 'preview', 'ready', DESCRIPTIONS[feature])
            if feature == 'mcp':
                add(feature, agent, 'python_api', 'pending_ui', 'Verify iTerm2 Settings > General > Magic > Enable Python API; connection and authorization are not yet verified.')
            if feature == 'restore' and agent == 'codex' and 'codex:no-daemon' not in context.capabilities:
                add(feature, agent, 'no_daemon', 'unavailable', 'Codex --no-daemon capability was not detected; hook tab identity cannot be guaranteed.')
    return findings


def plan(context: Context, selection: Selection) -> Plan:
    findings = validate(selection, context)
    from .features import restore
    findings.extend(restore.build(context,selection).findings)
    supported = selection.features - CODEX_ONLY if 'codex' not in selection.agents else selection.features
    selected = replace(selection, features=frozenset(supported))
    ui = [UiStep(f.code, f.feature, f.agent, f.message) for f in findings if f.state == 'pending_ui']
    payload = {'agents': sorted(selected.agents), 'features': sorted(selected.features),
               'shortcuts': sorted(selected.shortcuts), 'parent_profile': selected.parent_profile,
               'adopt_legacy': selected.adopt_legacy, 'versions': context.versions,
               'capabilities': sorted(context.capabilities)}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    changes = ChangeSet([], ui, findings)
    if not any(f.state in {'conflict', 'missing_dependency'} for f in findings):
        from .features.profiles import build
        from .features import shell, status, notifications, restore
        for builder in (build, shell.runtime_payload, shell.build, status.build, notifications.build):
            built = builder(context, selected)
            changes.edits.extend(built.edits)
            changes.ui.extend(built.ui)
            changes.findings.extend(built.findings)
            changes.consumers.update(built.consumers)
    return Plan(selected, changes, fingerprint)
