"""Explicit transfer of narrowly recognized legacy resources; no installers run."""
import shlex
import hashlib
import json
from pathlib import Path
from .config import jsonfile, tomlfile, zshrc
from .models import ChangeSet, FileEdit, Finding

# Exact public wrapper body from the reference installer; comments are ignored.
STATUS_BODY = '''function codex {
  case "${1-}" in
    agents|remote-control|app-server)
      command codex "$@" ;;
    *)
      if (( ! ${@[(Ie)--no-daemon]} )) \\
         && command codex --help 2>/dev/null | grep -q -- --no-daemon; then
        command codex --no-daemon "$@"
      else
        command codex "$@"
      fi ;;
  esac
}'''


def _body(value):
    return '\n'.join(line.rstrip() for line in value.splitlines() if line.strip() and not line.lstrip().startswith('#'))


def _recognized(name, body, context):
    if name == 'legacy-status':
        return _body(body) == STATUS_BODY
    # Source-only exact absolute path, backed by the pinned distributed script.
    # A file with merely the same basename is never sufficient evidence.
    try:
        words = shlex.split(body)
        if len(words) != 2 or words[0] != 'source' or '\n' in body:
            return False
        path = Path(words[1])
        reference = context.paths.repo/'runtime/codex_restore/codex-resume.zsh'
        if not path.is_absolute() or not path.is_file():
            return False
        raw = path.read_bytes()
        if raw == reference.read_bytes():
            return True
        # Package interpreter adaptation must not invalidate the pinned legacy
        # source identity that explicit adoption was designed to recognize.
        lock = json.loads((context.paths.repo/'sources.lock.json').read_bytes())
        original = next(e['upstream_sha256'] for e in lock['sources']
                        if e['path']=='runtime/codex_restore/codex-resume.zsh')
        return hashlib.sha256(raw).hexdigest() == original
    except (OSError,ValueError,KeyError,StopIteration):
        return False


def shell_before(context, selection, before):
    blocks = zshrc.blocks(before or b'')
    result = before or b''
    relevant = {'legacy-status':'status','legacy-restore':'restore'}
    for name, feature in relevant.items():
        if name not in blocks:
            continue
        if not selection.adopt_legacy or feature not in selection.features:
            raise ValueError('Legacy shell integration requires explicit adoption of its feature')
        if not _recognized(name,blocks[name],context):
            raise ValueError('Unknown legacy shell block')
        result = zshrc.block(result,name,None)
    return result


def inspect(context):
    findings = []
    try:
        path = context.paths.codex_home/'config.toml'
        plugins = tomlfile.parse(path.read_bytes() if path.exists() else b'').get('plugins',{})
        for key,value in plugins.items():
            if key.split('@',1)[0] in {'iterm2-status','codex-iterm2-status'} and isinstance(value,dict) and value.get('enabled') is True:
                findings.append(Finding('status','codex','legacy_status','ready','Existing enabled status plugin can be reused; --adopt-legacy explicitly transfers ownership.'))
        path = context.paths.zshrc
        for name,body in zshrc.blocks(path.read_bytes() if path.exists() else b'').items():
            if name.startswith('legacy-'):
                feature = 'status' if name == 'legacy-status' else 'restore'
                known = _recognized(name,body,context)
                findings.append(Finding(feature,'codex','legacy_block','ready' if known else 'conflict','Recognized legacy shell block; explicit adoption is required.' if known else 'Unknown legacy shell block; review it manually.'))
    except (ValueError,OSError,AttributeError):
        findings.append(Finding('migration',None,'legacy_conflict','conflict','Legacy configuration could not be safely inspected.'))
    return findings


def build(context, selection):
    changes = ChangeSet([],[],[])
    if not selection.adopt_legacy or 'codex' not in selection.agents:
        return changes
    if 'restore' in selection.features:
        try:
            edit = _restore_hooks(context)
            if edit is not None:
                changes.edits.append(edit)
        except (ValueError,OSError,TypeError,AttributeError):
            changes.findings.append(Finding('restore','codex','legacy_restore_hook_conflict','conflict',
                'Legacy restore hooks differ from the recognized source command/schema; review them manually before adoption.'))
    if 'status' in selection.features:
        path = context.paths.codex_home/'config.toml'
        before = path.read_bytes() if path.exists() else None
        try:
            plugins = tomlfile.parse(before or b'').get('plugins',{})
            after = before or b''
            for key,value in plugins.items():
                if key.split('@',1)[0] in {'iterm2-status','codex-iterm2-status'} and isinstance(value,dict) and value.get('enabled') is True:
                    # enabled is Codex's supported plugin toggle; source/cache stay intact.
                    after = tomlfile.patch(after,('plugins',key,'enabled'),False)
            if after != (before or b''):
                changes.edits.append(FileEdit(path,before,after,0o600,'status'))
        except (ValueError,AttributeError):
            changes.findings.append(Finding('status','codex','legacy_conflict','conflict','The exact legacy plugin enabled value cannot be safely changed.'))
    return changes


def _restore_hooks(context):
    """Transfer only the installer schema tied to a verified legacy source root."""
    shell = context.paths.zshrc
    block = zshrc.blocks(shell.read_bytes() if shell.exists() else b'').get('legacy-restore')
    if block is None:
        return None
    if not _recognized('legacy-restore',block,context):
        raise ValueError('Unknown legacy source')
    old_root = Path(shlex.split(block)[1]).parent
    command = shlex.quote(str(old_root/'codex-sessions'))+' hook'
    expected = {'hooks':[{'type':'command','command':command,'timeout':3}]}
    path = context.paths.codex_home/'hooks.json'
    before = path.read_bytes() if path.exists() else None
    document = jsonfile.parse(before or b'{}')
    hooks = document.get('hooks',{})
    if not isinstance(hooks,dict):
        raise ValueError('Invalid hooks object')
    changed = False
    for event in ('SessionStart','UserPromptSubmit','Stop'):
        entries = hooks.get(event,[])
        if not isinstance(entries,list):
            raise ValueError('Invalid hook event')
        kept = []
        for entry in entries:
            if not isinstance(entry,dict) or not isinstance(entry.get('hooks'),list):
                raise ValueError('Invalid hook group')
            known_command = any(isinstance(handler,dict) and handler.get('command') == command
                                for handler in entry['hooks'])
            if known_command:
                if entry != expected:
                    raise ValueError('Changed legacy hook schema')
                changed = True
            else:
                kept.append(entry)
        if len(entries)-len(kept) > 1:
            raise ValueError('Ambiguous legacy hooks')
        if len(kept) != len(entries):
            hooks[event] = kept
    if not changed:
        return None
    return FileEdit(path,before,(json.dumps(document,ensure_ascii=False,indent=2)+'\n').encode(),0o600,'restore')
