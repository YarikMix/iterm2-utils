"""Read-only prerequisite gate for the locally bundled Codex restorer."""
import re
from ..models import ChangeSet, Context, Selection, Finding


def build(context: Context, selection: Selection) -> ChangeSet:
    changes=ChangeSet([],[],[])
    if 'restore' not in selection.features:
        return changes
    def issue(code,state,message):
        changes.findings.append(Finding('restore','codex',code,state,message))
    if 'codex' not in selection.agents:
        issue('codex_only','unavailable','Session restoration is available only for Codex.')
        return changes
    version=context.versions.get('fzf','')
    match=re.match(r'^(\d+)\.(\d+)(?:\.(\d+))?',version)
    if 'fzf' not in context.executables or not match or tuple(map(int,match.groups(default='0'))) < (0,60,0):
        issue('fzf','missing_dependency','Session restoration requires fzf 0.60 or newer.')
    if 'codex:no-daemon' not in context.capabilities:
        issue('no_daemon','unavailable','Session restoration requires Codex --no-daemon.')
    if 'it2' not in context.executables:
        issue('it2','missing_dependency','Session restoration requires the selected iTerm2 it2 utility.')
    return changes
