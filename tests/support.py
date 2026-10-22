import os
import plistlib
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.responses = {'python3':'Python 3.11.9'}

    def run(self, argv, *, timeout, stdin=None, env=None):
        self.calls.append((argv, timeout, stdin))
        name = Path(argv[0]).name
        return subprocess.CompletedProcess(argv, 0, self.responses.get(name, '1.0 --no-daemon session-status python-api'), '')


class Fixture:
    """Synthetic macOS environment, with explicit overrides for platform negatives."""

    def __init__(self, *, platform='Darwin'):
        self.platform = platform

    def __enter__(self):
        self.tmp = TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        for name in ('codex', 'claude', 'zsh', 'python3', 'terminal-notifier', 'peekaboo', 'osascript'):
            file = self.bin / name
            file.write_text('#!/bin/sh\nexit 0\n')
            file.chmod(0o755)
        self.app = self.home / 'Applications/iTerm.app'
        (self.app / 'Contents/Resources').mkdir(parents=True)
        (self.app / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'com.googlecode.iterm2', 'CFBundleShortVersionString': '3.7.6', 'CFBundleExecutable': 'iTerm2'}))
        (self.app / 'Contents/MacOS').mkdir()
        binary = self.app / 'Contents/MacOS/iTerm2'
        binary.write_text('#!/bin/sh\n')
        binary.chmod(0o755)
        it2 = self.app / 'Contents/Resources/it2'
        it2.write_text('#!/bin/sh\n')
        it2.chmod(0o755)
        self.env = patch.dict(os.environ, {'HOME': str(self.home), 'PATH': str(self.bin), 'ITERM2_APP': str(self.app), 'SHELL': str(self.bin / 'zsh')}, clear=True)
        self.env.start()
        self.system = patch('iterm2_utils.discovery.platform.system', return_value=self.platform)
        self.system.start()
        self.runner = FakeRunner()
        return self

    def snapshot(self):
        return {str(p.relative_to(self.home)): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}

    def __exit__(self, *args):
        self.system.stop()
        self.env.stop()
        self.tmp.cleanup()
