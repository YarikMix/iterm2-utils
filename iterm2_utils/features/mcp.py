"""Pure opt-in MCP registration builder."""
from ..config.mcp import NAME, definition
from ..models import ChangeSet, RegistrationEdit, Finding, UiStep


def build(context, selection):
    changes=ChangeSet([],[],[])
    if 'mcp' not in selection.features:return changes
    for agent in sorted(selection.agents):
        changes.edits.append(RegistrationEdit(agent,NAME,None,definition(),'mcp'))
        changes.ui.append(UiStep('mcp_authorize','mcp',agent,
            'Enable iTerm2 Python API and authorize the pinned server, then restart the agent and run a live probe.'))
        if 'uvx' not in context.executables:
            changes.findings.append(Finding('mcp',agent,'uvx_missing','missing_dependency',
                'Install uvx separately. The pinned MCP server requires Python >=3.12; setup Python >=3.11 is insufficient.'))
    return changes
