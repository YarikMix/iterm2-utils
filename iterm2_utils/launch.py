"""Launch one explicitly addressed tab; never retry a terminal mutation."""
import json
import shlex
import subprocess
import time
from dataclasses import asdict

from runtime.codex_restore.codexlib.iterm import ITerm, UnknownTabOutcome
from runtime.codex_restore.codexlib.registry import normalize_terminal

from .commands import Runner
from .launch_checks import LaunchInspection, LaunchRequest, identity_guard, inspect_launch
from .models import Finding, Paths


class LaunchITerm(ITerm):
    def profile(self, name: str) -> dict:
        value = json.loads(self._run([self.executable, 'profile', 'show', name, '--json']))
        if not isinstance(value, dict):
            raise ValueError('invalid profile observation')
        return value

    def variable(self, terminal: str, name: str) -> str:
        value = json.loads(self._run([self.executable, 'session', 'get-var', name,
                                     '--session', normalize_terminal(terminal).upper()]))
        if not isinstance(value, str):
            raise ValueError('invalid session variable')
        return value


def _codex_arguments(request: LaunchRequest) -> list[str]:
    prompt = 'Read the handoff file at '+str(request.handoff)+' and carry out the task described there.'
    return ['-C', str(request.cwd), prompt]


def build_command(request: LaunchRequest, inspection: LaunchInspection, paths: Paths) -> str:
    script = (identity_guard(paths, inspection.identity)+' && '+
              shlex.join(['codex', *_codex_arguments(request)])+'\n'+
              # Keep the tab available even when its profile closes exited commands.
              shlex.join(['exec', str(inspection.zsh), '-i']))
    wrapper = ('export CODEX_RESTORE_NO_AUTO=1; cd -- '+shlex.quote(str(request.cwd))+' && '+
               shlex.join(['exec', str(inspection.zsh), '-ilc', script])+'; '+
               shlex.join(['exec', str(inspection.zsh), '-i']))
    return shlex.join(['/bin/sh', '-c', wrapper])


def launch(request: LaunchRequest, paths: Paths, runner: Runner) -> tuple[int, dict]:
    inspection, findings = inspect_launch(paths, request, runner)
    output = dict(mode='launch_codex', status='blocked', window_id=None, tab_id=None,
                  session_id=None, profile=request.profile, findings=[asdict(f) for f in findings])
    if inspection is None:
        return 2, output
    transport = LaunchITerm(str(inspection.it2), timeout=3)
    transport.executable = str(inspection.it2)  # Launch must ignore restore-only executable overrides.
    transport.deadline = time.monotonic()+15
    output['window_id'] = request.window_id
    key = None
    terminal = None
    try:
        terminal = transport.new_tab(request.window_id, profile=request.profile,
                                     command=build_command(request, inspection, paths))
        output['session_id'] = terminal
    except UnknownTabOutcome as error:
        key = error.tab_id
    # No key means creation may have happened, but guessing from other tabs is unsafe.
    if terminal is not None or key is not None:
        while time.monotonic() < transport.deadline:
            try:
                tabs = transport._list('tab')
                matches = [t for t in tabs if t.get('id') == key and t.get('window_id') == request.window_id]
                if len(matches) == 1 and isinstance(key, str) and key:
                    output['tab_id'] = key
                panes = transport.panes()
                matches = [p for p in panes if p.window_id == request.window_id and
                           (p.terminal == terminal if terminal is not None else
                            p.tab_id == key or p.terminal.lower() == str(key).lower())]
                if len(matches) == 1:
                    pane = matches[0]
                    if sum(p.tab_id == pane.tab_id for p in panes) != 1:
                        raise ValueError('created tab has multiple sessions')
                    output.update(tab_id=pane.tab_id, session_id=pane.terminal)
                    profile = transport.profile(request.profile)
                    applied = transport.variable(pane.terminal, 'session.profileName')
                    job = transport.variable(pane.terminal, 'session.jobName')
                    title = transport.variable(pane.terminal, 'session.processTitle')
                    command_line = transport.variable(pane.terminal, 'session.commandLine')
                    # iTerm joins argv without escaping; restore + simple wrapper can each add --no-daemon.
                    commands = [' '.join([title, *prefix, *_codex_arguments(request)])
                                for prefix in ([], ['--no-daemon'], ['--no-daemon', '--no-daemon'])]
                    if (title and command_line in commands and profile.get('guid') == inspection.profile_guid and
                            profile.get('name') == request.profile and applied == request.profile and job == 'codex'):
                        output['status'] = 'launched'
                        return 0, output
            except (OSError, ValueError, TypeError, KeyError, AttributeError, TimeoutError, subprocess.SubprocessError):
                # External exceptions carry private stderr; only fixed findings leave this boundary.
                pass
            remaining = transport.deadline-time.monotonic()
            if remaining > 0:
                time.sleep(min(.2, remaining))
    output['status'] = 'created_unverified' if output['tab_id'] or output['session_id'] else 'unknown'
    output['findings'].append(asdict(Finding('launch', 'codex', 'launch_'+output['status'], 'unavailable',
        'Launch observations are incomplete. Inspect the known tab before taking further action.')))
    return 3, output
