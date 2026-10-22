"""Inspection only: no shell startup files are executed and no GUI is launched."""
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
from pathlib import Path

from .commands import Runner
from .models import Context, Paths


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
    for name in sorted(agents | {'zsh', 'python3', 'terminal-notifier', 'peekaboo', 'fzf'}):
        found = shutil.which(name)
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


def status_installations(paths: Paths, app: Path | None = None) -> dict:
    """Return booleans only; never expose foreign hooks/env/settings bodies."""
    import shlex
    installed={}
    try:
        import tomllib
        config=tomllib.loads((paths.codex_home/'config.toml').read_text())
        plugins=config.get('plugins',{})
        # Official plugin key is package@marketplace; exact known package name.
        enabled=any(key.split('@',1)[0] in {'iterm2-status','codex-iterm2-status'} and
                    isinstance(value,dict) and value.get('enabled') is True
                    for key,value in plugins.items())
        if enabled:installed['codex-status']={'enabled':True}
    except (OSError,ValueError,TypeError,AttributeError):
        pass
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


def live_status(context: Context, runner: Runner) -> list:
    """Bounded read-only explicit-session API probe; payload never serialized."""
    from .models import Finding
    from runtime.events import terminal_id
    findings=[]
    if 'iterm2:session-status' not in context.capabilities:
        findings.append(Finding('status','codex','status_capability','unavailable','iTerm2 session status capability is unavailable.'))
        return findings
    terminal=terminal_id(os.environ.get('ITERM_SESSION_ID',''))
    ready=False
    if terminal and context.executables.get('it2'):
        try:
            result=runner.run([str(context.executables['it2']),'session','get-status','--session',terminal],timeout=2)
            value=json.loads(result.stdout)
            ready=result.returncode==0 and isinstance(value,dict) and value.get('status') in {'','idle','working','waiting'}
        except (OSError,ValueError,subprocess.SubprocessError):
            pass
    findings.append(Finding('status',None,'status_api','ready' if ready else 'pending_ui',
                            'Explicit-session API is reachable.' if ready else 'Enable Python API and authorize it2, then run doctor --live from an iTerm2 session.'))
    if context.installed.get('claude-status',{}).get('enabled'):
        findings.append(Finding('status','claude','native_status','ready','Native cc-status hook detected.'))
    else:
        findings.append(Finding('status','claude','native_status','pending_ui','Use iTerm2 > Install/Reinstall Claude Code Integration; select only API, hooks and Session Status.'))
    return findings
