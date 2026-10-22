"""Public diagnostics serialize an allowlist, never settings or subprocess output."""
import argparse
import json
from dataclasses import asdict
from .commands import Runner
from .discovery import discover, resolve_paths, live_status
from .models import Selection, Finding, Context
from . import lifecycle, migration, state
from .planner import AGENTS, FEATURES, SHORTCUTS, plan


def _csv(value):
    return frozenset(part.strip() for part in value.split(',') if part.strip())


def _exit(findings):
    if any(f.state in {'conflict','missing_dependency','unavailable'} for f in findings):
        return 2
    return 3 if any(f.state in {'pending_ui','new_session'} for f in findings) else 0


def _selection(selection):
    return dict(agents=sorted(selection.agents),features=sorted(selection.features),
                shortcuts=sorted(selection.shortcuts),parent_profile=selection.parent_profile)


def _outcome(mode, result):
    pending = {step.feature for step in result.receipt.pending_ui}
    return dict(mode=mode,selection=_selection(result.receipt.selection),
                completed=sorted(result.receipt.selection.features-pending),pending=sorted(pending),
                findings=[asdict(f) for f in result.findings],ui=[asdict(s) for s in result.receipt.pending_ui])


def main(argv=None):
    parser = argparse.ArgumentParser(description='Inspect and apply explicitly selected iTerm2 features.')
    sub = parser.add_subparsers(dest='command',required=True)
    for command in ('plan','install','update','uninstall','doctor','reconcile'):
        command_parser = sub.add_parser(command)
        command_parser.add_argument('--json',action='store_true')
        if command != 'reconcile':
            command_parser.add_argument('--dry-run',action='store_true')
        if command in {'plan','install'}:
            command_parser.add_argument('--agent',choices=['codex','claude','both'],required=True)
            command_parser.add_argument('--features',required=True,help=', '.join(sorted(FEATURES)))
            command_parser.add_argument('--shortcuts',default='',help=', '.join(sorted(SHORTCUTS)))
            command_parser.add_argument('--parent-profile',default='Default')
            command_parser.add_argument('--adopt-legacy',action='store_true')
        elif command == 'uninstall':
            command_parser.add_argument('--features',required=True)
        elif command == 'doctor':
            command_parser.add_argument('--live',action='store_true')
        elif command == 'reconcile':
            command_parser.add_argument('--step',required=True)
    bootstrap = sub.add_parser('bootstrap-skill', help='Copy only the public setup skill; select no terminal features.')
    bootstrap.add_argument('--agent', choices=['codex','claude','both'], required=True)
    bootstrap.add_argument('--dry-run', action='store_true')
    bootstrap.add_argument('--json', action='store_true')
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    if args.command in {'plan','install','uninstall'}:
        features = _csv(args.features)
        shortcuts = _csv(getattr(args,'shortcuts',''))
        if not features or features-FEATURES or shortcuts-SHORTCUTS:
            if args.json:
                print(json.dumps({'mode':'invalid_selection','findings':[asdict(Finding('selection',None,'invalid_selection','conflict','Choose supported features and shortcuts explicitly.'))]}))
            else:
                print('Choose supported features explicitly; no inspection or changes performed.')
            return 2
    runner = Runner()
    paths = resolve_paths()
    if args.command == 'bootstrap-skill':
        from . import skill_install
        agents = AGENTS if args.agent == 'both' else frozenset({args.agent})
        # Bootstrap reads only its own bundle/receipt, never agent settings or binaries.
        context = Context(paths, {}, {}, frozenset(), {}, {})
        findings = skill_install.install(context, agents, runner, dry_run=args.dry_run)
        output = dict(mode='bootstrap_preview' if args.dry_run else 'bootstrap_skill',
                      selection=dict(agents=sorted(agents), features=[], shortcuts=[], parent_profile='Default'),
                      findings=[asdict(f) for f in findings])
        status = _exit(findings)
    elif args.command in {'plan','install'}:
        agents = AGENTS if args.agent=='both' else frozenset({args.agent})
        context = discover(paths,runner,agents=agents)
        selection = Selection(agents,features,shortcuts,args.parent_profile,args.adopt_legacy)
        if args.command == 'plan':
            prepared = plan(context,selection)
            output = dict(mode='read_only_preview',selection=_selection(prepared.selection),
                          findings=[asdict(f) for f in prepared.changes.findings],
                          ui=[asdict(s) for s in prepared.changes.ui],fingerprint=prepared.fingerprint)
            status = _exit(prepared.changes.findings)
        else:
            result = lifecycle.install(context,selection,runner,dry_run=args.dry_run)
            output = _outcome('install_preview' if args.dry_run else 'install',result)
            status = _exit(result.findings)
    else:
        receipt_error = False
        try:
            receipt = state.load(paths.data/'receipt.json')
        except (ValueError,OSError):
            receipt = None
            receipt_error = True
        agents = receipt.selection.agents if receipt else AGENTS
        context = discover(paths,runner,agents=agents)
        if args.command == 'doctor':
            findings = migration.inspect(context)
            if receipt_error:
                findings.append(Finding('selection',None,'ownership_unavailable','conflict',
                    'The ownership receipt is unreadable or invalid; repair it before updating or uninstalling.'))
            if receipt:
                findings += [Finding(s.feature,s.agent,s.code,'pending_ui',s.instruction) for s in receipt.pending_ui]
            if args.live:
                findings.extend(live_status(context,runner))
                if receipt and 'mcp' in receipt.selection.features:
                    from .config.mcp import probe
                    findings.extend(probe(context,runner,a) for a in sorted(receipt.selection.agents))
            output = dict(mode='read_only_discovery',executables=sorted(context.executables),versions=context.versions,
                          capabilities=sorted(context.capabilities),features=sorted(FEATURES),
                          python_api='ready' if any(f.code=='status_api' and f.state=='ready' for f in findings) else 'not_verified',
                          runtime_connection='not_verified',findings=[asdict(f) for f in findings])
            if receipt:
                output['selection'] = _selection(receipt.selection)
            status = _exit(findings) if 'iterm2' in context.executables else 2
        else:
            if args.command == 'update':
                result = lifecycle.update(context,runner,dry_run=args.dry_run)
            elif args.command == 'uninstall':
                result = lifecycle.uninstall(context,features,runner,dry_run=args.dry_run)
            else:
                result = lifecycle.reconcile_ui(context,args.step,runner)
            output = _outcome(args.command+('_preview' if getattr(args,'dry_run',False) else ''),result)
            status = _exit(result.findings)
    if args.json:
        print(json.dumps(output,sort_keys=True))
    else:
        print(output['mode'].replace('_',' ').capitalize()+'.')
        for finding in output['findings']:
            print(f"{finding['feature']} ({finding['agent'] or 'selection'}): {finding['state']}: {finding['message']}")
        if args.command == 'doctor':
            print('Detected: '+', '.join(output['executables']))
            print('Available features: '+', '.join(sorted(FEATURES)))
    return status
