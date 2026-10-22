"""Private, versioned receipts. Invalid state never grants ownership."""
import base64
import binascii
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from .models import Receipt, Selection, UiStep

VERSION = '1'
FIELDS = {'kind','target','locator','before','installed','owners','version'}
KINDS = {'file','json','toml','zsh','preference','registration','symlink'}


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
    if receipt.version != VERSION or not isinstance(receipt.resources,list):
        raise ValueError('Unsupported receipt')
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
        if r['kind'] in {'file','json','toml','zsh'}:
            mode = r['locator'].get('mode')
            if type(mode) is not int or not 0 <= mode <= 0o7777:
                raise ValueError('Invalid receipt mode')
        if r['kind'] in {'zsh','registration','preference'}:
            key = 'key' if r['kind']=='preference' else 'name'
            if not isinstance(r['locator'].get(key),str) or not r['locator'][key]:
                raise ValueError('Invalid receipt address')
        if r['kind'] in {'file','json','toml','zsh','symlink'} and not Path(r['target']).is_absolute():
            raise ValueError('Invalid receipt target')
        if r['kind'] in {'json','toml'} and (not isinstance(r['locator'].get('pointer'),list) or
                any(type(p) not in (str,int) for p in r['locator']['pointer'])):
            raise ValueError('Invalid receipt address')
    return receipt


def load(path: Path) -> Receipt | None:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    try:
        data = json.loads(raw)
        if set(data) != {'version','selection','resources','pending_ui'}:
            raise ValueError()
        selection = dict(data['selection'])
        for key in ('agents','features','shortcuts'):
            if not isinstance(selection[key],list) or any(not isinstance(v,str) for v in selection[key]):
                raise ValueError('Invalid selection')
            selection[key] = frozenset(selection[key])
        return validate(Receipt(data['version'],Selection(**selection),data['resources'],[UiStep(**s) for s in data['pending_ui']]))
    except (ValueError,TypeError,KeyError,UnicodeError):
        raise ValueError('Invalid or unsupported receipt; ownership unavailable') from None


def save(path: Path, receipt: Receipt) -> None:
    validate(receipt)
    data = asdict(receipt)
    for key in ('agents','features','shortcuts'):
        data['selection'][key] = sorted(data['selection'][key])
    private_dir(path.parent)
    durable_write(path,(json.dumps(data,sort_keys=True,ensure_ascii=False)+'\n').encode())
