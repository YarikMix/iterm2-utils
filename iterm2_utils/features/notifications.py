"""Pure notification configuration; no permission decisions or live delivery."""
import json
import shlex
from pathlib import Path
from ..models import ChangeSet,FileEdit,Finding
from ..config import tomlfile

CLAUDE_EVENTS=('SessionStart','UserPromptSubmit','Notification','Stop','StopFailure','SubagentStop','SessionEnd','PostToolUse','PostToolUseFailure')
MATCHER='permission_prompt|idle_prompt|elicitation_dialog|elicitation_url_dialog'

def runtime_settings(context):
    return dict(terminal_notifier=str(context.executables.get('terminal-notifier','')),osascript=str(context.executables.get('osascript','')),notification_cache=str(context.paths.cache/'notifications'))

def build(context,selection):
    changes=ChangeSet([],[],[])
    if 'notifications' not in selection.features:
        return changes
    conflicts = [a for a in foreign_handlers(context, selection) if not selection.coexist_for(a)]
    if conflicts:
        changes.findings.extend(Finding('notifications', agent, 'foreign_notifications', 'conflict',
            'Existing notification handler detected. Keep it by leaving notifications unselected, or explicitly choose --coexist-notifications (duplicate banners may occur); foreign handlers will be preserved.') for agent in conflicts)
    if 'codex' in selection.agents_for('notifications') and 'codex' not in conflicts:
        if 'codex:approval-notifications' not in context.capabilities:
            changes.findings.append(Finding('notifications','codex','native_policy_version','unavailable','Native approval policy is verified only for Codex 0.163.0; this version is unverified.'))
        else:
            path=context.paths.codex_home/'config.toml';before=path.read_bytes() if path.exists() else None
            try:
                after=tomlfile.set_tui_key(before or b'','notifications',['approval-requested'])
                changes.edits.append(FileEdit(path,before,after,0o600,'notifications'))
            except ValueError:
                changes.findings.append(Finding('notifications','codex','native_policy_conflict','conflict','Codex native notification policy cannot be safely edited.'))
    if 'claude' in selection.agents_for('notifications') and 'claude' not in conflicts:
        settings_path=context.paths.config/'runtime.json'
        path=context.paths.claude_settings;before=path.read_bytes() if path.exists() else None
        try:
            document=json.loads(before or b'{}');hooks=document.setdefault('hooks',{})
            command=shlex.join([str(context.executables['python3']),str(context.paths.data/'current/hook.py'),'--agent','claude','--settings',str(settings_path)])
            for name in CLAUDE_EVENTS:
                entry={'hooks':[{'type':'command','command':command,'timeout':3}]}
                if name=='Notification':entry['matcher']=MATCHER
                entries=hooks.setdefault(name,[])
                from .status import replace_owned_hook
                replace_owned_hook(context, path, name, entries, entry)
                if entry not in entries:entries.append(entry)
            changes.edits.append(FileEdit(path,before,(json.dumps(document,sort_keys=True,indent=2)+'\n').encode(),0o600,'notifications'))
        except (ValueError,TypeError,AttributeError,KeyError):
            changes.edits.clear()
            changes.findings.append(Finding('notifications','claude','hook_conflict','conflict','Claude notification hooks cannot be safely merged.'))
    return changes


def foreign_handlers(context, selection):
    """Recognize exact notifier executables, without storing command bodies."""
    from .status import owned_entries
    found = set()
    for agent in selection.agents_for('notifications'):
        if agent == 'codex' and context.installed.get('codex-status', {}).get('enabled'):
            found.add(agent)
        path = context.paths.claude_settings if agent == 'claude' else context.paths.codex_home/'hooks.json'
        document = json.loads(path.read_bytes()) if path.exists() else {}
        for event, entries in document.get('hooks', {}).items():
            owned = owned_entries(context, path, event)
            for entry in entries:
                if entry in owned:
                    continue
                for hook in entry.get('hooks', []):
                    if hook.get('type') != 'command':
                        continue
                    words = shlex.split(hook.get('command', ''))
                    if words and words[0] in {'exec','command'}:
                        words = words[1:]
                    if words and Path(words[0]).name == 'terminal-notifier':
                        found.add(agent)
    return sorted(found)
