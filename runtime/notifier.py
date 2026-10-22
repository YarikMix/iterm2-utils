"""Deduplicated observational notices; cache contains only bounded state/IDs."""
from dataclasses import dataclass
from pathlib import Path
import json
import shlex
import subprocess
import sys
import time
try:
    from vendor.codex_status import status
except ImportError:
    from .vendor.codex_status import status
try:
    import claude_notifications
except ImportError:
    from . import claude_notifications

@dataclass(frozen=True)
class Notice:
    agent:str
    terminal_uuid:str
    session_id:str
    token:str
    kind:str

# UUID is an argv item, never inserted into the AppleScript source. Frontmost
# refers to iTerm itself; split panes in the selected tab all count as visible.
CONTEXT_SCRIPT='''on run argv
    set targetID to item 1 of argv
    tell application id "com.googlecode.iterm2"
        set visibleIDs to {}
        if frontmost then
            try
                repeat with s in sessions of current tab of current window
                    set end of visibleIDs to unique ID of s
                end repeat
            on error
                return "unknown"
            end try
        end if
        repeat with w in windows
            repeat with t in tabs of w
                repeat with s in sessions of t
                    if unique ID of s is targetID then return ((targetID is in visibleIDs) as string)
                end repeat
            end repeat
        end repeat
    end tell
    return "unknown"
end run'''

def transition(previous,event):
    if event.agent=='claude':
        state,kind=claude_notifications.transition(previous,event)
    else:
        raw={'hook_event_name':event.name,'session_id':event.session_id,'turn_id':event.turn_key,'tool_name':event.tool_name,'tool_key':event.tool_key,'source':event.source,'agent_id':event.agent_id}
        state=status.transition(previous,raw)
        if state is None:
            return previous,None
        # Upstream pending-work semantics: a main Stop can precede subagent idle.
        reset=(previous.get('session_id')!=event.session_id or event.name in {'UserPromptSubmit','Interrupt','SessionEnd'} or event.name=='SessionStart' and event.source!='compact')
        if reset:
            state.pop('claimed',None);state.pop('completion_pending',None)
        if event.name=='Stop' and previous.get('working'):
            state['completion_pending']=True
        kind=None
        if event.name=='PreToolUse' and event.tool_name in status.INPUT_TOOLS:
            kind='input'
        elif state['status']=='idle' and state.get('completion_pending'):
            kind='complete';state.pop('completion_pending',None)
        if kind and state.get('claimed')==kind:
            kind=None
        elif kind:
            state['claimed']=kind
        elif state['status']=='working':
            state.pop('claimed',None)
        # Cache no project/detail strings: these are upstream presentation fields.
        state.pop('project',None);state.pop('detail',None)
    if not kind:
        return state,None
    token=str(time.time_ns())
    state['token']=token
    return state,Notice(event.agent,event.terminal_uuid,event.session_id,token,kind)

def _settings(context):
    if isinstance(context,dict):
        return context
    return {**{k:str(v) for k,v in context.executables.items()},'terminal_notifier':str(context.executables.get('terminal-notifier',''))}

def deliver(notice,context,runner):
    settings=_settings(context)
    paths=[settings.get(k,'') for k in ('terminal_notifier','it2','osascript')]
    if status.terminal_id(notice.terminal_uuid)!=notice.terminal_uuid or not all(Path(p).is_absolute() for p in paths):
        return False
    try:
        result=runner.run([paths[2],'-e',CONTEXT_SCRIPT,notice.terminal_uuid],timeout=0.5)
        if result.returncode or result.stdout.strip()!='false':
            return False
        action=shlex.join([sys.executable,'-B',str(Path(__file__).with_name('focus.py').absolute()),notice.terminal_uuid,paths[1]])
        argv=[paths[0],'-title',notice.agent.capitalize(),'-message',{'input':'Нужен ответ','complete':'Ответ готов','attention':'Нужно внимание'}[notice.kind],'-group',notice.agent+'-'+notice.terminal_uuid,'-execute',action]
        runner.run([sys.executable,'-B',str(Path(__file__).absolute()),'--post',*argv],timeout=0.5)
        return True
    except Exception:
        return False

def handle(event,settings,runner):
    cache=Path(settings.get('notification_cache',''))
    if not cache.is_absolute():
        return
    cache.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=cache/(event.agent+'-'+event.terminal_uuid+'.json')
    with status.locked(path.with_suffix('.lock'),0.1):
        previous=status.read_state(path)
        state,notice=transition(previous,event)
        # Claim before handing off delivery: repeated hooks never resend.
        status.write_state(path,state)
    if notice:
        deliver(notice,settings,runner)

if __name__=='__main__' and len(sys.argv)>2 and sys.argv[1]=='--post':
    # Bounded asynchronous helper. Delivery never holds the hook for app startup.
    try:
        subprocess.Popen([sys.executable,'-B',str(Path(__file__).absolute()),'--worker',*sys.argv[2:]],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True,start_new_session=True)
    except OSError:
        pass
elif __name__=='__main__' and len(sys.argv)>2 and sys.argv[1]=='--worker':
    try:
        subprocess.run(sys.argv[2:],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=9,check=False)
    except (OSError,subprocess.SubprocessError):
        pass
