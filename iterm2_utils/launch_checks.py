"""Bounded launch checks. No settings writes, GUI mutation or TOML reimplementation."""
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from runtime.codex_restore.codexlib import transcripts

from .commands import Runner
from .config import preferences
from .discovery import _iterm, platform
from .models import Finding, Paths

DOMAIN = 'com.googlecode.iterm2'
FUNCTIONS = ('codex', '_iterm2_utils_classify', '_codex_restore_previous',
             '_codex_restore_call', '_codex_restore_classify',
             '_codex_restore_previous_call', '_codex_restore_sessions')
_RESUME_TIMEOUT = 10
_HEADER_LIMIT = 64 * 1024  # A malformed header must not consume an entire conversation.


@dataclass(frozen=True)
class LaunchRequest:
    window_id: str
    profile: str
    cwd: Path
    handoff: Path | None = None
    resume_session_id: str | None = None

    @property
    def launch_mode(self) -> str:
        return 'resume' if self.resume_session_id is not None else 'handoff'


@dataclass(frozen=True)
class LaunchIdentity:
    executable: Path
    version: str
    home: Path
    codex_home: Path
    zdotdir: Path
    wrapper_fingerprint: str
    restore_root: str
    python: str


@dataclass(frozen=True)
class LaunchInspection:
    it2: Path
    zsh: Path
    profile_guid: str
    identity: LaunchIdentity


def _finding(code, message, state='unavailable'):
    return Finding('launch', 'codex', code, state, message)


def _valid_name(value):
    return isinstance(value, str) and bool(value.strip()) and not any(
        unicodedata.category(char) == 'Cc' for char in value)


def validate_request(request: LaunchRequest) -> None:
    if not _valid_name(request.window_id) or not _valid_name(request.profile):
        raise ValueError('launch_invalid_target')
    if (request.handoff is None) == (request.resume_session_id is None):
        raise ValueError('launch_invalid_mode')
    if request.resume_session_id is not None:
        try:
            transcripts.normalize_uuid(request.resume_session_id)
        except ValueError:
            raise ValueError('launch_invalid_resume') from None
    for path in (request.cwd, *([request.handoff] if request.handoff is not None else [])):
        if not isinstance(path, Path) or not path.is_absolute() or '\0' in str(path):
            raise ValueError('launch_invalid_path')
    try:
        if not request.cwd.is_dir():
            raise ValueError('launch_invalid_cwd')
    except OSError:
        raise ValueError('launch_invalid_cwd') from None
    if request.handoff is None:
        return
    try:
        info = request.handoff.lstat()
        if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o444:
            raise ValueError('launch_invalid_handoff')
        # O_NOFOLLOW/nonblocking avoid following or hanging on a replaced FIFO/link.
        fd = os.open(request.handoff, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('launch_invalid_handoff')
        finally:
            os.close(fd)
    except OSError:
        raise ValueError('launch_invalid_handoff') from None


def _resume_lookup(codex_home: Path, cwd: Path, session_id: str) -> bool:
    """Run only in a bounded worker; directory descriptors prevent symlink races."""
    def walk(directory, path):
        count = 0
        with os.scandir(directory) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=directory)
                    try:
                        count += walk(child, path/entry.name)
                    finally:
                        os.close(child)
                elif re.search(r'(?:^|-)'+re.escape(session_id)+r'\.jsonl$', entry.name.lower()):
                    if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o444:
                        raise ValueError('unsafe transcript')
                    fd = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=directory)
                    with os.fdopen(fd, 'rb', buffering=0) as stream:
                        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                            raise ValueError('unsafe transcript')
                        header = stream.readline(_HEADER_LIMIT+1)
                    if len(header) > _HEADER_LIMIT:
                        raise ValueError('oversized header')
                    header = json.loads(header)
                    if not isinstance(header, dict):
                        raise ValueError('invalid header')
                    if transcripts.validate(path/entry.name, session_id, codex_home, cwd, header=header):
                        count += 1
                if count > 1:
                    return count
        return count

    try:
        home = codex_home.resolve()
        sessions = home/'sessions'
        directory = os.open(sessions, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            return walk(directory, sessions) == 1
        finally:
            os.close(directory)
    except (OSError, ValueError, TypeError, RuntimeError, RecursionError):
        return False


def validate_resume(request: LaunchRequest, identity: LaunchIdentity) -> None:
    sid = transcripts.normalize_uuid(request.resume_session_id)
    code = ('import sys; from pathlib import Path; '
            f'sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r}); '
            'from iterm2_utils.launch_checks import _resume_lookup; '
            'sys.exit(0 if _resume_lookup(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]) else 2)')
    try:
        result = subprocess.run([sys.executable, '-c', code, str(identity.codex_home), str(request.cwd), sid],
                                timeout=_RESUME_TIMEOUT, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            return
    except (OSError, subprocess.SubprocessError):
        pass
    raise ValueError('launch_resume_unverified')


def check_profile(profile: dict) -> list[Finding]:
    keys = profile.get('Keyboard Map') if isinstance(profile, dict) else None
    if not isinstance(keys, dict):
        return [_finding('launch_profile_unverified', 'Materialized profile bindings are unavailable; use iterm2-setup.')]
    for char in ('0x63', '0x441'):
        for mask, wanted in (('0x40000', b'\x03'), ('0x100000', b'\x1b[99;9u')):
            binding = keys.get(f'{char}-{mask}-0x8-0x1')
            try:
                if not isinstance(binding, dict) or type(binding.get('Action')) is not int or binding['Action'] != 11:
                    raise ValueError
                tokens = binding['Text'].split()
                if not tokens or any(not re.fullmatch(r'(?:0[xX])?[0-9a-fA-F]{1,2}', token) for token in tokens):
                    raise ValueError
                if bytes(int(token, 16) for token in tokens) != wanted:
                    raise ValueError
            except (ValueError, KeyError, AttributeError, TypeError):
                return [_finding('launch_profile_bindings', 'Codex copy bindings differ; use iterm2-setup.', 'conflict')]
    return []


def _body(value):
    # zsh canonical function bodies may differ only by surrounding whitespace.
    return value.strip()


def _identity(raw):
    functions = raw['functions']
    if not isinstance(functions, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in functions.items()):
        raise ValueError('launch_config_unverified')
    fingerprint = hashlib.sha256(json.dumps({k: _body(v) for k, v in functions.items() if v},
                                sort_keys=True).encode()).hexdigest()
    paths = [Path(raw[key]) for key in ('executable', 'home', 'codex_home', 'zdotdir')]
    if not all(p.is_absolute() and '\0' not in str(p) for p in paths):
        raise ValueError('launch_config_unverified')
    if raw.get('alias') or raw['version'].strip() != 'codex-cli 0.166.0':
        raise ValueError('launch_config_unverified')
    return LaunchIdentity(paths[0], '0.166.0', paths[1], paths[2], paths[3], fingerprint,
                          raw['restore_root'], raw['python'])


def _metadata_command(paths, expected=None):
    """Private function bodies go only to the transport, never public diagnostics."""
    keys = ('executable', 'version', 'home', 'codex_home', 'zdotdir', 'alias', 'restore_root', 'python')
    expressions = ('${commands[codex]-}', '$("${commands[codex]}" --version 2>/dev/null)',
                   '${HOME-}', '${CODEX_HOME:-$HOME/.codex}', '${ZDOTDIR:-$HOME}',
                   '${aliases[codex]-}', '${_codex_restore_root-}', '${ITERM2_UTILS_PYTHON-}')
    code = ('import json,sys; ' + f'raw=dict(zip({keys!r},sys.argv[1:9])); ' +
            f'raw["functions"]=dict(zip({FUNCTIONS!r},sys.argv[9:])); ')
    if expected is None:
        code += 'print(chr(10)+json.dumps({"iterm2_launch_identity":raw}),flush=True)'
    else:
        values = asdict(expected)
        values = {key: str(value) if isinstance(value, Path) else value for key, value in values.items()}
        code += (f'sys.path.insert(0,{str(paths.repo)!r}); '
                 'from iterm2_utils.launch_checks import _identity; '
                 f'sys.exit(0 if {{k:str(v) for k,v in vars(_identity(raw)).items()}}=={values!r} else 1)')
    args = [f'"{value}"' for value in expressions]
    args.extend(f'"${{functions[{name}]-}}"' for name in FUNCTIONS)
    return shlex.join([sys.executable, '-c', code])+' '+' '.join(args)


def identity_guard(paths: Paths, identity: LaunchIdentity) -> str:
    """Task 3 runs this in its login shell before the original codex invocation."""
    return _metadata_command(paths, identity)+' 2>/dev/null'


def _references(paths, zsh, runner, env):
    # A clean non-login shell canonicalizes only the shipped function definitions.
    script = ('builtin source '+shlex.quote(str(paths.repo/'runtime/codex.zsh'))+' || exit 1\n'
              'typeset dispatcher=$functions[codex]\n'
              'function _launch_direct { command codex "$@" }\n'
              'function _launch_simple { command codex --no-daemon "$@" }\n'
              'unfunction codex\n'
              'builtin source '+shlex.quote(str(paths.repo/'runtime/codex_restore/codex-resume.zsh'))+' || exit 1\n')
    names = ('direct', 'simple', 'dispatcher', '_iterm2_utils_classify', 'restore',
             '_codex_restore_call', '_codex_restore_classify', '_codex_restore_previous_call', '_codex_restore_sessions')
    args = ('"$functions[_launch_direct]" "$functions[_launch_simple]" "$dispatcher" '
            '"$functions[_iterm2_utils_classify]" "$functions[codex]" '
            '"$functions[_codex_restore_call]" "$functions[_codex_restore_classify]" '
            '"$functions[_codex_restore_previous_call]" "$functions[_codex_restore_sessions]"')
    code = f'import json,sys; print(json.dumps(dict(zip({names!r},sys.argv[1:]))))'
    script += shlex.join([sys.executable, '-c', code])+' '+args
    result = runner.run([str(zsh), '-dfc', script], timeout=5, env=env)
    if result.returncode:
        raise ValueError('launch_config_unverified')
    reference = json.loads(result.stdout)
    if not isinstance(reference, dict) or any(not isinstance(reference.get(name), str) for name in names):
        raise ValueError('launch_config_unverified')
    return reference


def _check_wrapper(raw, reference, paths):
    identity = _identity(raw)
    if not identity.executable.is_file() or not os.access(identity.executable, os.X_OK):
        raise ValueError('launch_missing_codex')
    functions = raw['functions']

    def matches(actual, expected):
        return isinstance(actual, str) and _body(actual) == _body(reference[expected])

    def dispatcher(body):
        return matches(body, 'dispatcher') and matches(functions.get('_iterm2_utils_classify'), '_iterm2_utils_classify')

    current = functions.get('codex', '')
    valid = not current or matches(current, 'direct') or matches(current, 'simple') or dispatcher(current)
    if matches(current, 'restore'):
        required = ('_codex_restore_call', '_codex_restore_classify', '_codex_restore_previous_call', '_codex_restore_sessions')
        previous = functions.get('_codex_restore_previous', '')
        valid = all(matches(functions.get(name), name) for name in required) and (
            not previous or matches(previous, 'direct') or matches(previous, 'simple') or dispatcher(previous))
        # Registration is part of the shipped wrapper; verify its external helper provenance too.
        root = Path(identity.restore_root)
        if not root.is_absolute():
            valid = False
        if valid:
            source = paths.repo/'runtime/codex_restore'
            for file in source.rglob('*'):
                if file.is_file() and '__pycache__' not in file.parts and (file.suffix in {'.py', '.zsh'} or file.name == 'codex-sessions'):
                    relative = file.relative_to(source)
                    installed = (root/relative).read_bytes()
                    # e90b332 sources.lock.json pins this helper before the optional header API.
                    previous = relative.as_posix() == 'codexlib/transcripts.py' and hashlib.sha256(installed).hexdigest() == (
                        'e68b9119054a44cfa90897a79887fd7437e64695f449f5fddc6b55e029e59f74')
                    if installed != file.read_bytes() and not previous:
                        valid = False
                        break
    if not valid:
        raise ValueError('launch_config_unverified')
    return identity


def inspect_launch(paths: Paths, request: LaunchRequest, runner: Runner) -> tuple[LaunchInspection | None, list[Finding]]:
    try:
        validate_request(request)
    except ValueError as error:
        return None, [_finding(str(error), 'Launch inputs are invalid.')]
    if platform.system() != 'Darwin':
        return None, [_finding('launch_platform', 'Codex launch requires macOS.')]
    app, _ = _iterm(paths)
    zsh = shutil.which('zsh')
    if not app or not zsh or not Path(zsh).is_absolute():
        return None, [_finding('launch_dependency', 'A verified iTerm2 bundle and zsh are required.')]
    it2 = app/'Contents/Resources/utilities/it2'
    if not it2.is_file() or not os.access(it2, os.X_OK) or it2.resolve() != app.resolve()/'Contents/Resources/utilities/it2':
        return None, [_finding('launch_dependency', 'The selected iTerm2 bundle must contain executable it2.')]
    try:
        def query(args):
            result = runner.run([str(it2), *args], timeout=5)
            if result.returncode:
                raise ValueError('launch_protocol')
            return result.stdout

        windows = json.loads(query(['window', 'list', '--json']))
        if not isinstance(windows, list) or sum(isinstance(w, dict) and w.get('id') == request.window_id for w in windows) != 1:
            return None, [_finding('launch_window', 'The explicit target window is unavailable or ambiguous.')]
        live = json.loads(query(['profile', 'list', '--json']))
        if not isinstance(live, list):
            raise ValueError('launch_profile_unverified')
        selected = [p for p in live if isinstance(p, dict) and p.get('name') == request.profile]
        if len(selected) != 1 or not _valid_name(selected[0].get('guid')):
            return None, [_finding('launch_profile_unverified', 'The live profile name must resolve to one GUID.')]
        guid = selected[0]['guid']
        if sum(isinstance(p, dict) and p.get('guid') == guid for p in live) != 1:
            raise ValueError('launch_profile_unverified')
        raw = preferences.read(runner, DOMAIN, 'New Bookmarks')
        if not raw['exists'] or not isinstance(raw['value'], list):
            raise ValueError('launch_profile_unverified')
        selected_raw = [p for p in raw['value'] if isinstance(p, dict) and
                        (p.get('Guid') == guid or p.get('Name') == request.profile)]
        if len(selected_raw) != 1 or selected_raw[0].get('Guid') != guid or selected_raw[0].get('Name') != request.profile:
            raise ValueError('launch_profile_unverified')
        findings = check_profile(selected_raw[0])
        if findings:
            return None, findings
        copy = preferences.read(runner, DOMAIN, 'CopySelection')
        if not copy['exists'] or copy['value'] is not False:
            return None, [_finding('launch_copy_selection', 'Disable iTerm2 CopySelection using iterm2-setup.', 'conflict')]
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        return None, [_finding('launch_profile_unverified', 'Window/profile state could not be verified; use iterm2-setup.')]
    try:
        env = dict(os.environ, CODEX_RESTORE_NO_AUTO='1')
        env.pop('ITERM_SESSION_ID', None)
        env.pop('TERM_SESSION_ID', None)
        reference = _references(paths, Path(zsh), runner, env)
        script = (_metadata_command(paths)+'\n'
                  'IFS= read -r _iterm2_launch_continue || exit 1\n'
                  '[[ $_iterm2_launch_continue == iterm2-utils-continue ]] || exit 1\n'
                  'codex app-server --stdio')
        identity, config = runner.codex_config([zsh, '-ilc', script], timeout=10, env=env,
            cwd=request.cwd, check_identity=lambda raw: _check_wrapper(raw, reference, paths))
        tui = config.get('tui', {})
        if not isinstance(tui, dict):
            raise ValueError('launch_config_unverified')
        if tui.get('alternate_screen', 'auto') not in {'auto', 'always'} or tui.get('fullscreen_transcript', True) is not True:
            return None, [_finding('launch_tui_mode', 'Codex needs its fullscreen alternate-screen transcript; use iterm2-setup.', 'conflict')]
        if tui.get('copy_on_select', 'auto') != 'never':
            return None, [_finding('launch_copy_on_select', 'Set effective Codex tui.copy_on_select to never using iterm2-setup.', 'conflict')]
        if request.resume_session_id is not None:
            try:
                validate_resume(request, identity)
            except ValueError:
                return None, [_finding('launch_resume_unverified', 'The requested interactive transcript is unavailable, unsafe or ambiguous.')]
        return LaunchInspection(it2, Path(zsh), guid, identity), []
    except (OSError, ValueError, TypeError, KeyError, AttributeError, TimeoutError, subprocess.SubprocessError):
        return None, [_finding('launch_config_unverified', 'Effective Codex configuration or shell wrapper could not be verified; use iterm2-setup.')]
