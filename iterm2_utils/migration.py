"""Explicit transfer of narrowly recognized legacy resources; no installers run."""
import shlex
from pathlib import Path
from .config import tomlfile, zshrc
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
        return path.is_absolute() and path.is_file() and path.read_bytes() == reference.read_bytes()
    except (OSError,ValueError):
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
