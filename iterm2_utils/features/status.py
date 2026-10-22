"""Pure owned Codex hook settings and native Claude UI checkpoint."""
import json
import shlex
from ..models import ChangeSet, FileEdit, Finding, UiStep
from runtime.events import EVENTS


def build(context, selection):
    changes=ChangeSet([],[],[])
    selected=selection.features & {'status','notifications','restore'}
    if not selected:
        return changes
    if 'status' in selected and 'claude' in selection.agents:
        if context.installed.get('claude-status',{}).get('enabled'):
            changes.findings.append(Finding('status','claude','native_status','ready','Native cc-status hook detected.'))
        else:
            instruction=('Open iTerm2 > Install/Reinstall Claude Code Integration. Choose only API, hooks and '
                         'Session Status; leave Workgroup and Auto-Enter unchecked. Confirm hook trust yourself.')
            changes.ui.append(UiStep('claude-native-status','status','claude',instruction))
            changes.findings.append(Finding('status','claude','native_status','pending_ui',instruction))
    if 'codex' not in selection.agents:
        return changes
    existing=context.installed.get('codex-status',{}).get('enabled')
    if existing and 'status' in selected:
        changes.findings.append(Finding('status','codex','existing_status','ready','Existing enabled codex-iterm2-status is reused.'))
        selected=selected-{'status'}
    if not selected:
        return changes
    if 'codex:no-daemon' not in context.capabilities:
        changes.findings.append(Finding('status','codex','no_daemon','unavailable','Codex --no-daemon is required for reliable hook session identity.'))
        return changes
    if 'status' in selected and 'iterm2:session-status' not in context.capabilities:
        changes.findings.append(Finding('status','codex','status_capability','unavailable','iTerm2 session-status capability is unavailable.'))
        selected=selected-{'status'}
        if not selected:
            return changes
    # Feature flags are independently selected. Task6/7 extend runtime modules;
    # this shared settings address must not imply a visible status selection.
    owner='shared:hooks'
    settings_path=context.paths.config/'runtime.json'
    hooks_path=context.paths.codex_home/'hooks.json'
    try:
        before=hooks_path.read_bytes() if hooks_path.exists() else None
        document=json.loads(before) if before else {}
        hooks=document.setdefault('hooks',{})
        if not isinstance(hooks,dict):
            raise ValueError('hooks object')
        command=' '.join(shlex.quote(str(p)) for p in [context.executables['python3'],context.paths.data/'current/hook.py','--agent','codex','--settings',settings_path])
        for event in EVENTS:
            entries=hooks.setdefault(event,[])
            if not isinstance(entries,list):
                raise ValueError('hooks array')
            own={'hooks':[{'type':'command','command':command,'timeout':3}]}
            if own not in entries:
                entries.append(own)
        after=(json.dumps(document,sort_keys=True,indent=2)+'\n').encode()
        previous=settings_path.read_bytes() if settings_path.exists() else None
        settings=json.loads(previous) if previous else {}
        if not isinstance(settings,dict):
            raise ValueError('settings object')
        settings.update({feature:feature in selected for feature in ('status','notifications','restore')})
        settings.update(it2=str(context.executables.get('it2','')),cache=str(context.paths.cache/'status'))
        if 'notifications' in selected:
            from .notifications import runtime_settings
            settings.update(runtime_settings(context))
        changes.edits.extend([FileEdit(hooks_path,before,after,0o600,owner),FileEdit(settings_path,previous,(json.dumps(settings,sort_keys=True,indent=2)+'\n').encode(),0o600,owner)])
        changes.consumers[owner]=frozenset(selected)
    except (ValueError,TypeError,AttributeError):
        changes.findings.append(Finding('status','codex','hook_conflict','conflict','Codex hook configuration cannot be safely merged.'))
    return changes
