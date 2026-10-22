"""Installed observational dispatcher. Success and every failure emit only {}."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

class Runner:
    def run(self,argv,*,timeout,stdin=None):
        return subprocess.run(argv,input=stdin,text=True,capture_output=True,timeout=timeout,check=False)


def dispatch(event, settings: dict, runner: Runner) -> None:
    from vendor.codex_status import status
    from vendor.codex_status.iterm_support import status_command
    if not status.terminal_id(event.terminal_uuid):
        return
    # Independent, optional handlers are registered by their feature modules.
    if settings.get('notifications'):
        try:
            from notifications import handle
            handle(event,settings,runner)
        except Exception:
            pass
    if settings.get('restore') and event.agent == 'codex':
        try:
            from codex_restore.registry import handle
            handle(event,settings,runner)
        except Exception:
            pass
    if not settings.get('status') or event.agent != 'codex' or not settings.get('it2') or not settings.get('cache'):
        return
    data=Path(settings['cache'])
    if not data.is_absolute():
        return
    data.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=data/(event.terminal_uuid+'.json')
    # Only bounded identifiers/state cross this adapter. No prompt, cwd, arguments,
    # tool output, transcript path reaches the cache. Opaque upstream-compatible tool identities are retained.
    raw={'hook_event_name':event.name,'session_id':event.session_id,
         'turn_id':event.turn_key,'tool_name':event.tool_name,'source':event.source,
         'agent_id':event.agent_id,'tool_key':event.tool_key}
    with status.locked(data/(event.terminal_uuid+'.lock'),0.15):
        previous=status.read_state(path)
        state=status.transition(previous,raw)
        if state is None:
            return
        state.update(revision=previous.get('revision',0)+1,reported=False)
        status.write_state(path,state)
    deadline=time.monotonic()+1.5
    with status.locked(data/(event.terminal_uuid+'.report.lock'),0.2):
        while time.monotonic()<deadline:
            with status.locked(data/(event.terminal_uuid+'.lock'),0.1):
                current=status.read_state(path)
                if current.get('reported'):
                    return
            result=runner.run(status_command(settings['it2'],event.terminal_uuid,current),
                              timeout=min(0.6,max(0.05,deadline-time.monotonic())))
            with status.locked(data/(event.terminal_uuid+'.lock'),0.1):
                latest=status.read_state(path)
                if latest.get('revision')==current.get('revision'):
                    latest['reported']=result.returncode==0
                    status.write_state(path,latest)
                    return


def main(argv: list[str]) -> int:
    # OS-level budget also bounds slow stdin/settings reads and lock contention.
    def expired(*_):
        raise TimeoutError('hook budget')
    old=None
    try:
        old=signal.signal(signal.SIGALRM,expired)
        signal.setitimer(signal.ITIMER_REAL,2.7)
        args=dict(zip(argv[::2],argv[1::2]))
        try:
            from events import normalize
        except ImportError:
            from .events import normalize
        settings_path=Path(args['--settings'])
        settings=json.loads(settings_path.read_text())
        raw=json.loads(sys.stdin.read(2*1024*1024))
        event=normalize(raw,args.get('--agent','codex'),os.environ.get('ITERM_SESSION_ID'))
        if event:
            dispatch(event,settings,Runner())
    except Exception:
        pass
    finally:
        if old is not None:
            signal.setitimer(signal.ITIMER_REAL,0)
            signal.signal(signal.SIGALRM,old)
    print('{}')
    return 0

if __name__=='__main__':
    sys.exit(main(sys.argv[1:]))
