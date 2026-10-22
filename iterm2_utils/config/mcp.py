"""Pinned optional MCP registration. Foreign configuration never leaves inspection."""
import json
import os
from pathlib import Path
import subprocess
import shlex
from ..models import Finding

NAME = 'iterm2-observe'
ARGS = ['--with', 'mcp<2', 'mcp-server-iterm2==0.1.1']
TOOLS = frozenset({'list_sessions','get_session_info','get_screen_contents','get_selection',
    'get_scrollback','get_recent_output','get_variable','list_profiles','set_badge',
    'set_title','set_tab_color','set_user_variable','post_notification'})


def definition():
    return {'command':'uvx','args':list(ARGS),'scope':'user','enabled':True,'environment_empty':True}


def _run(context, runner, agent, args):
    if agent not in {'codex','claude'} or agent not in context.executables:
        raise ValueError('MCP agent unavailable')
    env=os.environ.copy()
    env['HOME']=str(context.paths.home)
    if agent == 'codex':env['CODEX_HOME']=str(context.paths.codex_home)
    elif env.get('CLAUDE_CONFIG_DIR') and Path(env['CLAUDE_CONFIG_DIR']).expanduser() != context.paths.claude_settings.parent:
        raise ValueError('CLAUDE_CONFIG_DIR differs from selected Claude scope')
    return runner.run([str(context.executables[agent]),'mcp',*args],timeout=5,env=env)


def inspect(agent, name, context, runner):
    if name != NAME:raise ValueError('Unsupported MCP name')
    capability=_run(context,runner,agent,['get','--help'])
    if capability.returncode or (agent == 'codex' and '--json' not in capability.stdout):
        raise ValueError('MCP inspection capability unavailable')
    args=['get',name] + (['--json'] if agent == 'codex' else [])
    result=_run(context,runner,agent,args)
    if result.returncode:
        absent = {f"No MCP server named '{name}' found.", f"No MCP server found with name: {name}"}
        if result.returncode == 1 and (result.stderr.strip() in absent or result.stdout.strip() in absent):
            return None
        raise ValueError('MCP registration inspection failed')
    if agent == 'claude':
        return _claude(result.stdout,name)
    try:
        value=json.loads(result.stdout)
        if value is None:return None
        transport=value.get('transport',{})
        exact=(value.get('enabled') is True and transport.get('type')=='stdio' and
            transport.get('command')=='uvx' and transport.get('args')==ARGS and
            not transport.get('env') and not transport.get('env_vars') and
            not transport.get('cwd') and not value.get('disabled_reason') and
            not value.get('enabled_tools') and not value.get('disabled_tools'))
        return definition() if exact else {'conflict':True}
    except (ValueError,TypeError,AttributeError):
        raise ValueError('MCP registration format unavailable') from None



def _claude(output, name):
    # Human CLI output is version-sensitive: reject unknown formats rather than
    # guess scope or silently ignore environment overrides.
    fields={}
    for line in output.splitlines():
        line=line.strip()
        if not line or line == name+':' or line.startswith('To remove this server, run:'):
            continue
        key, separator, value=line.partition(':')
        if not separator or key not in {'Scope','Status','Type','Command','Args','Environment'} or key in fields:
            return {'conflict':True}
        fields[key]=value.strip()
    try:
        exact=(fields.get('Scope') == 'User config (available in all your projects)' and
            fields.get('Status') in {'✓ Connected','✗ Failed to connect'} and
            fields.get('Type') == 'stdio' and fields.get('Command') == 'uvx' and
            shlex.split(fields.get('Args','')) == ARGS and
            not fields.get('Environment'))
    except ValueError:
        exact=False
    return definition() if exact else {'conflict':True}

def apply(edit, context, runner):
    if edit.after is not None and edit.after != definition():
        raise ValueError('Unsupported MCP definition')
    current=inspect(edit.agent,edit.name,context,runner)
    if current == edit.after:return
    if current != edit.before or (current is not None and current != definition()):
        raise ValueError('MCP registration conflict')
    action='add' if edit.after is not None else 'remove'
    help_result=_run(context,runner,edit.agent,[action,'--help'])
    if help_result.returncode:raise ValueError('MCP CLI capability unavailable')
    if edit.agent == 'claude' and not all(flag in help_result.stdout for flag in ('--scope', '--transport') if action == 'add'):
        raise ValueError('MCP CLI capability unavailable')
    argv=([action,edit.name,'--','uvx',*ARGS] if edit.after is not None else [action,edit.name])
    if edit.agent == 'claude':
        argv=([action,'--transport','stdio','--scope','user',edit.name,'--','uvx',*ARGS] if edit.after is not None else [action,'--scope','user',edit.name])
    try:
        result=_run(context,runner,edit.agent,argv)
        if result.returncode:raise ValueError('MCP registration mutation failed')
    except subprocess.TimeoutExpired:
        # Unknown mutation outcome: inspect once, never repeat add/remove.
        if inspect(edit.agent,edit.name,context,runner) != edit.after:
            raise ValueError('MCP mutation outcome unknown') from None
        return
    if inspect(edit.agent,edit.name,context,runner) != edit.after:
        raise ValueError('MCP mutation could not be verified')


def probe(context, runner, agent):
    ready=False
    try:
        if inspect(agent,NAME,context,runner) != definition():
            raise ValueError('Pinned registration unavailable')
        env=os.environ.copy()
        env['HOME']=str(context.paths.home)
        value=runner.mcp_probe([str(context.executables['uvx']),*ARGS],timeout=10,env=env)
        tools=value['tools']
        ready=(bool(tools) and set(tools)<=TOOLS and 'list_sessions' in tools and value['sessions'] is True)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,subprocess.SubprocessError):
        pass
    return Finding('mcp',agent,'mcp_connection','ready' if ready else 'unavailable',
        'Pinned MCP connection and tool policy verified.' if ready else
        'Pinned MCP connection or tool policy could not be verified; authorize the iTerm2 Python API and retry.')
