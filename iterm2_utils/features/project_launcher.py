"""Pure project profiles and grouped native bar edits from an explicit snapshot."""
import base64
import copy
import json
import unicodedata
import uuid
from dataclasses import replace

from .. import state
from ..config import iterm
from ..models import ChangeSet, FileEdit, Finding, ProfileBarEdit, StatusBarPositionEdit

FEATURE = 'project-launcher'
OWNER = 'shared:project-launcher'
FILENAME = 'iterm2-utils-project-launcher.json'


def _text(value):
    if (type(value) is not str or not value.strip() or len(value) > 256 or
            any(unicodedata.category(c).startswith('C') for c in value)):
        raise ValueError('Invalid project text')
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate configuration field')
        result[key] = value
    return result


def _config(raw, *, historical=False):
    from pathlib import Path
    if len(raw) > 1048576:
        raise ValueError('Configuration too large')
    doc = json.loads(raw, object_pairs_hook=_unique_object)
    if type(doc) is not dict or set(doc) != {'profiles','projects'}:
        raise ValueError('Invalid configuration fields')
    for key in ('profiles','projects'):
        if type(doc[key]) is not list or not doc[key] or len(doc[key]) > 256:
            raise ValueError('Invalid configuration list')
    names = [_text(name) for name in doc['profiles']]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate profile')
    ids, names = set(), set()
    for project in doc['projects']:
        if type(project) is not dict or set(project) != {'id','name','path'}:
            raise ValueError('Invalid project fields')
        pid, name = _text(project['id']), _text(project['name'])
        path = project['path']
        if (type(path) is not str or len(path) > 4096 or
                any(unicodedata.category(c).startswith('C') for c in path) or
                not Path(path).is_absolute() or (not historical and not Path(path).is_dir())):
            raise ValueError('Project directory unavailable')
        if pid in ids or name in names:
            raise ValueError('Duplicate project')
        ids.add(pid); names.add(name)
    return doc


def guid(project_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'iterm2-utils:project-launcher:'+project_id))


def _load(context):
    receipt = state.load(context.paths.data/'receipt.json')
    config_path = context.paths.config/FILENAME
    dynamic_path = context.paths.profiles/FILENAME
    for path in (config_path, dynamic_path):
        if path.is_symlink():
            raise ValueError('Owned file must not be a symlink')
        if path.exists():
            owned = next((r for r in receipt.resources if r['kind']=='file' and
                r['target']==str(path.resolve()) and OWNER in r['owners']), None) if receipt else None
            if (owned is None or owned['installed'] != {'exists':True,
                    'value':base64.b64encode(path.read_bytes()).decode()}):
                raise ValueError('Owned configuration changed or externally owned')
    source = context.project_launcher_config
    if source is None and (receipt is None or FEATURE not in receipt.selection.features):
        raise ValueError('Explicit initial configuration required')
    config = _config((source if source is not None else config_path).read_bytes())
    return config, receipt


def prepare(context, selection, runner):
    """Only explicitly selected/recorded consumers may contact the native helper."""
    if not selection.agents_for(FEATURE):
        return context
    snapshot = None
    try:
        _load(context)
        if (context.versions.get('iterm2') == '3.7.6' and 'python:iterm2' in context.capabilities
                and {'iterm2','zsh','python3'} <= context.executables.keys()):
            snapshot = iterm.inspect(context, runner)
    except (ValueError, OSError, TypeError, KeyError):
        pass
    return replace(context, project_launcher_snapshot=snapshot)


def _component(project):
    action = dict(action=27, version=2, applyMode=0, escaping=1,
                  title=project['name'], parameter=guid(project['id']))
    return {'class':'iTermStatusBarActionComponent', 'configuration':{
        'knobs':{'base: compression resistance':1, 'maxwidth':1.7976931348623157e+308,
                 'base: priority':5, 'minwidth':'0', 'shared font':'', 'action':action},
        'layout advanced configuration dictionary value':{
            'remove empty components':False, 'auto-rainbow style':0,
            'draw separator between status bar and terminal':False, 'algorithm':0}}}


def _panel(bar, projects, previous, baseline):
    result = copy.deepcopy(bar)
    layout = result['Status Bar Layout']
    components = layout.get('components')
    if type(components) is not list:
        raise ValueError('Native component list unavailable')
    baseline_components = baseline['Status Bar Layout']['components']
    previous_components = [_component(p) for p in previous if _component(p) not in baseline_components]
    layout['components'] = [c for c in components if c not in previous_components]
    for project in projects:
        component = _component(project)
        if component not in layout['components']:
            layout['components'].append(component)
    result['Show Status Bar'] = True
    return result


def build(context, selection):
    changes = ChangeSet([], [], [])
    agents = selection.agents_for(FEATURE)
    if not agents:
        return changes
    def fail(code, message, status='conflict'):
        changes.edits.clear()
        changes.findings.append(Finding(FEATURE,None,code,status,message))
        return changes
    try:
        config, receipt = _load(context)
    except (ValueError, OSError, TypeError, KeyError):
        return fail('project_launcher_config','Use a valid explicit project configuration; resolve changed or externally owned launcher files first.')
    if context.versions.get('iterm2') != '3.7.6':
        return fail('project_launcher_version','The native project launcher format is verified only for iTerm2 3.7.6.','unavailable')
    if 'python:iterm2' not in context.capabilities:
        return fail('project_launcher_sdk','Select an existing Python 3.11+ with iterm2 using ITERM2_UTILS_PYTHON; enable and authorize the iTerm2 Python API.','missing_dependency')
    try:
        snapshot = iterm.validate_inventory(context.project_launcher_snapshot)
        profiles = {p['name']:p for p in snapshot['profiles']}
        parent = profiles[selection.parent_profile]
        targets = [profiles[name] for name in config['profiles']]
        old_path = context.paths.config/FILENAME
        previous = _config(old_path.read_bytes(),historical=True)['projects'] if old_path.exists() else []
        dynamic_path = context.paths.profiles/FILENAME
        before = dynamic_path.read_bytes() if dynamic_path.exists() else None
        owned_guids = {p['Guid'] for p in json.loads(before)['Profiles']} if before else set()
        existing_guids = {p['guid'] for p in snapshot['profiles']}
        baseline_bars = {r['target']:r['before']['value'] for r in receipt.resources
            if r['kind']=='profile_bar' and OWNER in r['owners']} if receipt else {}
        for project in config['projects']:
            if guid(project['id']) in existing_guids - owned_guids:
                raise ValueError('Generated project GUID is externally owned')
            existing = profiles.get(project['name'])
            if existing and existing['guid'] != guid(project['id']):
                raise ValueError('Project name collision')
        bars = []
        for target in targets:
            for session in snapshot['sessions']:
                if not session['provenance'] or (session['profile_guid']==target['guid'] and not iterm.same(session['bar'],target['bar'])):
                    raise ValueError('Session propagation conflict')
            # Owned project bars change atomically with their dedicated file.
            if target['guid'] not in owned_guids:
                bars.append(ProfileBarEdit(target['guid'],target['bar'],_panel(target['bar'],config['projects'],previous,baseline_bars.get(target['guid'],target['bar'])),OWNER))
        target_guids = {p['guid'] for p in targets}
        for resource in receipt.resources if receipt else ():
            if resource['kind']=='profile_bar' and OWNER in resource['owners'] and resource['target'] not in target_guids:
                current = next(p for p in snapshot['profiles'] if p['guid']==resource['target'])
                if not iterm.same(current['bar'],resource['installed']['value']):
                    raise ValueError('Removed target bar changed')
                bars.append(ProfileBarEdit(resource['target'],current['bar'],resource['before']['value'],OWNER))
        panel = _panel(parent['bar'],config['projects'],previous,baseline_bars.get(parent['guid'],parent['bar']))
        rows = [dict(Name=p['name'], Guid=guid(p['id']), **{
            'Dynamic Profile Parent GUID':parent['guid'], 'Custom Command':'No', 'Command':'',
            'Custom Directory':'Yes', 'Working Directory':p['path'], **panel}) for p in config['projects']]
        after = (json.dumps({'Profiles':rows},sort_keys=True,indent=2)+'\n').encode()
        dynamic = FileEdit(dynamic_path,before,after,0o600,OWNER)
        # Remove confirmed owned buttons before deleting their profile targets.
        removing = owned_guids - {p['Guid'] for p in rows}
        changes.edits = bars+[dynamic] if removing else [dynamic]+bars
        changes.edits.append(StatusBarPositionEdit(snapshot['position'],iterm.POSITION_BOTTOM,OWNER))
        normalized = (json.dumps(config,sort_keys=True,indent=2)+'\n').encode()
        changes.edits.append(FileEdit(old_path,old_path.read_bytes() if old_path.exists() else None,normalized,0o600,OWNER))
        changes.consumers[OWNER] = frozenset(a+':'+FEATURE for a in agents)
        changes.findings.append(Finding(FEATURE,None,'project_launcher_native','ready',
            'Native inventory and typed panel edits prepared; visual CLI acceptance remains unverified.'))
    except (ValueError, OSError, KeyError, TypeError, StopIteration):
        return fail('project_launcher_native','Native inventory, selected profiles or session propagation could not be verified; resolve conflicts before retrying.')
    return changes
