"""CAS mutations, address-level ownership, and durable interrupted-step recovery.

Journal intent is persisted before each write. Recovery compares the current
address with before/installed and never restores a complete shared config backup.
"""
import base64
import copy
import fcntl
import json
import os
import shutil
import stat
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from . import state
from .config import jsonfile, tomlfile, zshrc, preferences, mcp
from .models import SymlinkEdit, FileEdit, PreferenceEdit, RegistrationEdit, Receipt, Outcome, Finding, Plan, Context
from .commands import Runner

# Registration backend uses the transaction Context for every inspection and write.
registration_adapter = mcp


def _finding(code, message, owner='transaction', status='conflict'):
    return Finding(owner,None,code,status,message)


def _same(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left,dict):
        return left.keys() == right.keys() and all(_same(left[k],right[k]) for k in left)
    if isinstance(left,(list,tuple)):
        return len(left) == len(right) and all(_same(a,b) for a,b in zip(left,right))
    return left == right


def _value(value=None, exists=True):
    return {'exists':exists,'value':value if exists else None}


def _empty(selection):
    return Receipt(state.VERSION,selection,[],[])


def _resource(kind,target,locator,before,installed,owner):
    return dict(kind=kind,target=str(target),locator=locator,before=before,
                installed=installed,owners=[owner],version=state.VERSION)


def _identity(r):
    address = {k:v for k,v in r['locator'].items() if k not in {'mode','placement'}}
    return r['kind'],r['target'],json.dumps(address,sort_keys=True)


def _bytes(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _encode(value):
    return _value(base64.b64encode(value).decode()) if value is not None else _value(exists=False)


def _resolve(path):
    # Preserve symlink itself; the receipt pins the resolved destination.
    return path.resolve(strict=False)


def _write_file(path, content, mode, *, expected):
    def check():
        if _bytes(path) != expected:
            raise ValueError('Concurrent file edit during staging')
    if content is None:
        check()
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    state.durable_write(path,content,mode,before_replace=check)


def _lookup(root,pointer):
    node = root
    try:
        for key in pointer:
            node = node[key]
        return _value(node)
    except (KeyError,IndexError):
        return _value(exists=False)


def _diff(before, after, prefix=()):
    if isinstance(before,dict) and isinstance(after,dict):
        for key in sorted(before.keys() | after.keys()):
            if key not in before:
                # New objects are decomposed so later additions survive removal.
                if isinstance(after[key],dict) and after[key]:
                    yield from _diff({},after[key],prefix+(key,))
                else:
                    yield prefix+(key,),_value(exists=False),_value(after[key])
            elif key not in after:
                yield prefix+(key,),_value(before[key]),_value(exists=False)
            else:
                yield from _diff(before[key],after[key],prefix+(key,))
    elif not _same(before,after):
        yield prefix,_value(before),_value(after)


def _compile(edit):
    if isinstance(edit,SymlinkEdit):
        if not edit.path.is_absolute():
            raise ValueError('Invalid symlink address')
        # Resolve parents only. The pointer itself is the owned resource.
        path = edit.path.parent.resolve() / edit.path.name
        return [_resource('symlink',path,{},_value(edit.before,edit.before is not None),_value(edit.after,edit.after is not None),edit.owner)]
    if isinstance(edit,RegistrationEdit):
        if registration_adapter is None:
            raise ValueError('Registration backend unavailable')
        return [_resource('registration',edit.agent,{'name':edit.name},_value(edit.before,edit.before is not None),_value(edit.after,edit.after is not None),edit.owner)]
    if isinstance(edit,PreferenceEdit):
        return [_resource('preference',edit.domain,{'key':edit.key},_value(edit.before,edit.before is not None),_value(edit.after,edit.after is not None),edit.owner)]
    if not isinstance(edit,FileEdit) or not edit.path.is_absolute():
        raise ValueError('Invalid file edit')
    path = _resolve(edit.path)
    old, new = edit.before, edit.after
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else edit.mode
    locator = {'mode':mode}
    if edit.path.name == 'iterm2-utils.json':
        return [_resource('file',path,locator,_encode(old),_encode(new),edit.owner)]
    if edit.path.suffix in {'.json','.toml'} and new is not None:
        kind = edit.path.suffix[1:]
        parser = jsonfile.parse if kind=='json' else tomlfile.parse
        before = parser(old) if old is not None else {}
        after = parser(new)
        if not isinstance(before,dict) or not isinstance(after,dict):
            raise ValueError('Configuration root must be a table')
        result = []
        for pointer,a,b in _diff(before,after):
            if kind == 'json' and len(pointer) == 2 and pointer[0] == 'hooks':
                old_entries = a['value'] if a['exists'] else []
                new_entries = b['value'] if b['exists'] else []
                if not isinstance(old_entries,list) or not isinstance(new_entries,list):
                    raise ValueError('Invalid hook array')
                for entry in old_entries + new_entries:
                    if old_entries.count(entry) > 1 or new_entries.count(entry) > 1:
                        raise ValueError('Ambiguous duplicate hooks')
                    was, now = entry in old_entries, entry in new_entries
                    if was == now:
                        continue
                    state.validate_hook(entry)
                    resource = _resource('hook',path,{'pointer':list(pointer),'entry':entry,'mode':mode},_value(entry,was),_value(entry,now),edit.owner)
                    if resource not in result:
                        result.append(resource)
                continue
            # Validate supported syntax against the original file before writes.
            patcher = jsonfile.patch if kind=='json' else tomlfile.patch
            patcher(old or (b'{}' if kind=='json' else b''),pointer,b['value'],remove=not b['exists'])
            result.append(_resource(kind,path,{'pointer':list(pointer),'mode':mode},a,b,edit.owner))
        return result
    if edit.path.name in {'.zshrc','zshrc'} and new is not None:
        before,after = zshrc.blocks(old or b''), zshrc.blocks(new)
        # Only managed blocks may differ in a shell configuration.
        a,b = old or b'',new
        for name in before:
            a = zshrc.block(a,name,None)
        for name in after:
            b = zshrc.block(b,name,None)
        if a != b:
            raise ValueError('Shell edit changes unmanaged content')
        resources = []
        for name in sorted(before.keys() | after.keys()):
            if before.get(name) == after.get(name):
                continue
            address = {'name':name,'mode':mode}
            if name in {'legacy-status','legacy-restore'} and name in before and name not in after:
                address['placement'] = zshrc.placement(old or b'',name)
            resources.append(_resource('zsh',path,address,_value(before.get(name),name in before),_value(after.get(name),name in after),edit.owner))
        return resources
    return [_resource('file',path,locator,_encode(old),_encode(new),edit.owner)]


def _read(r,runner,context):
    kind,loc = r['kind'],r['locator']
    if kind == 'symlink':
        path = Path(r['target'])
        if path.is_symlink():
            return _value(os.readlink(path))
        if path.exists():
            raise ValueError('Existing non-symlink resource')
        return _value(exists=False)
    if kind == 'preference':
        return preferences.read(runner,r['target'],loc['key'])
    if kind == 'registration':
        if registration_adapter is None:
            raise ValueError('Registration backend unavailable')
        value = registration_adapter.inspect(r['target'],loc['name'],context,runner)
        return _value(value,value is not None)
    return _file_value(r,_bytes(Path(r['target'])))


def _file_value(r,raw):
    kind,loc = r['kind'],r['locator']
    if kind == 'file':
        return _encode(raw)
    if raw is None:
        return _value(exists=False)
    if kind == 'zsh':
        blocks = zshrc.blocks(raw)
        return _value(blocks.get(loc['name']),loc['name'] in blocks)
    parsed = (jsonfile.parse if kind in {'json','hook'} else tomlfile.parse)(raw)
    if kind == 'hook':
        found = _lookup(parsed,loc['pointer'])
        entries = found['value'] if found['exists'] else []
        if not isinstance(entries,list) or entries.count(loc['entry']) > 1:
            raise ValueError('Ambiguous hook entries')
        return _value(loc['entry'],loc['entry'] in entries)
    return _lookup(parsed,loc['pointer'])


def _set(r,value,runner,context, *, expected):
    if not _same(_read(r,runner,context),expected):
        raise ValueError('Concurrent resource edit')
    kind,loc = r['kind'],r['locator']
    if kind == 'symlink':
        path = Path(r['target'])
        if path.exists() and not path.is_symlink():
            raise ValueError('Existing non-symlink resource')
        if not value['exists']:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
            os.close(fd)
            os.unlink(temporary)
            try:
                os.symlink(value['value'],temporary)
                if not _same(_read(r,runner,context),expected):
                    raise ValueError('Concurrent symlink edit during staging')
                os.replace(temporary,path)
            finally:
                if os.path.islink(temporary):
                    os.unlink(temporary)
        directory = os.open(path.parent,os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return
    if kind == 'preference':
        preferences.write(runner,r['target'],loc['key'],value)
        return
    if kind == 'registration':
        if registration_adapter is None:
            raise ValueError('Registration backend unavailable')
        registration_adapter.apply(RegistrationEdit(r['target'],loc['name'],expected['value'] if expected['exists'] else None,value['value'] if value['exists'] else None,'mcp'),context,runner)
        return
    path = Path(r['target'])
    raw = _bytes(path)
    # Validate the exact snapshot used for patching and final bytes CAS.
    if not _same(_file_value(r,raw),expected):
        raise ValueError('Concurrent resource edit before patch')
    if kind == 'file':
        result = base64.b64decode(value['value'],validate=True) if value['exists'] else None
    elif kind == 'hook':
        document = jsonfile.parse(raw or b'{}')
        found = _lookup(document,loc['pointer'])
        entries = list(found['value']) if found['exists'] else []
        if value['exists']:
            entries.append(loc['entry'])
        else:
            entries.remove(loc['entry'])
        result = jsonfile.patch(raw or b'{}',tuple(loc['pointer']),entries)
    elif kind == 'zsh':
        if value['exists'] and not expected['exists'] and 'placement' in loc:
            result = zshrc.restore(raw or b'',loc['name'],value['value'],loc['placement'])
        else:
            result = zshrc.block(raw or b'',loc['name'],value['value'] if value['exists'] else None)
    else:
        patcher = jsonfile.patch if kind=='json' else tomlfile.patch
        result = patcher(raw or (b'{}' if kind=='json' else b''),tuple(loc['pointer']),value['value'],remove=not value['exists'])
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else loc['mode']
    _write_file(path,result,mode,expected=raw)


def _backup(r,context):
    if r['kind'] not in {'file','json','toml','zsh','hook'}:
        return
    raw = _bytes(Path(r['target']))
    if raw is not None:
        directory = context.paths.data/'backups'
        state.private_dir(directory)
        state.durable_write(directory/(uuid.uuid4().hex+'.bak'),raw)


def _inverse(records,runner,context):
    unresolved,findings = [],[]
    for r in reversed(records):
        try:
            current = _read(r,runner,context)
            if _same(current,r['before']):
                continue
            if not _same(current,r['installed']):
                raise ValueError('Concurrent change')
            _set(r,r['before'],runner,context,expected=r['installed'])
            if not _same(_read(r,runner,context),r['before']):
                raise ValueError('Unverified inverse')
        except Exception:
            unresolved.append(r)
            findings.append(_finding('rollback_unresolved','Resource could not be restored safely; retained for recovery: ' + r['target'],r['owners'][0]))
    return list(reversed(unresolved)),findings


@contextmanager
def _lock(context):
    state.private_dir(context.paths.data)
    path = context.paths.data/'transaction.lock'
    fd = os.open(path,os.O_CREAT|os.O_RDWR,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def _recover(context,runner):
    journal = context.paths.data/'journal'
    if not journal.exists():
        return []
    phase = _bytes(journal/'phase')
    if phase == b'commit':
        result = state.load(journal/'result.json')
        if result is None:
            raise ValueError('Missing committed journal')
        state.save(context.paths.data/'receipt.json',result)
        shutil.rmtree(journal)
        return []
    intent = state.load(journal/'intent.json')
    if intent is None:
        # Initialization crashed before a durable intent; no mutations began.
        shutil.rmtree(journal)
        return []
    unresolved,findings = _inverse(intent.resources,runner,context)
    if unresolved:
        intent.resources = unresolved
        state.save(journal/'intent.json',intent)
        return findings
    shutil.rmtree(journal)
    return []


def _transaction(changes,result,context,runner):
    journal = context.paths.data/'journal'
    state.private_dir(journal)
    intent = _empty(result.selection)
    findings = []
    try:
        for r in changes:
            if not _same(_read(r,runner,context),r['before']):
                raise ValueError('Concurrent change')
            _backup(r,context)
            intent.resources.append(r)
            state.save(journal/'intent.json',intent)
            # Recheck after durable intent/backup, immediately before mutation.
            if not _same(_read(r,runner,context),r['before']):
                raise ValueError('Concurrent change')
            _set(r,r['installed'],runner,context,expected=r['before'])
            if not _same(_read(r,runner,context),r['installed']):
                raise ValueError('Write verification failed')
        state.save(journal/'result.json',result)
        state.durable_write(journal/'phase',b'commit')
        state.save(context.paths.data/'receipt.json',result)
        shutil.rmtree(journal)
        return True,[]
    except Exception as error:
        # A committed intent must be completed, never rolled back.
        if _bytes(journal/'phase') == b'commit':
            return False,[_finding('commit_pending','Receipt commit needs recovery before another mutation.')]
        unresolved,findings = _inverse(intent.resources,runner,context)
        findings.insert(0,_finding('transaction_failed','A resource changed or could not be written; transaction was stopped.'))
        if isinstance(error,zshrc.PlacementConflict):
            findings.append(_finding('legacy_placement_conflict','Legacy shell placement changed. Review the surrounding shell lines before retrying; the feature step was rolled back.','migration'))
        if unresolved:
            intent.resources = unresolved
            state.save(journal/'intent.json',intent)
        else:
            shutil.rmtree(journal)
        return False,findings


def pair_resources(resources, selection, context):
    from .models import resource_pairs
    result = copy.deepcopy(resources)
    for resource in result:
        owners = []
        shared = next((o for o in resource['owners'] if o.startswith('shared:')), None)
        for owner in resource['owners']:
            if ':' in owner:
                owners.append(owner)
            else:
                owners.extend(sorted(resource_pairs(selection, owner, resource['target'], context, shared)))
        if shared == 'shared:hooks' and resource['target'] == str((context.paths.codex_home/'hooks.json').resolve()):
            owners = ['shared:codex-hooks' if o == shared else o for o in owners]
        resource['owners'] = list(dict.fromkeys(owners))
    return result


def apply(plan: Plan, context: Context, runner: Runner, *, ui_snapshots=None, remove_owners=frozenset(), expected_receipt=...) -> Outcome:
    empty = _empty(plan.selection)
    findings = list(plan.changes.findings)
    if ((not plan.selection.features and not remove_owners) or not plan.selection.agents or
            any(f.state in {'conflict','missing_dependency','unavailable'} for f in findings)):
        return Outcome(empty,findings or [_finding('invalid_selection','Select agents and features before installation.')])
    try:
        compiled = []
        for edit in plan.changes.edits:
            consumers = None
            if edit.owner.startswith('shared:'):
                consumers = plan.changes.consumers.get(edit.owner)
                if not consumers or not consumers <= (plan.selection.features | plan.selection.pairs):
                    raise ValueError('Shared dependency consumers must be explicit')
            for r in _compile(edit):
                if consumers is not None:
                    r['owners'].extend(sorted(consumers))
                compiled.append(r)
        if not remove_owners and not plan.changes.edits and not plan.changes.ui and not any(f.state == 'ready' for f in findings):
            return Outcome(empty,findings+[_finding('no_implemented_features','No selected feature has an implemented installer.','selection','unavailable')])
        with _lock(context):
            recovery = _recover(context,runner)
            if recovery:
                return Outcome(empty,findings+recovery)
            persisted = state.load(context.paths.data/'receipt.json')
            if expected_receipt is not ... and persisted != expected_receipt:
                raise ValueError('Receipt changed since feature planning')
            previous = persisted or empty
            previous = copy.deepcopy(previous)
            if plan.selection.agent_features is not None:
                previous.resources = pair_resources(previous.resources, previous.selection, context)
            resources = copy.deepcopy(previous.resources)
            # A regenerated builder may describe an implemented no-op. Reuse only
            # addresses already owned by this exact feature/shared marker, never
            # infer ownership from other unchanged values in the same file.
            for edit in plan.changes.edits:
                if not isinstance(edit,FileEdit) or edit.after is None:
                    continue
                for owned in previous.resources:
                    if (owned['target'] != str(_resolve(edit.path)) or
                            edit.owner not in owned['owners'] or
                            owned['kind'] not in {'json','toml','zsh','hook'}):
                        continue
                    before = _file_value(owned,edit.before)
                    after = _file_value(owned,edit.after)
                    if not _same(before,after):
                        continue
                    if not _same(before,owned['installed']):
                        raise ValueError('Owned unchanged address no longer matches')
                    reference = copy.deepcopy(owned)
                    reference['before'] = before
                    reference['installed'] = after
                    reference['owners'] = [edit.owner]
                    if edit.owner.startswith('shared:'):
                        reference['owners'].extend(sorted(plan.changes.consumers[edit.owner]))
                    compiled.append(reference)
            changes = []
            for r in compiled:
                current = _read(r,runner,context)
                own = next((item for item in resources if _identity(item)==_identity(r)),None)
                if own:
                    if not _same(current,own['installed']):
                        raise ValueError('Owned resource changed')
                    if not _same(r['before'],current) and not _same(r['installed'],current):
                        raise ValueError('Stale plan')
                    for owner in r['owners']:
                        if owner not in own['owners']:
                            own['owners'].append(owner)
                    if not _same(r['installed'],current):
                        changes.append(r)
                        own['installed'] = r['installed']
                    if own['kind'] == 'hook' and not own['installed']['exists'] and not own['before']['exists']:
                        resources.remove(own)
                else:
                    # Reuse an exact existing MCP registration without adopting it.
                    if r['kind'] == 'registration' and _same(current,r['installed']):
                        continue
                    if not _same(current,r['before']):
                        raise ValueError('Stale plan')
                    # Existing identical foreign values are not adopted.
                    if not _same(current,r['installed']):
                        resources.append(r)
                        changes.append(r)
            if remove_owners:
                retained = []
                for resource in resources:
                    removed = set(resource['owners']) & remove_owners
                    others = set(resource['owners']) - remove_owners
                    if not removed:
                        retained.append(resource)
                    elif any(not owner.startswith('shared:') for owner in others):
                        resource['owners'] = sorted(others)
                        retained.append(resource)
                    elif not _same(_read(resource,runner,context),resource['installed']):
                        retained.append(resource)
                        findings.append(_finding('uninstall_changed','User-changed value was preserved; ownership remains unresolved.',resource['owners'][0]))
                    else:
                        changes.append(dict(resource,before=resource['installed'],installed=resource['before']))
                resources = retained
            receipt = Receipt(state.VERSION,plan.selection,resources,plan.changes.ui,previous.ui_snapshots if ui_snapshots is None else ui_snapshots)
            ok,failed = _transaction(changes,receipt,context,runner)
            return Outcome(receipt if ok else previous,findings+failed)
    except Exception:
        return Outcome(empty,findings+[_finding('apply_conflict','Configuration or ownership could not be verified; no installation was committed.')])


def revert(receipt: Receipt, context: Context, runner: Runner, owners: frozenset[str]) -> Outcome:
    findings = []
    try:
        state.validate(receipt)
        if not owners:
            return Outcome(receipt,[_finding('invalid_selection','Select features before uninstalling.')])
        with _lock(context):
            findings = _recover(context,runner)
            if findings:
                return Outcome(receipt,findings)
            persisted = state.load(context.paths.data/'receipt.json')
            if persisted != receipt:
                raise ValueError('Receipt does not match private state')
            remaining,changes = [],[]
            for original in receipt.resources:
                r = copy.deepcopy(original)
                removed = set(r['owners']) & owners
                if not removed:
                    remaining.append(r)
                    continue
                others = set(r['owners']) - owners
                if any(not owner.startswith('shared:') for owner in others):
                    r['owners'] = sorted(others)
                    remaining.append(r)
                    continue
                if not _same(_read(r,runner,context),r['installed']):
                    remaining.append(r)
                    findings.append(_finding('uninstall_changed','User-changed value was preserved; ownership remains unresolved.',r['owners'][0]))
                    continue
                changes.append(dict(r,before=r['installed'],installed=r['before']))
            result = Receipt(state.VERSION,receipt.selection,remaining,receipt.pending_ui,receipt.ui_snapshots)
            ok,failed = _transaction(changes,result,context,runner)
            return Outcome(result if ok else receipt,findings+failed)
    except Exception:
        return Outcome(receipt,findings+[_finding('ownership_unavailable','Valid current ownership is required before uninstalling.')])
