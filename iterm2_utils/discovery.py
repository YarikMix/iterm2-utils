"""Inspection only: no shell startup files are executed and no GUI is launched."""
import json
import os
import platform
import plistlib
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from .commands import Runner
from .models import Context, Paths

NATIVE_STATUS_FLAGS = frozenset({
    '--background-tasks', '--background-tasks-delta', '--turn-open',
    '--if-turn-open', '--if-background-tasks', '--json',
})


def _native_utility(app, name):
    path = app / 'Contents/Resources/utilities' / name
    try:
        expected = app.resolve() / 'Contents/Resources/utilities' / name
        return path.is_file() and os.access(path, os.X_OK) and path.resolve() == expected
    except (OSError, RuntimeError):
        return False


def _native_version(info):
    version = info.get('CFBundleShortVersionString')
    if not isinstance(version, str) or not re.fullmatch(r'[0-9]+\.[0-9]+(?:\.[0-9]+)?', version):
        return False
    parts = tuple(int(part) for part in version.split('.'))
    return (parts + (0,) * (3 - len(parts))) >= (3, 7, 6)


def resolve_paths() -> Paths:
    home = Path.home().absolute()

    def location(key, default):
        value = Path(os.environ.get(key, str(default))).expanduser()
        # Relative XDG overrides are invalid; never resolve them against caller cwd.
        return value if value.is_absolute() else default

    return Paths(home, location('ZDOTDIR', home) / '.zshrc',
                 location('CODEX_HOME', home / '.codex'),
                 home / '.claude/settings.json',
                 location('XDG_CONFIG_HOME', home / '.config') / 'iterm2-utils',
                 location('XDG_CACHE_HOME', home / '.cache') / 'iterm2-utils',
                 location('XDG_DATA_HOME', home / '.local/share') / 'iterm2-utils',
                 home / 'Library/Application Support/iTerm2/DynamicProfiles',
                 Path(__file__).resolve().parent.parent)


def _probe(runner, binary, args):
    try:
        result = runner.run([str(binary), *args], timeout=5)
        return result.stdout if result.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return ''


def _version(output):
    match = re.search(r'\b\d+\.\d+(?:\.\d+)?\b', output)
    return match.group() if match else 'unknown'


def _iterm(paths):
    override = os.environ.get('ITERM2_APP')
    candidates = [Path(override).expanduser()] if override else [Path('/Applications/iTerm.app'), paths.home / 'Applications/iTerm.app']
    for app in candidates:
        if not app.is_absolute():
            continue
        try:
            info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
            name = info.get('CFBundleExecutable', 'iTerm2')
            if info.get('CFBundleIdentifier') != 'com.googlecode.iterm2' or not isinstance(name, str) or Path(name).name != name:
                continue
            binary = app / 'Contents/MacOS' / name
            if binary.is_file() and os.access(binary, os.X_OK):
                return app, info
        except (OSError, ValueError, plistlib.InvalidFileException, AttributeError):
            continue
    return None, {}


def discover(paths: Paths, runner: Runner, *, agents: frozenset[str] = frozenset({'codex', 'claude'})) -> Context:
    executables, versions, capabilities = {}, {}, set()
    if platform.system() == 'Darwin':
        capabilities.add('macos')
    for name in sorted(agents | {'zsh', 'python3', 'terminal-notifier', 'peekaboo', 'fzf', 'uvx'}):
        found = os.environ.get('ITERM2_UTILS_PYTHON') if name == 'python3' and os.environ.get('ITERM2_UTILS_PYTHON') else shutil.which(name)
        if found and not Path(found).is_absolute():
            found = None
        if not found:
            continue
        binary = Path(found).absolute()
        output = _probe(runner, binary, ['--version'])
        if not output:
            continue
        executables[name] = binary
        versions[name] = _version(output)
        # Current official docs + release v2.1.308 (2026-10-22) document
        # Option+Enter. No support is inferred for older/future releases.
        if name == 'claude' and versions[name] == '2.1.308':
            capabilities.add('claude:alt-enter')
        if name == 'codex':
            help_output = _probe(runner, binary, ['--help'])
            if '--no-daemon' in help_output:
                capabilities.add('codex:no-daemon')
            # Verified default keymap in rust-v0.163.0; no historical/future floor.
            if versions[name] == '0.163.0':
                capabilities.add('codex:alt-enter')
                capabilities.add('codex:approval-notifications')
    osascript = shutil.which('osascript')
    if osascript:
        executables['osascript'] = Path(osascript).absolute()
    app, info = _iterm(paths)
    if app:
        executables['iterm2'] = app
        versions['iterm2'] = _version(str(info.get('CFBundleShortVersionString', '')))
        it2 = app / 'Contents/Resources/utilities/it2'
        if not it2.is_file():
            it2 = app / 'Contents/Resources/it2'
        if it2.is_file() and os.access(it2, os.X_OK):
            output = _probe(runner, it2, ['--help'])
            if 'set-status' in output or 'session-status' in output:
                capabilities.add('iterm2:session-status')
            if output:
                executables['it2'] = it2
        if _native_version(info) and all(_native_utility(app, name) for name in ('it2', 'cc-status')):
            output = _probe(runner, app / 'Contents/Resources/utilities/it2', ['set-status', '--help'])
            flags = set(re.findall(r'(?<![\w-])--[a-z][a-z-]*(?![\w-])', output))
            if NATIVE_STATUS_FLAGS <= flags:
                capabilities.add('iterm2:cc-status-codex')
    preferences = {}
    profiles = {}
    if app:
        try:
            result = runner.run(['defaults', 'export', 'com.googlecode.iterm2', '-'], timeout=5)
            values = plistlib.loads(result.stdout.encode()) if result.returncode == 0 else {}
            allowed = {key: values[key] for key in ('CopySelection',) if key in values and isinstance(values[key], bool)}
            preferences['com.googlecode.iterm2'] = allowed
            for profile in values.get('New Bookmarks', []):
                if isinstance(profile, dict) and isinstance(profile.get('Name'), str):
                    profiles[profile['Name']] = profile
        except (OSError, ValueError, TypeError, AttributeError, plistlib.InvalidFileException, subprocess.SubprocessError):
            pass
    if paths.profiles.is_dir():
        for path in sorted(paths.profiles.glob('*.json')):
            try:
                document = json.loads(path.read_text())
                for profile in document.get('Profiles', []):
                    if isinstance(profile, dict) and isinstance(profile.get('Name'), str):
                        profiles[profile['Name']] = profile
            except (OSError, ValueError, AttributeError, TypeError):
                continue
    # External integration readiness is allowlisted; ownership remains in receipts.
    # Foreign env/MCP/auth values are never retained in Context or diagnostics.
    return Context(paths, executables, versions, frozenset(capabilities), profiles, status_installations(paths, app), preferences)


def _legacy_codex_status(paths):
    try:
        import tomllib
        config = tomllib.loads((paths.codex_home / 'config.toml').read_text())
        plugins = config.get('plugins', {})
        return any(key.split('@', 1)[0] in {'iterm2-status', 'codex-iterm2-status'} and
                   isinstance(value, dict) and value.get('enabled') is True
                   for key, value in plugins.items())
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def _shell_tokens(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ''
    return list(lexer)


def _shell_commands(command):
    """Split only unquoted shell operators; quoted operator arguments stay data."""
    segments, segment = [], []
    quote, escaped, comment, word_start = None, False, False, True
    for char in command:
        if comment:
            if char != '\n':
                continue
            comment = False
        if escaped:
            segment.append(char)
            escaped = False
            if char != '\n':
                word_start = False
        elif char == chr(92) and quote != "'":
            segment.append(char)
            escaped = True
        elif char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            segment.append(char)
            word_start = False
        elif quote is None and char == '#' and word_start:
            comment = True
        elif quote is None and char in ';&|()\n':
            segments.append(''.join(segment))
            segment = []
            word_start = True
        else:
            segment.append(char)
            word_start = quote is None and char.isspace()
    segments.append(''.join(segment))
    return segments


def _shell_substitutions(command):
    """Find executing substitutions before shlex discards quoting/escaping."""
    bodies = []

    def scan(start, terminator=None, depth=0):
        if depth > 16:
            raise ValueError('Shell substitution nesting limit')
        index, quote, parentheses, word_start = start, None, 0, True
        while index < len(command):
            char = command[index]
            if char == chr(92) and quote != "'":
                if command[index:index + 2] != chr(92) + '\n':
                    word_start = False
                index += 2
                continue
            if quote is None and char == '#' and word_start:
                # Backquotes are delimited before their body is parsed as shell
                # code: even a body comment cannot hide an unescaped closer.
                while index < len(command) and command[index] != '\n':
                    if terminator == '`':
                        if command[index] == '`':
                            return index
                        if command[index] == chr(92) and index + 1 < len(command):
                            index += 2
                            continue
                    index += 1
                continue
            if quote == "'":
                if char == "'":
                    quote = None
            elif char == "'" and quote is None:
                quote = "'"
            elif terminator == '`' and char == '`':
                return index
            elif command.startswith('$(', index) or char == '`':
                offset = 2 if char == '$' else 1
                end = scan(index + offset, ')' if char == '$' else '`', depth + 1)
                bodies.append(command[index + offset:end])
                index = end
            elif char == '"':
                quote = None if quote == '"' else '"'
            elif quote is None and char == '(':
                parentheses += 1
            elif quote is None and char == ')':
                if parentheses:
                    parentheses -= 1
                elif terminator == ')':
                    return index
            word_start = quote is None and (char.isspace() or char in ';&|()')
            index += 1
        if terminator:
            raise ValueError('Unterminated shell substitution')
        return index

    scan(0)
    return bodies


def _status_command_roles(command, depth=0):
    """Classify executable positions and explicit wrappers, never ordinary args."""
    if depth > 8:
        return set()
    roles = set()
    for body in _shell_substitutions(command):
        roles |= _status_command_roles(body, depth + 1)
    for segment in _shell_commands(command):
        words = _shell_tokens(segment)
        # Conditional keywords and assignments precede the executable position.
        while words and (words[0] in {'if', 'then', 'elif', 'else', 'while', 'until', 'do', '!'} or
                         re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', words[0], re.S)):
            words = words[1:]
        if not words:
            continue
        executable = Path(words[0]).name
        if executable == 'cc-status':
            roles.add('native')
        elif executable in {'iterm2-status', 'codex-iterm2-status'}:
            roles.add('legacy')
        elif executable in {'sh', 'bash', 'zsh', 'dash', 'ksh'}:
            for index, option in enumerate(words[1:], 1):
                if not re.fullmatch(r'-[A-Za-z]+', option):
                    break
                if 'c' in option and index + 1 < len(words):
                    roles |= _status_command_roles(words[index + 1], depth + 1)
                    break
        elif executable in {'command', 'exec', 'env', 'nohup'}:
            rest = words[1:]
            operands = ({'-u', '--unset', '-P', '-C', '--chdir'} if executable == 'env'
                        else {'-a'} if executable == 'exec' else set())
            while rest:
                if rest[0] == '--':
                    rest = rest[1:]
                    break
                if rest[0] in operands:
                    rest = rest[2:]
                elif rest[0].startswith('-') or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', rest[0], re.S):
                    rest = rest[1:]
                else:
                    break
            roles |= _status_command_roles(shlex.join(rest), depth + 1)
    return roles


def native_codex_hook_state(paths: Paths, app: Path) -> str:
    """Inspect external direct hooks; never execute hooks or read executable bodies."""
    from runtime.events import CODEX_EVENTS
    required = set(CODEX_EVENTS) - {'PreCompact', 'PostCompact'}
    try:
        document = json.loads((paths.codex_home / 'hooks.json').read_text())
    except FileNotFoundError:
        return 'absent'
    except (OSError, ValueError):
        return 'conflict'
    if not isinstance(document, dict) or not isinstance(document.get('hooks', {}), dict):
        return 'conflict'
    counts = dict.fromkeys(required, 0)
    found = conflict = legacy = False
    expected = app.resolve() / 'Contents/Resources/utilities/cc-status'
    for event, groups in document.get('hooks', {}).items():
        if not isinstance(groups, list):
            conflict = True
            continue
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get('hooks'), list):
                conflict = True
                continue
            for hook in group['hooks']:
                if not isinstance(hook, dict) or not isinstance(hook.get('command'), str):
                    continue
                command = hook['command']
                try:
                    roles = _status_command_roles(command)
                except ValueError:
                    conflict = True
                    continue
                legacy |= 'legacy' in roles
                if 'native' not in roles:
                    continue
                found = True
                try:
                    tokens = _shell_tokens(command)
                    executable = Path(tokens[0]) if tokens else Path('.')
                    matches = executable.is_absolute() and executable.resolve(strict=True) == expected
                    valid = (hook.get('type') == 'command' and matches and
                             tokens[1:] == ['--agent', 'codex'] and
                             group.get('matcher', '') in ('', '*') and
                             event in required and not hook.get('async', False))
                except (OSError, RuntimeError, ValueError):
                    valid = False
                if valid:
                    counts[event] += 1
                else:
                    conflict = True
    if not found:
        return 'conflict' if conflict else 'absent'
    if conflict or legacy or _legacy_codex_status(paths) or any(count != 1 for count in counts.values()):
        return 'conflict'
    return 'complete'


def status_installations(paths: Paths, app: Path | None = None) -> dict:
    """Return booleans only; never expose foreign hooks/env/settings bodies."""
    installed={}
    if _legacy_codex_status(paths):
        installed['codex-status']={'enabled':True}
    if app:
        native = native_codex_hook_state(paths, app)
        if native != 'absent':
            installed['codex-native-status'] = {'enabled': True} if native == 'complete' else {'conflict': True}
    try:
        document=json.loads(paths.claude_settings.read_text())
        expected={str(paths.home/'.config/iterm2/cc-status')}
        if app:expected.add(str(app/'Contents/Resources/utilities/cc-status'))
        for entries in document.get('hooks',{}).values():
            for entry in entries:
                for hook in entry.get('hooks',[]):
                    if hook.get('type')=='command':
                        tokens=shlex.split(hook.get('command',''))
                        if tokens and tokens[0] in expected:
                            installed['claude-status']={'enabled':True}
    except (OSError,ValueError,TypeError,AttributeError):
        pass
    return installed


def live_status(context: Context, runner: Runner, selection=None) -> list:
    """Bounded read-only explicit-session API probe; payload never serialized."""
    from .models import Finding
    from runtime.events import terminal_from_environment
    findings=[]
    if selection is None or not selection.agents_for('status'):
        return findings
    if 'iterm2:session-status' not in context.capabilities:
        findings.append(Finding('status',next(iter(selection.agents_for('status'))) if len(selection.agents_for('status')) == 1 else None,'status_capability','unavailable','iTerm2 session status capability is unavailable.'))
        return findings
    terminal=terminal_from_environment(os.environ)
    if os.environ.get('TMUX') or not terminal:
        message = ('Live status is unverified in TMUX; use an ordinary local iTerm2 panel.'
                   if os.environ.get('TMUX') else
                   'Live status requires an explicit valid UUID in TERM_SESSION_ID or ITERM_SESSION_ID; both sources must agree when present.')
        findings.append(Finding('status',None,'status_api','pending_ui',message))
        return findings
    ready=False
    if terminal and context.executables.get('it2'):
        try:
            result=runner.run([str(context.executables['it2']),'session','get-status','--session',terminal],timeout=2)
            value=json.loads(result.stdout)
            ready=(result.returncode==0 and isinstance(value,dict) and
                   isinstance(value.get('status'),str) and value['status'] in {'','idle','working','waiting','done','error'})
        except (OSError,ValueError,subprocess.SubprocessError):
            pass
    findings.append(Finding('status',None,'status_api','ready' if ready else 'pending_ui',
                            'Explicit-session API is reachable; hook delivery and error-event support remain unverified.' if ready else 'Enable Python API and authorize it2, then run doctor --live from an iTerm2 session.'))
    if 'claude' not in selection.agents_for('status'):
        return findings
    if context.installed.get('claude-status',{}).get('enabled'):
        findings.append(Finding('status','claude','native_status','ready','Native cc-status hook detected.'))
    else:
        findings.append(Finding('status','claude','native_status','pending_ui','Use iTerm2 > Install/Reinstall Claude Code Integration; select only API, hooks and Session Status.'))
    return findings


def native_status_findings(context: Context, selection) -> list:
    """Describe selected Codex status capabilities without executing a hook."""
    from .models import Finding
    if 'codex' not in selection.agents_for('status'):
        return []
    native = context.installed.get('codex-native-status', {})
    legacy = context.installed.get('codex-status', {}).get('enabled')
    reused = legacy and not native and not selection.adopt_legacy
    if native.get('conflict') or native.get('enabled') and legacy:
        backend, backend_state = 'Conflicting status writers; resolve native/legacy registrations.', 'conflict'
    elif reused:
        backend, backend_state = 'Codex backend: legacy reused; this is not cc-status. Use --adopt-legacy for explicit migration.', 'ready'
    elif native.get('enabled'):
        backend, backend_state = 'Codex backend: external native cc-status reused without ownership; adapter-only input/compact behavior is unavailable.', 'ready'
    else:
        backend, backend_state = 'Codex backend: cc-status via package adapter; installed files do not establish loaded hooks or event delivery.', 'ready'
    findings = [Finding('status','codex','status_backend',backend_state,backend)]
    if not reused:
        capable = 'iterm2:cc-status-codex' in context.capabilities
        findings.append(Finding('status','codex','native_status_capability','ready' if capable else 'unavailable',
            'Compatible iTerm2 3.7.6+ bundle and executable cc-status/it2 pair with required flags detected; live delivery is unverified.' if capable else
            'Codex native status requires iTerm2 3.7.6+ and an executable cc-status/it2 pair from the selected compatible bundle.'))
    version = context.versions.get('codex','unknown')
    message = ('Codex 0.163.0: StopFailure is absent from the verified hook schema; API failures cannot reliably produce native error.'
               if version == '0.163.0' else
               f'Codex {version}: StopFailure error-event source is unverified; automatic native error is not supported by this adapter.')
    findings.append(Finding('status','codex','codex_error_event','limited',message))
    return findings
