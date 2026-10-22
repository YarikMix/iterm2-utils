"""Build inherited foreground-job profiles without changing the default profile."""
import copy
import fnmatch
import json
import uuid
from ..config import tomlfile
from ..models import ChangeSet, Context, Selection, FileEdit, PreferenceEdit, Finding

DOMAIN = 'com.googlecode.iterm2'
OWNER = 'shared:agent-profiles'
SHORTCUTS = {
    'ctrl-v-ru': ('0x43c-0x40000-0x9-0x1', 11, '0x16'),
    'alt-enter': ('0xd-0x20000-0x24-0x1', 11, '0x1b 0x0d'),
    'ctrl-q': ('0x71-0x40000-0xc-0x1', 11, '0x03 0x03'),
    'resume': ('0x52-0x120000-0xf-0x1', 12, '/resume\n'),
}


def build(context: Context, selection: Selection) -> ChangeSet:
    changes = ChangeSet([], [], [])
    clipboard = 'clipboard' in selection.features and 'codex' in selection.agents
    shortcuts = selection.shortcuts if 'shortcuts' in selection.features else frozenset()
    if not clipboard and not shortcuts:
        return changes

    def finding(code, message, agent=None, state='conflict'):
        changes.findings.append(Finding('clipboard' if clipboard else 'shortcuts', agent, code, state, message))

    parent = context.profiles.get(selection.parent_profile)
    if parent is None:
        finding('missing_parent', 'The selected parent profile must exist.')
        return changes
    if not isinstance(parent.get('Keyboard Map', {}), dict):
        finding('invalid_parent_keyboard_map', 'The parent keyboard map must be a dictionary.')
        return changes
    # iTerm2 v3.7.6 ITAddressBookMgr.h KEY_PREVENT_APS; session overrides
    # are not readable as a global defaults flag.
    if parent.get('Prevent Automatic Profile Switching'):
        finding('prevent_aps', 'The parent prevents automatic profile switching; choose how to resolve it.')
        return changes
    preferences = context.preferences.get(DOMAIN, {})
    agents = sorted(selection.agents if shortcuts else {'codex'})
    for name, existing in context.profiles.items():
        if (name in {'iterm2-utils:codex', 'iterm2-utils:claude'} and
                existing.get('Guid') == str(uuid.uuid5(uuid.NAMESPACE_URL, name))):
            continue
        if any(isinstance(rule, str) and '&' in rule and
               any(fnmatch.fnmatchcase(agent, rule.rsplit('&', 1)[1]) for agent in agents)
               for rule in existing.get('Bound Hosts', [])):
            finding('competing_aps', 'An existing automatic profile rule matches the selected agent.')
            return changes
    profiles = []
    for agent in agents:
        keys = copy.deepcopy(parent.get('Keyboard Map', {}))
        wanted = {}
        if clipboard and agent == 'codex':
            for char in ('0x63', '0x441'):
                wanted[char+'-0x40000-0x8-0x1'] = {'Action': 11, 'Text': '0x03'}
                wanted[char+'-0x100000-0x8-0x1'] = {'Action': 11, 'Text': '0x1b 0x5b 0x39 0x39 0x3b 0x39 0x75'}
        for shortcut in sorted(shortcuts):
            if shortcut == 'alt-enter' and agent+':alt-enter' not in context.capabilities:
                finding('shortcut_capability', 'Alt+Enter compatibility has not been verified for this agent version.', agent, 'unavailable')
                continue
            if shortcut == 'alt-enter' and agent == 'codex':
                finding('custom_keymap_caveat', 'Alt+Enter uses the verified default insert_newline binding; a custom Codex TUI keymap may override it.', agent, 'ready')
            key, action, text = SHORTCUTS[shortcut]
            wanted[key] = {'Action': action, 'Text': text}
        for key, value in wanted.items():
            if key in keys and keys[key] != value:
                finding('binding_conflict', 'A parent binding differs; explicit conflict resolution is required.', agent)
                return changes
        keys.update(wanted)
        profiles.append({'Name': 'iterm2-utils:'+agent,
                         'Guid': str(uuid.uuid5(uuid.NAMESPACE_URL, 'iterm2-utils:'+agent)),
                         'Dynamic Profile Parent Name': selection.parent_profile,
                         'Bound Hosts': ['&'+agent], 'Keyboard Map': keys})
    path = context.paths.profiles/'iterm2-utils.json'
    before = path.read_bytes() if path.exists() else None
    # A dedicated profile document is still CAS protected and address-owned by the engine.
    changes.edits.append(FileEdit(path, before, (json.dumps({'Profiles': profiles}, sort_keys=True, indent=2)+'\n').encode(), 0o600, OWNER))
    consumers = ({'clipboard'} if clipboard else set()) | ({'shortcuts'} if shortcuts else set())
    changes.consumers[OWNER] = frozenset(consumers)
    if clipboard:
        path = context.paths.codex_home/'config.toml'
        before = path.read_bytes() if path.exists() else None
        try:
            config = tomlfile.parse(before or b'')
            overrides = config.get('profiles', {})
            if any(isinstance(p, dict) and isinstance(p.get('tui'), dict) and 'copy_on_select' in p['tui'] for p in overrides.values()):
                finding('profile_copy_override', 'A named Codex profile overrides tui.copy_on_select; review invocations using that profile.', 'codex')
            after = tomlfile.patch(before or b'', ('tui', 'copy_on_select'), 'never')
        except (ValueError, AttributeError):
            finding('codex_config_conflict', 'Codex configuration cannot be safely edited.', 'codex')
            changes.edits.clear()
            return changes
        changes.edits.extend([FileEdit(path, before, after, 0o600, 'clipboard'),
                              PreferenceEdit(DOMAIN, 'CopySelection', preferences.get('CopySelection'), False, 'clipboard')])
    return changes
