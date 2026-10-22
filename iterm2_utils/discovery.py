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
    for name in sorted(agents | {'zsh', 'python3', 'terminal-notifier', 'peekaboo'}):
        found = shutil.which(name)
        if not found:
            continue
        binary = Path(found).absolute()
        output = _probe(runner, binary, ['--version'])
        if not output:
            continue
        executables[name] = binary
        versions[name] = _version(output)
        if name == 'codex' and '--no-daemon' in _probe(runner, binary, ['--help']):
            capabilities.add('codex:no-daemon')
    app, info = _iterm(paths)
    if app:
        executables['iterm2'] = app
        versions['iterm2'] = _version(str(info.get('CFBundleShortVersionString', '')))
        it2 = app / 'Contents/Resources/it2'
        if it2.is_file() and os.access(it2, os.X_OK):
            output = _probe(runner, it2, ['--help'])
            if 'session-status' in output:
                capabilities.add('iterm2:session-status')
            if output:
                executables['it2'] = it2
    profiles = {}
    if paths.profiles.is_dir():
        for path in sorted(paths.profiles.glob('*.json')):
            try:
                document = json.loads(path.read_text())
                for profile in document.get('Profiles', []):
                    if isinstance(profile, dict) and isinstance(profile.get('Name'), str):
                        profiles[profile['Name']] = profile
            except (OSError, ValueError, AttributeError, TypeError):
                continue
    # Existing installation ownership is established by later receipt handling.
    # Agent configs (especially third-party MCP env/auth blocks) are not read.
    return Context(paths, executables, versions, frozenset(capabilities), profiles, {})
