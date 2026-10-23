#!/usr/bin/env python3
"""Validate only explicitly shipped files; never print offending content."""
import hashlib
import json
from pathlib import Path
import re
import sys

# Deliberately explicit: unknown files are never added by glob, gitignore or git.
EXPORT_FILES = (
    'CHANGELOG.md',
    'LICENSE',
    'README.md',
    'THIRD_PARTY_NOTICES.md',
    'docs/compatibility.md',
    'docs/native-status-events.md',
    'docs/notification-events.md',
    'iterm2_utils/__init__.py',
    'iterm2_utils/__main__.py',
    'iterm2_utils/cli.py',
    'iterm2_utils/commands.py',
    'iterm2_utils/config/__init__.py',
    'iterm2_utils/config/jsonfile.py',
    'iterm2_utils/config/mcp.py',
    'iterm2_utils/config/preferences.py',
    'iterm2_utils/config/tomlfile.py',
    'iterm2_utils/config/zshrc.py',
    'iterm2_utils/discovery.py',
    'iterm2_utils/engine.py',
    'iterm2_utils/features/__init__.py',
    'iterm2_utils/features/mcp.py',
    'iterm2_utils/features/notifications.py',
    'iterm2_utils/features/profiles.py',
    'iterm2_utils/features/restore.py',
    'iterm2_utils/features/shell.py',
    'iterm2_utils/features/status.py',
    'iterm2_utils/lifecycle.py',
    'iterm2_utils/migration.py',
    'iterm2_utils/models.py',
    'iterm2_utils/planner.py',
    'iterm2_utils/skill_install.py',
    'iterm2_utils/state.py',
    'runtime/claude_notifications.py',
    'runtime/codex.zsh',
    'runtime/codex_restore/codex-resume.zsh',
    'runtime/codex_restore/codex-sessions',
    'runtime/codex_restore/codexlib/__init__.py',
    'runtime/codex_restore/codexlib/cli.py',
    'runtime/codex_restore/codexlib/iterm.py',
    'runtime/codex_restore/codexlib/models.py',
    'runtime/codex_restore/codexlib/registry.py',
    'runtime/codex_restore/codexlib/restore.py',
    'runtime/codex_restore/codexlib/snapshots.py',
    'runtime/codex_restore/codexlib/store.py',
    'runtime/codex_restore/codexlib/transcripts.py',
    'runtime/codex_restore/registry.py',
    'runtime/events.py',
    'runtime/focus.py',
    'runtime/hook.py',
    'runtime/native_status.py',
    'runtime/notifier.py',
    'skills/iterm2-setup/SKILL.md',
    'skills/iterm2-setup/references/features.md',
    'skills/iterm2-setup/references/troubleshooting.md',
    'skills/iterm2-setup/references/ui.md',
    'sources.lock.json',
    'tests/__init__.py',
    'tests/fixtures/beta1-status.json',
    'tests/restore/__init__.py',
    'tests/restore/helpers.py',
    'tests/restore/test_cli.py',
    'tests/restore/test_codex.zsh',
    'tests/restore/test_registry.py',
    'tests/restore/test_restore.py',
    'tests/restore/test_snapshots.py',
    'tests/support.py',
    'tests/test_agent_workflow.py',
    'tests/test_claude_notifications.py',
    'tests/test_cli.py',
    'tests/test_codex_shell.zsh',
    'tests/test_config.py',
    'tests/test_discovery.py',
    'tests/test_engine.py',
    'tests/test_export.py',
    'tests/test_final_fixes.py',
    'tests/test_lifecycle.py',
    'tests/test_mcp.py',
    'tests/test_migration.py',
    'tests/test_native_status.py',
    'tests/test_native_status_migration.py',
    'tests/test_notifications_feature.py',
    'tests/test_notifier.py',
    'tests/test_payload.py',
    'tests/test_pending_ui.py',
    'tests/test_profiles.py',
    'tests/test_restore_feature.py',
    'tests/test_runtime_events.py',
    'tests/test_selection.py',
    'tests/test_shell.py',
    'tests/test_skill_install.py',
    'tests/test_state.py',
    'tests/test_status_feature.py',
    'tests/test_status_upstream.py',
    'tools/build_release.py',
    'tools/check_export.py',
    'tools/check_skill.py',
    'tools/check_sources.py',
    'vendor/codex_status/LICENSE',
    'vendor/codex_status/iterm_support.py',
    'vendor/codex_status/status.py',
    'vendor/shell_integration/LICENSE',
    'vendor/shell_integration/iterm2_shell_integration.zsh',
)

_PRIVATE = re.compile(
    rb"/(?:Users|home)/[A-Za-z0-9_.-]+|~/(?:\.paiw|\.ai)/|"
    rb"(?<![A-Za-z0-9.-])(?:[A-Za-z0-9_-]+\.)*(?:vk\.team|devmail\.ru|corp\.mail\.ru|codegb\.rustore\.ru)(?=[:/\s\"']|$)",
    re.I,
)
_SHA = re.compile(r"[0-9a-f]{64}")


def check(repo: Path) -> list[str]:
    repo = Path(repo).resolve()
    errors = []
    contents = {}
    for name in EXPORT_FILES:
        path = repo/name
        # Reject links in any component, even links pointing back into the tree.
        if any(p.is_symlink() for p in (path, *path.parents) if p != repo.parent):
            errors.append('Symlink in export: '+name)
            continue
        if not path.is_file():
            errors.append('Missing export file: '+name)
            continue
        try:
            content = path.read_bytes()
        except OSError:
            errors.append('Unreadable export file: '+name)
            continue
        contents[name] = content
        if _PRIVATE.search(content):
            errors.append('Private reference in export: '+name)
    try:
        lock = json.loads(contents['sources.lock.json'])
        entries = lock['sources']
        if not isinstance(entries, list) or not entries:
            raise ValueError()
        seen = set()
        for entry in entries:
            name, digest, ref = entry['path'], entry['sha256'], entry['ref']
            if name not in contents or name in seen or not _SHA.fullmatch(digest):
                raise ValueError()
            seen.add(name)
            if not (re.fullmatch(r'[0-9a-f]{40}', ref) or re.fullmatch(r'v[0-9]+(?:\.[0-9]+)+(?:[-.][A-Za-z0-9]+)*', ref)):
                raise ValueError()
            if hashlib.sha256(contents[name]).hexdigest() != digest:
                errors.append('Source digest mismatch: '+name)
            from urllib.parse import urlparse
            if 'url' in entry:
                url = urlparse(entry['url'])
                if url.scheme != 'https' or not url.hostname or url.username or url.password:
                    raise ValueError()
            elif not all(isinstance(entry.get(k), str) and entry[k].strip() for k in ('source','author')):
                raise ValueError()
            if not isinstance(entry.get('license'), str) or not entry['license'].strip():
                raise ValueError()
            if entry.get('license_file') not in contents or entry.get('attribution_file') != 'THIRD_PARTY_NOTICES.md':
                raise ValueError()
            if 'source' in entry and entry.get('license_scope') != 'bundled-port-only':
                raise ValueError()
            if entry.get('transformation') not in (None, 'none') and not any(k in entry for k in ('upstream_sha256','local_snapshot_sha256')):
                raise ValueError()
            if 'source' in entry and 'upstream_sha256' not in entry:
                raise ValueError()
            for field in ('upstream_sha256', 'local_snapshot_sha256'):
                if field in entry and not _SHA.fullmatch(entry[field]):
                    raise ValueError()
        required = {n for n in contents if n.startswith('vendor/')}
        required |= {n for n in contents if n.startswith('runtime/codex_restore/codexlib/')}
        required |= {'runtime/codex.zsh','runtime/notifier.py','runtime/focus.py','runtime/codex_restore/codex-resume.zsh','runtime/codex_restore/codex-sessions'}
        if not required <= seen:
            errors.append('Missing source provenance')
    except (KeyError, TypeError, ValueError, AttributeError):
        errors.append('Invalid or missing source lock metadata')
    for name in ('LICENSE','THIRD_PARTY_NOTICES.md','vendor/codex_status/LICENSE','vendor/shell_integration/LICENSE'):
        if not contents.get(name, b'').strip():
            errors.append('Missing license or attribution: '+name)
    return errors


if __name__ == '__main__':
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    errors = check(root)
    for error in errors:
        print(error, file=sys.stderr)
    if not errors:
        print(f'{len(EXPORT_FILES)} allowlisted files verified; provenance/licenses/private-reference checks passed.')
    raise SystemExit(bool(errors))
