"""Self-contained skill copies, owned separately from feature installation.

A bootstrap never probes or installs an agent and never selects terminal features.
The regular CAS transaction engine maintains its own bootstrap receipt.
"""
import base64
from dataclasses import replace
from . import engine, state
from .models import ChangeSet, Context, FileEdit, Finding, Plan, Selection

AGENTS = frozenset({'codex', 'claude'})
OWNER = 'bootstrap-skill'
FILES = ('SKILL.md', 'references/features.md', 'references/ui.md', 'references/troubleshooting.md')
BUNDLES = {'iterm2-setup': FILES, 'iterm2-launch': ('SKILL.md', 'references/handoff.md')}


def _context(context, skill):
    receipt = OWNER if skill == 'iterm2-setup' else OWNER+'-'+skill
    return replace(context, paths=replace(context.paths, data=context.paths.data/receipt))


def _destination(context, agent, skill):
    root = context.paths.codex_home if agent == 'codex' else context.paths.home/'.claude'
    return root/'skills'/skill


def _conflict(agent, code, message):
    return Finding('skill', agent, code, 'conflict', message)


def build(context: Context, agents: frozenset[str], *, skill='iterm2-setup') -> ChangeSet:
    """Prepare selected destinations only; existing foreign directories are refused."""
    changes = ChangeSet([], [], [])
    if skill not in BUNDLES:
        changes.findings.append(_conflict(None, 'invalid_skill', 'Select iterm2-setup or iterm2-launch.'))
        return changes
    if not agents or agents - AGENTS:
        changes.findings.append(_conflict(None, 'invalid_agents', 'Select codex, claude or both.'))
        return changes
    if skill == 'iterm2-launch' and agents != frozenset({'codex'}):
        changes.findings.append(_conflict(None, 'invalid_agents', 'Select only codex for iterm2-launch.'))
        return changes
    try:
        receipt = state.load(_context(context, skill).paths.data/'receipt.json')
        owned = {r['target']: r['installed'] for r in receipt.resources
                 if r['kind'] == 'file' and r['owners'] == [OWNER]} if receipt else {}
        source = context.paths.repo/'skills'/skill
        payload = {}
        for name in BUNDLES[skill]:
            path = source/name
            if path.is_symlink() or not path.is_file():
                raise ValueError('Invalid public skill bundle')
            payload[name] = path.read_bytes()
        for agent in sorted(agents):
            destination = _destination(context, agent, skill)
            if destination.is_symlink() or (destination.exists() and
                    (not destination.is_dir() or str((destination/'SKILL.md').resolve()) not in owned)):
                changes.findings.append(_conflict(agent, 'foreign_skill', f'Existing {skill} path is not owned by this bootstrap; preserve it and choose a resolution.'))
                continue
            edits = []
            for name, content in payload.items():
                path = destination/name
                # Do not follow an injected references directory or file symlink.
                if path.is_symlink() or (path.parent != destination and path.parent.is_symlink()):
                    raise ValueError('Invalid skill symlink')
                before = path.read_bytes() if path.exists() else None
                installed = owned.get(str(path.resolve()))
                if installed is not None:
                    expected = base64.b64decode(installed['value']) if installed['exists'] else None
                    if before != expected:
                        raise ValueError('User-changed skill file')
                elif before is not None:
                    raise ValueError('Foreign skill file')
                edits.append(FileEdit(path, before, content, 0o644, OWNER))
            changes.edits.extend(edits)
            changes.findings.append(Finding('skill', agent, 'skill_prepared', 'ready',
                'Self-contained skill prepared; terminal features and agent binaries are unchanged.'))
    except (ValueError, OSError, TypeError, KeyError):
        changes.edits.clear()
        changes.findings.append(_conflict(None, 'skill_ownership_unavailable', 'Skill bundle or bootstrap ownership could not be verified; no copy was prepared.'))
    return changes


def install(context, agents, runner, *, dry_run=False, skill='iterm2-setup') -> list[Finding]:
    """Apply a skill-only transaction without touching the feature receipt."""
    changes = build(context, agents, skill=skill)
    if dry_run or any(f.state == 'conflict' for f in changes.findings):
        return changes.findings
    isolated = _context(context, skill)
    try:
        receipt = state.load(isolated.paths.data/'receipt.json')
        selected = agents | (receipt.selection.agents if receipt else frozenset())
    except (ValueError, OSError):
        return [_conflict(None, 'skill_ownership_unavailable', 'Bootstrap ownership is unavailable.')]
    selection = Selection(selected, frozenset({OWNER}), frozenset(), 'Default')
    result = engine.apply(Plan(selection, changes, 'skill-bootstrap'), isolated, runner, expected_receipt=receipt)
    return result.findings
