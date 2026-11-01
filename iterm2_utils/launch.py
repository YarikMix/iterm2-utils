"""Launch one explicitly addressed tab; never retry a terminal mutation."""
import asyncio
import json
import shlex
import subprocess
import time
from dataclasses import asdict

from runtime.codex_restore.codexlib.iterm import ITerm
from runtime.codex_restore.codexlib.registry import normalize_terminal
from runtime.codex_restore.codexlib.transcripts import normalize_uuid

from .commands import Runner
from .launch_api import create_tab
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
    if request.resume_session_id is not None:
        return ['resume', normalize_uuid(request.resume_session_id), '-C', str(request.cwd)]
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
    try:
        resume_id = normalize_uuid(request.resume_session_id) if request.resume_session_id is not None else None
    except ValueError:
        resume_id = None
    output = dict(mode='launch_codex', status='blocked', window_id=None, tab_id=None,
                  session_id=None, profile=request.profile, findings=[asdict(f) for f in findings],
                  launch_mode=request.launch_mode, resume_session_id=resume_id)
    if inspection is None:
        return 2, output
    creation = asyncio.run(create_tab(request.window_id, request.profile, inspection.profile_guid,
                                      build_command(request, inspection, paths)))
    output.update(window_id=creation.window_id, tab_id=creation.tab_id, session_id=creation.session_id)
    if creation.status == 'blocked':
        output['findings'].extend(asdict(f) for f in creation.findings)
        return 2, output
    transport = LaunchITerm(str(inspection.it2), timeout=3)
    transport.executable = str(inspection.it2)  # Launch must ignore restore-only executable overrides.
    transport.deadline = creation.deadline
    try:
        if output['session_id'] is not None:
            output['session_id'] = normalize_terminal(output['session_id'])
        terminal = output['session_id']
    except ValueError:
        terminal = None
    # Only complete SDK identities authorize observation; inventories never supply missing IDs.
    if (creation.window_id == request.window_id and creation.tab_id and terminal and
            transport.deadline is not None):
        while time.monotonic() < transport.deadline:
            try:
                panes = transport.panes()
                matches = [p for p in panes if p.window_id == creation.window_id and
                           p.tab_id == creation.tab_id and p.terminal == terminal]
                if len(matches) == 1 and sum(p.tab_id == creation.tab_id for p in panes) == 1:
                    profile = transport.profile(request.profile)
                    applied = transport.variable(terminal, 'session.profileName')
                    job = transport.variable(terminal, 'session.jobName')
                    title = transport.variable(terminal, 'session.processTitle')
                    command_line = transport.variable(terminal, 'session.commandLine')
                    # iTerm observations may contain either literal joins or shell-quoted argv.
                    commands = [[title, *prefix, *_codex_arguments(request)]
                                for prefix in ([], ['--no-daemon'], ['--no-daemon', '--no-daemon'])]
                    matches_command = (command_line in (' '.join(args) for args in commands) or
                                       shlex.split(command_line) in commands)
                    if (title and matches_command and profile.get('guid') == inspection.profile_guid and
                            profile.get('name') == request.profile and applied == request.profile and job == 'codex' and
                            time.monotonic() < transport.deadline):
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
