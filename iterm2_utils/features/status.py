"""Pure owned Codex hook settings and native Claude UI checkpoint."""
import json
import shlex
from ..models import ChangeSet, FileEdit, Finding, UiStep
from runtime.events import CODEX_EVENTS


def build(context, selection):
    changes=ChangeSet([],[],[])
    selected=selection.features_for('codex') & {'status','notifications','restore'}
    claude_notifications = 'claude' in selection.agents_for('notifications')
    if not selected and not claude_notifications and 'claude' not in selection.agents_for('status'):
        return changes
    if 'claude' in selection.agents_for('status'):
        if context.installed.get('claude-status',{}).get('enabled'):
            changes.findings.append(Finding('status','claude','native_status','ready','Native cc-status hook detected.'))
        else:
            instruction=('Open iTerm2 > Install/Reinstall Claude Code Integration. Choose only API, hooks and '
                         'Session Status; leave Workgroup and Auto-Enter unchecked. Confirm hook trust yourself.')
            changes.ui.append(UiStep('claude-native-status','status','claude',instruction))
            changes.findings.append(Finding('status','claude','native_status','pending_ui',instruction))
    runtime_consumers = frozenset('codex:'+feature for feature in selected)
    if claude_notifications:
        runtime_consumers |= {'claude:notifications'}
    existing=context.installed.get('codex-status',{}).get('enabled')
    native=context.installed.get('codex-native-status',{})
    native_reused=False
    if 'status' in selected:
        owned_status = owned_visible_status(context)
        legacy_collision = existing and owned_status and not selection.adopt_legacy
        if legacy_collision or native.get('conflict') or native.get('enabled') and (existing or owned_status):
            code = 'legacy_hook_conflict' if legacy_collision else 'native_hook_conflict'
            changes.findings.append(Finding('status','codex',code,'conflict',
                'Conflicting native/legacy status writers require explicit resolution before installing status.'))
            if owned_status:
                # Only Python runtime consumers need this shared rebuild;
                # Claude's native status UI checkpoint remains independent.
                for pair in sorted(runtime_consumers - {'codex:status'}):
                    agent, feature = pair.split(':',1)
                    changes.findings.append(Finding(feature,agent,code,'conflict',
                        'Owned visible status prevents safe shared hook/runtime recomposition while an external status writer is active.'))
            return changes
        if native.get('enabled'):
            native_reused=True
            selected=selected-{'status'}
            changes.findings.append(Finding('status','codex','native_status_reused','ready',
                'External native cc-status hooks are reused without ownership; adapter-only input/compact behavior is unavailable.'))
    if existing and 'status' in selected and not selection.adopt_legacy:
        changes.findings.append(Finding('status','codex','existing_status','ready','Existing enabled codex-iterm2-status is reused.'))
        selected=selected-{'status'}
        runtime_consumers -= {'codex:status'}
    if not selected and not claude_notifications and not native_reused:
        return changes
    if (selected or native_reused) and 'codex:no-daemon' not in context.capabilities:
        changes.findings.append(Finding('status' if 'status' in selected or native_reused else sorted(selected)[0],'codex','no_daemon','unavailable','Codex --no-daemon is required for reliable hook session identity.'))
    if ('status' in selected or native_reused) and 'iterm2:cc-status-codex' not in context.capabilities:
        changes.findings.append(Finding('status','codex','status_capability','unavailable','Codex status requires a compatible iTerm2 3.7.6+ cc-status bundle.'))
    # Shared settings must not imply a visible status selection.
    owner='shared:hooks'
    settings_path=context.paths.config/'runtime.json'
    hooks_path=context.paths.codex_home/'hooks.json'
    try:
        before=hooks_path.read_bytes() if selected and hooks_path.exists() else None
        document=json.loads(before) if before else {}
        hooks=document.setdefault('hooks',{})
        if not isinstance(hooks,dict):
            raise ValueError('hooks object')
        command=' '.join(shlex.quote(str(p)) for p in [context.executables['python3'],context.paths.data/'current/hook.py','--agent','codex','--settings',settings_path])
        for event in CODEX_EVENTS if selected else ():
            entries=hooks.setdefault(event,[])
            if not isinstance(entries,list):
                raise ValueError('hooks array')
            own={'hooks':[{'type':'command','command':command,'timeout':3}]}
            replace_owned_hook(context, hooks_path, event, entries, own)
            if own not in entries:
                entries.append(own)
        after=(json.dumps(document,sort_keys=True,indent=2)+'\n').encode()
        previous=settings_path.read_bytes() if settings_path.exists() else None
        settings=json.loads(previous) if previous else {}
        if not isinstance(settings,dict):
            raise ValueError('settings object')
        settings.update({feature:feature in selected for feature in ('status','notifications','restore')})
        settings.update(it2=str(context.executables.get('it2','')),
                        status_backend='cc-status',iterm2_app=str(context.executables.get('iterm2','')),
                        native_identity_cache=str(context.paths.cache/'native-identity'))
        if 'restore' in selected:
            settings.update(restore_codex_home=str(context.paths.codex_home),restore_cache=str(context.paths.cache/'restore'),restore_process=str(context.executables['iterm2']/'Contents/MacOS/iTerm2'))
        if 'notifications' in selected or claude_notifications:
            from .notifications import runtime_settings
            settings.update(runtime_settings(context))
        settings['notification_agents'] = sorted(selection.agents_for('notifications'))
        settings['notifications'] = bool(settings['notification_agents'])
        if selected:
            changes.edits.append(FileEdit(hooks_path,before,after,0o600,'shared:codex-hooks'))
            changes.consumers['shared:codex-hooks'] = frozenset('codex:'+feature for feature in selected)
        changes.edits.append(FileEdit(settings_path,previous,(json.dumps(settings,sort_keys=True,indent=2)+'\n').encode(),0o600,owner))
        changes.consumers[owner]=runtime_consumers
    except (ValueError,TypeError,AttributeError):
        changes.findings.append(Finding('notifications' if claude_notifications and not selected else 'status',None if claude_notifications else 'codex','hook_conflict','conflict','Selected hook/runtime configuration cannot be safely merged.'))
    return changes


def owned_visible_status(context):
    """Do not silently leave a previously owned visible writer beside an external status writer."""
    from .. import state
    receipt = state.load(context.paths.data/'receipt.json')
    if not receipt:
        return False
    target = str((context.paths.config/'runtime.json').resolve())
    return any(r['kind']=='json' and r['target']==target
               and r['locator'].get('pointer')==['status']
               and r['installed']=={'exists':True,'value':True}
               and 'shared:hooks' in r['owners'] for r in receipt.resources)


def owned_entries(context, path, event):
    from .. import state
    receipt = state.load(context.paths.data/'receipt.json')
    if not receipt:
        return []
    return [r['locator']['entry'] for r in receipt.resources
            if r['kind']=='hook' and r['target']==str(path.resolve())
            and r['locator']['pointer']==['hooks',event] and r['installed']['exists']
            and not r['before']['exists']
            and any(o in {'notifications','claude:notifications','shared:hooks','shared:codex-hooks'} for o in r['owners'])]


def replace_owned_hook(context, path, event, entries, desired):
    for old in owned_entries(context, path, event):
        if entries.count(old) != 1:
            raise ValueError('Owned hook missing or duplicated')
        if old != desired:
            entries.remove(old)
