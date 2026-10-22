"""Explicit-session it2 command construction; adapted from iterm2-status (MIT)."""
from .status import COLORS, terminal_id

def status_command(it2, terminal, state):
    terminal = terminal_id(terminal)
    if not terminal:
        return None
    color = COLORS[state['status']]
    return [str(it2), 'session', 'set-status', '--session', terminal,
            '--status', state['status'], '--dot-color', color,
            '--text-color', color, '--detail', state['detail'],
            '--background-tasks', str(len(state['agents']))]
