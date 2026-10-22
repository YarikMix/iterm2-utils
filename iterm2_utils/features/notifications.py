"""Pure notification configuration; no permission decisions or live delivery."""
import json
import shlex
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
    if 'codex' in selection.agents:
        if 'codex:approval-notifications' not in context.capabilities:
            changes.findings.append(Finding('notifications','codex','native_policy_version','unavailable','Native approval policy is verified only for Codex 0.163.0; this version is unverified.'))
        else:
            path=context.paths.codex_home/'config.toml';before=path.read_bytes() if path.exists() else None
            try:
                after=tomlfile.set_tui_key(before or b'','notifications',['approval-requested'])
                changes.edits.append(FileEdit(path,before,after,0o600,'notifications'))
            except ValueError:
                changes.findings.append(Finding('notifications','codex','native_policy_conflict','conflict','Codex native notification policy cannot be safely edited.'))
    if 'claude' in selection.agents:
        settings_path=context.paths.config/'runtime.json'
        path=context.paths.claude_settings;before=path.read_bytes() if path.exists() else None
        try:
            document=json.loads(before or b'{}');hooks=document.setdefault('hooks',{})
            command=shlex.join([str(context.executables['python3']),str(context.paths.data/'current/hook.py'),'--agent','claude','--settings',str(settings_path)])
            for name in CLAUDE_EVENTS:
                entry={'hooks':[{'type':'command','command':command,'timeout':3}]}
                if name=='Notification':entry['matcher']=MATCHER
                entries=hooks.setdefault(name,[])
                if entry not in entries:entries.append(entry)
            changes.edits.append(FileEdit(path,before,(json.dumps(document,sort_keys=True,indent=2)+'\n').encode(),0o600,'notifications'))
            if 'codex' not in selection.agents:
                previous=settings_path.read_bytes() if settings_path.exists() else None
                settings=json.loads(previous or b'{}')
                settings.update(runtime_settings(context),notifications=True,status=False,restore=False,it2=str(context.executables.get('it2','')))
                changes.edits.append(FileEdit(settings_path,previous,(json.dumps(settings,sort_keys=True,indent=2)+'\n').encode(),0o600,'shared:hooks'))
                changes.consumers['shared:hooks']=frozenset({'notifications'})
        except (ValueError,TypeError,AttributeError,KeyError):
            changes.edits.clear()
            changes.findings.append(Finding('notifications','claude','hook_conflict','conflict','Claude notification hooks cannot be safely merged.'))
    return changes
