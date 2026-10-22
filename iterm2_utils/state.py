"""Private, versioned receipts. Invalid state never grants ownership."""
import base64
import binascii
import json
import os
import shlex
import re
import tempfile
from dataclasses import asdict
from pathlib import Path
from .models import Receipt, Selection, UiStep

VERSION = '1'
FIELDS = {'kind','target','locator','before','installed','owners','version'}
KINDS = {'file','json','toml','zsh','preference','registration','symlink','hook'}


def private_dir(path):
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    path.chmod(0o700)


def durable_write(path, content, mode=0o600, *, before_replace=None):
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            os.fchmod(stream.fileno(),mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if before_replace is not None:
            before_replace()
        os.replace(temporary,path)
        directory = os.open(path.parent,os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate(receipt):
    choice = receipt.selection
    if not isinstance(choice.parent_profile, str) or type(choice.adopt_legacy) is not bool or type(choice.coexist_notifications) is not bool:
        raise ValueError('Invalid selection')
    if choice.notification_coexist_agents is not None and (not isinstance(choice.notification_coexist_agents, list) or
            any(not isinstance(a,str) or a not in choice.agents for a in choice.notification_coexist_agents)):
        raise ValueError('Invalid coexistence choice')
    if (choice.agent_features is None) != (choice.agent_shortcuts is None):
        raise ValueError('Incomplete pairwise selection')
    if choice.agent_features is not None:
        for mapping, allowed in ((choice.agent_features, choice.features), (choice.agent_shortcuts, choice.shortcuts)):
            if not isinstance(mapping, dict) or set(mapping) != set(choice.agents):
                raise ValueError('Invalid pairwise agents')
            for agent, values in mapping.items():
                if not isinstance(values, list) or any(not isinstance(v,str) for v in values) or len(set(values)) != len(values) or not set(values) <= allowed:
                    raise ValueError('Invalid pairwise choices')
            if set().union(*(set(values) for values in mapping.values())) != set(allowed):
                raise ValueError('Pairwise choices disagree with aggregate')
        if any(choice.agent_shortcuts[a] and 'shortcuts' not in choice.agent_features[a] for a in choice.agents):
            raise ValueError('Shortcut choices require their feature')
    if receipt.version != VERSION or not isinstance(receipt.resources,list):
        raise ValueError('Unsupported receipt')
    if not isinstance(receipt.ui_snapshots, dict) or set(receipt.ui_snapshots) - {'claude-native-status'}:
        raise ValueError('Invalid UI snapshot')
    for entries in receipt.ui_snapshots.values():
        if not isinstance(entries, list):
            raise ValueError('Invalid UI snapshot')
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {'event', 'entry'} or not isinstance(entry['event'], str):
                raise ValueError('Invalid UI snapshot entry')
            validate_native_entry(entry)
    for r in receipt.resources:
        if (not isinstance(r,dict) or set(r) != FIELDS or r['version'] != VERSION or
            r['kind'] not in KINDS or not isinstance(r['target'],str) or
            not isinstance(r['locator'],dict) or not isinstance(r['owners'],list) or
            not r['owners'] or any(not isinstance(o,str) or not o for o in r['owners'])):
            raise ValueError('Invalid receipt resource')
        for field in ('before','installed'):
            if (not isinstance(r[field],dict) or set(r[field]) != {'exists','value'} or
                type(r[field]['exists']) is not bool):
                raise ValueError('Invalid receipt value')
        for field in ('before','installed'):
            value = r[field]
            if not value['exists'] and value['value'] is not None:
                raise ValueError('Invalid absent receipt value')
            if value['exists'] and r['kind'] in {'file','zsh','symlink'}:
                if not isinstance(value['value'],str):
                    raise ValueError('Invalid receipt payload')
                if r['kind'] == 'file':
                    try:
                        base64.b64decode(value['value'],validate=True)
                    except (ValueError,binascii.Error):
                        raise ValueError('Invalid receipt payload') from None
        if r['kind'] in {'file','json','toml','zsh','hook'}:
            mode = r['locator'].get('mode')
            if type(mode) is not int or not 0 <= mode <= 0o7777:
                raise ValueError('Invalid receipt mode')
        if r['kind'] in {'zsh','registration','preference'}:
            key = 'key' if r['kind']=='preference' else 'name'
            if not isinstance(r['locator'].get(key),str) or not r['locator'][key]:
                raise ValueError('Invalid receipt address')
        if r['kind'] in {'file','json','toml','zsh','symlink','hook'} and not Path(r['target']).is_absolute():
            raise ValueError('Invalid receipt target')
        if r['kind'] in {'json','toml'} and (not isinstance(r['locator'].get('pointer'),list) or
                any(type(p) not in (str,int) for p in r['locator']['pointer'])):
            raise ValueError('Invalid receipt address')
        if r['kind'] == 'zsh' and 'placement' in r['locator']:
            loc = r['locator']
            value = loc['placement']
            if (set(loc) != {'name','mode','placement'} or loc['name'] not in {'legacy-status','legacy-restore'} or
                    not isinstance(value,dict) or set(value) != {'before','after','order'} or
                    any(value[key] is not None and (not isinstance(value[key],str) or not re.fullmatch('[0-9a-f]{64}',value[key])) for key in ('before','after')) or
                    not isinstance(value['order'],list) or any(name not in {'legacy-status','legacy-restore'} for name in value['order']) or
                    len(set(value['order'])) != len(value['order']) or loc['name'] not in value['order']):
                raise ValueError('Invalid legacy placement')
        if r['kind'] == 'hook':
            loc = r['locator']
            if set(loc) != {'pointer','entry','mode'} or not isinstance(loc['pointer'],list) or len(loc['pointer']) != 2 or loc['pointer'][0] != 'hooks' or not isinstance(loc['pointer'][1],str):
                raise ValueError('Invalid hook address')
            validate_hook(loc['entry'])
            for key in ('before','installed'):
                if r[key]['exists'] and r[key]['value'] != loc['entry']:
                    raise ValueError('Invalid hook value')
    return receipt


def load(path: Path) -> Receipt | None:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    try:
        data = json.loads(raw)
        if set(data) not in ({'version','selection','resources','pending_ui'}, {'version','selection','resources','pending_ui','ui_snapshots'}):
            raise ValueError()
        selection = dict(data['selection'])
        for key in ('agents','features','shortcuts'):
            if not isinstance(selection[key],list) or any(not isinstance(v,str) for v in selection[key]):
                raise ValueError('Invalid selection')
            selection[key] = frozenset(selection[key])
        return validate(Receipt(data['version'],Selection(**selection),data['resources'],[UiStep(**s) for s in data['pending_ui']],data.get('ui_snapshots',{})))
    except (ValueError,TypeError,KeyError,UnicodeError):
        raise ValueError('Invalid or unsupported receipt; ownership unavailable') from None


def save(path: Path, receipt: Receipt) -> None:
    validate(receipt)
    data = asdict(receipt)
    for key in ('agents','features','shortcuts'):
        data['selection'][key] = sorted(data['selection'][key])
    private_dir(path.parent)
    durable_write(path,(json.dumps(data,sort_keys=True,ensure_ascii=False)+'\n').encode())


def validate_hook(entry):
    if not isinstance(entry,dict) or set(entry) - {'hooks','matcher'} or 'hooks' not in entry:
        raise ValueError('Invalid hook entry')
    if 'matcher' in entry and (not isinstance(entry['matcher'],str) or len(entry['matcher']) > 512):
        raise ValueError('Invalid hook matcher')
    if not isinstance(entry['hooks'],list) or len(entry['hooks']) != 1:
        raise ValueError('Invalid hook commands')
    hook = entry['hooks'][0]
    if (not isinstance(hook,dict) or set(hook) - {'type','command','timeout','async'} or
            hook.get('type') != 'command' or not isinstance(hook.get('command'),str) or
            len(hook['command']) > 8192 or ('timeout' in hook and type(hook['timeout']) not in (int,float)) or
            ('async' in hook and type(hook['async']) is not bool)):
        raise ValueError('Invalid hook command')


NATIVE_EVENTS = frozenset({'SessionStart','SessionEnd','UserPromptSubmit','PreToolUse','PostToolUse',
    'PostToolUseFailure','PermissionRequest','Notification','Stop','StopFailure','SubagentStart',
    'SubagentStop','PreCompact','PostCompact'})
NATIVE_ARGUMENTS = frozenset({'start','stop','working','waiting','idle','session-start','session-end',
    'user-prompt-submit','pre-tool-use','post-tool-use','notification','permission-request'})


def validate_native_entry(item):
    if item['event'] not in NATIVE_EVENTS:
        raise ValueError('Unknown native hook event')
    entry = item['entry']
    validate_hook(entry)
    if entry.get('matcher','') not in {'','*'}:
        raise ValueError('Unknown native matcher')
    words = shlex.split(entry['hooks'][0]['command'])
    if (not words or not Path(words[0]).is_absolute() or
            not (words[0].endswith('/.config/iterm2/cc-status') or
                 words[0].endswith('/Contents/Resources/utilities/cc-status')) or
            len(words) > 2 or (len(words)==2 and words[1] not in NATIVE_ARGUMENTS)):
        raise ValueError('Unknown native command')
