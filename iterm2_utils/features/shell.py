"""Pure builders for installed, checkout-independent zsh/runtime resources.

runtime/ maps directly to current/; vendor/ maps to current/vendor/.
Future hook.py and codex_restore/ modules belong under runtime/ and may use
sibling imports through their installed script directory. No checkout sys.path.
"""
import hashlib
import os
import re
import shlex
from pathlib import Path
from .. import __version__
from ..config import zshrc
from ..models import ChangeSet, Context, Selection, FileEdit, SymlinkEdit, Finding

OWNER = 'shared:shell'
RUNTIME_OWNER = 'shared:runtime'
DEPENDENTS = frozenset({'status', 'notifications', 'restore'})


def _dispatcher(selection):
    return bool(selection.features_for('codex') & DEPENDENTS)


def _consumers(selection):
    return frozenset(a+':'+feature for a in selection.agents
                     for feature in selection.features_for(a)
                     if feature=='shell' or a=='codex' and feature in DEPENDENTS
                     or a=='claude' and feature=='notifications')


def runtime_payload(context: Context, selection: Selection) -> ChangeSet:
    """Copy validated source trees before switching the stable current symlink.

    Only runtime Python/zsh, vendor Python/zsh/license and package helpers are
    eligible, together with root license/attribution. Mutable caches/configuration
    never belong in the release tree.
    """
    changes = ChangeSet([], [], [])
    consumers = _consumers(selection)
    if not consumers:
        return changes
    files = {}
    for tree in ('runtime', 'vendor'):
        root = context.paths.repo / tree
        if root.is_symlink() or not root.is_dir():
            raise ValueError('Missing runtime source tree')
        for source in sorted(root.rglob('*')):
            if source.is_symlink():
                raise ValueError('Runtime source symlinks are not allowed')
            if not source.is_file() or '__pycache__' in source.parts:
                continue
            if source.suffix not in {'.py', '.zsh'} and source.name not in {'LICENSE', 'NOTICE', 'codex-sessions'}:
                continue
            relative = source.relative_to(root)
            target = relative if tree == 'runtime' else Path('vendor') / relative
            files[target] = source.read_bytes()
    if Path('codex.zsh') not in files or Path('vendor/shell_integration/iterm2_shell_integration.zsh') not in files:
        raise ValueError('Incomplete runtime payload')
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        source = context.paths.repo/name
        if source.is_symlink() or not source.is_file():
            raise ValueError('Missing runtime license or attribution')
        files[Path(name)] = source.read_bytes()
    digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        digest.update(str(name).encode()+b'\0'+content+b'\0')
    release = context.paths.data / 'releases' / (__version__+'-'+digest.hexdigest()[:20])
    # All reads/validation complete before any edits are emitted; engine applies
    # file edits in order and atomically switches the explicit symlink last.
    for name, content in sorted(files.items()):
        path = release / name
        before = path.read_bytes() if path.exists() else None
        if before is not None and before != content:
            raise ValueError('Immutable release content changed')
        changes.edits.append(FileEdit(path,before,content,0o700 if name == Path("codex_restore/codex-sessions") else 0o600,RUNTIME_OWNER))
    current = context.paths.data / 'current'
    if current.exists() and not current.is_symlink():
        raise ValueError('Runtime current must be a symlink')
    changes.edits.append(SymlinkEdit(current,os.readlink(current) if current.is_symlink() else None,str(release),RUNTIME_OWNER))
    changes.consumers[RUNTIME_OWNER] = frozenset(consumers)
    return changes


def build(context: Context, selection: Selection) -> ChangeSet:
    changes = ChangeSet([], [], [])
    marks = 'shell' in selection.features
    dispatch = _dispatcher(selection)
    if not marks and not dispatch:
        return changes
    path = context.paths.zshrc
    before = path.read_bytes() if path.exists() else None
    try:
        from .. import migration
        base = migration.shell_before(context,selection,before) if dispatch else (before or b'')
        managed = zshrc.blocks(base)
        foreign = base
        for name in managed:
            foreign = zshrc.block(foreign,name,None)
        text = foreign.decode()
        # Known old managed wrappers must be deliberately adopted, never nested.
        if re.search(r'(?m)^\s*#.*(?:codex.*(?:wrapper|no.daemon)|(?:>>>|BEGIN).*codex)', text, re.I):
            raise ValueError('Legacy managed Codex block requires migration')
        if dispatch and re.search(r'(?m)^\s*(?:alias(?:\s+-\S+)*\s+codex\s*=|(?:function\s+)?codex\s*\(\s*\)|function\s+codex\b)', text):
            raise ValueError('Existing Codex alias or function')
        reuse = marks and bool(re.search(r'(?m)^\s*(?:source|\.)\s+[^\n]*iterm2_shell_integration',text))
        lines = []
        current = context.paths.data / 'current'
        quote = lambda value: shlex.quote(str(value))
        if marks and not reuse:
            lines.extend(['if [[ ${TERM_PROGRAM-} == iTerm.app && -z ${ITERM_SHELL_INTEGRATION_INSTALLED-} ]]; then',
                          '  source '+quote(current/'vendor/shell_integration/iterm2_shell_integration.zsh'), 'fi'])
        if reuse:
            changes.findings.append(Finding('shell',None,'existing_integration','ready','Existing shell integration is reused.'))
        if dispatch:
            lines.extend(['typeset -g ITERM2_UTILS_PYTHON='+quote(context.executables['python3']),
                          'typeset -g ITERM2_UTILS_CODEX_NO_DAEMON='+('1' if 'codex:no-daemon' in context.capabilities else '0'),
                          'source '+quote(current/'codex.zsh')])
            if 'restore' in selection.features_for('codex'):
                lines.extend(['export CODEX_RESTORE_IT2='+quote(context.executables['it2']),
                              'export CODEX_RESTORE_ITERM_PROCESS='+quote(context.executables['iterm2']/'Contents/MacOS/iTerm2'),
                              'export CODEX_RESTORE_CACHE_DIR='+quote(context.paths.cache/'restore'),
                              'typeset -g _codex_restore_no_daemon=1',
                              '[[ -n ${CODEX_HOME+x} ]] || export CODEX_HOME='+quote(context.paths.codex_home)])
                restore = quote(current/'codex_restore/codex-resume.zsh')
                lines.append('[[ ! -f '+restore+' ]] || source '+restore)
        # A no-op existing integration needs no ownership claim.
        if lines or 'root' in managed:
            after = zshrc.block(base,'root','\n'.join(lines) if lines else None)
            changes.edits.append(FileEdit(path,before,after,0o600,OWNER))
            changes.consumers[OWNER] = frozenset(p for p in _consumers(selection) if p.endswith(':shell') or dispatch and p.startswith('codex:'))
    except (ValueError, UnicodeError):
        changes.findings.append(Finding('shell',None,'shell_conflict','conflict','Shell startup contains conflicting or ambiguous managed integration; explicit migration is required.'))
    return changes
