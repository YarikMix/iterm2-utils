"""Bounded metadata-only bridge to the bundled source registry."""
import os
from pathlib import Path
import time
from .codexlib import registry, snapshots, store
from .codexlib.iterm import ITerm


def handle(event, settings, runner, metadata=None):
    if not metadata or event.name not in {'SessionStart','UserPromptSubmit','Stop'}:
        return
    home=Path(os.environ.get('CODEX_HOME',settings['restore_codex_home']))
    paths=store.paths(home,Path(os.environ.get('CODEX_RESTORE_CACHE_DIR',settings['restore_cache'])))
    client=ITerm(settings['it2'])
    client.process=settings['restore_process']
    # Preserve the dispatcher's OS-level deadline. Source registry lock waits and
    # subprocess calls remain bounded, and BaseException escapes to hook.main.
    client.deadline=time.monotonic()+2.0
    now=time.time()
    if registry.accept_event(paths,os.environ.get('CODEX_RESTORE_TOKEN',''),event.terminal_uuid,metadata,client.identity,now):
        snapshots.capture(paths,client,now,required_terminal=event.terminal_uuid,required_token=os.environ.get('CODEX_RESTORE_TOKEN',''))
