"""Public diagnostics serialize an allowlist, never settings or subprocess output."""
import argparse
import json
from dataclasses import asdict

from .commands import Runner
from .discovery import discover, resolve_paths
from .models import Selection
from .planner import AGENTS, FEATURES, SHORTCUTS, plan


def _csv(value):
    return frozenset(part.strip() for part in value.split(',') if part.strip())


def _exit(findings):
    if any(f.state in {'conflict', 'missing_dependency', 'unavailable'} for f in findings):
        return 2
    return 3 if any(f.state in {'pending_ui', 'new_session'} for f in findings) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Read-only iTerm2 setup discovery; installation is not implemented yet.')
    sub = parser.add_subparsers(dest='command', required=True)
    doctor = sub.add_parser('doctor', help='Inspect dependencies without changing settings')
    doctor.add_argument('--json', action='store_true')
    preview = sub.add_parser('plan', help='Preview an explicit feature selection; writes nothing')
    preview.add_argument('--agent', choices=['codex', 'claude', 'both'], required=True)
    preview.add_argument('--features', required=True, help=', '.join(sorted(FEATURES)))
    preview.add_argument('--shortcuts', default='', help=', '.join(sorted(SHORTCUTS)))
    preview.add_argument('--parent-profile', default='Default')
    preview.add_argument('--json', action='store_true')
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    if args.command == 'plan':
        agents = AGENTS if args.agent == 'both' else frozenset({args.agent})
        features, shortcuts = _csv(args.features), _csv(args.shortcuts)
        if not features or features - FEATURES or shortcuts - SHORTCUTS:
            print('Choose supported features explicitly; no inspection or changes performed.')
            return 2
        context = discover(resolve_paths(), Runner(), agents=agents)
        result = plan(context, Selection(agents, features, shortcuts, args.parent_profile))
        output = {'mode': 'read_only_preview', 'installation_implemented': False,
                  'selection': {'agents': sorted(result.selection.agents), 'features': sorted(result.selection.features),
                                'shortcuts': sorted(result.selection.shortcuts), 'parent_profile': result.selection.parent_profile},
                  'findings': [asdict(f) for f in result.changes.findings],
                  'ui': [asdict(step) for step in result.changes.ui], 'fingerprint': result.fingerprint}
        status = _exit(result.changes.findings)
    else:
        context = discover(resolve_paths(), Runner())
        output = {'mode': 'read_only_discovery', 'installation_implemented': False,
                  'executables': sorted(context.executables), 'versions': context.versions,
                  'capabilities': sorted(context.capabilities),
                  'features': sorted(FEATURES), 'python_api': 'not_verified',
                  'runtime_connection': 'not_verified'}
        status = 0 if 'iterm2' in context.executables else 2
    if args.json:
        print(json.dumps(output, sort_keys=True))
    else:
        print('Read-only preview. Installation is not implemented yet.')
        if args.command == 'doctor':
            print('Detected: ' + ', '.join(output['executables']))
            print('Python API and live runtime connection: not verified.')
            print('Available features: ' + ', '.join(sorted(FEATURES)))
        else:
            for finding in output['findings']:
                print(f"{finding['feature']} ({finding['agent'] or 'selection'}): {finding['state']}: {finding['message']}")
    return status
