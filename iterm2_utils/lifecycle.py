"""Selective feature checkpoints and explicitly verified native UI ownership."""
import copy
import json
import shlex
from dataclasses import replace
from . import engine, migration, state
from .config import jsonfile, mcp, zshrc
from .discovery import status_installations
from .models import ChangeSet, Finding, Outcome, Plan, Receipt, Selection, FileEdit
from .planner import FEATURES, plan, validate

BLOCKING = {'conflict','missing_dependency','unavailable'}
ORDER = ('shell','clipboard','shortcuts','status','notifications','restore','mcp')


def _empty():
    return Receipt(state.VERSION,Selection(frozenset(),frozenset(),frozenset(),'Default'),[],[])


def _load(context):
    return state.load(context.paths.data/'receipt.json')


def _problem(receipt, code='ownership_unavailable', message='No valid ownership receipt is available.'):
    return Outcome(receipt or _empty(),[Finding('selection',None,code,'conflict',message)])


def _context(context):
    # Refresh only public integration markers; never trust stale ownership hints.
    installed = dict(context.installed)
    detected = status_installations(context.paths,context.executables.get('iterm2'))
    for key in ('codex-status','codex-native-status'):
        installed.pop(key,None)
        if key in detected:
            installed[key] = detected[key]
    return replace(context,installed=installed)


def native_entries(context):
    """Bounded allowlisted native entries; unrelated settings never enter state."""
    path = context.paths.claude_settings
    document = jsonfile.parse(path.read_bytes()) if path.exists() else {}
    expected = {str(context.paths.home/'.config/iterm2/cc-status')}
    if 'iterm2' in context.executables:
        expected.add(str(context.executables['iterm2']/'Contents/Resources/utilities/cc-status'))
    entries = []
    hooks = document.get('hooks',{})
    if not isinstance(hooks,dict):
        raise ValueError('Invalid hooks')
    for event, values in hooks.items():
        if not isinstance(values,list):
            raise ValueError('Invalid hooks')
        for entry in values:
            try:
                state.validate_native_entry({'event':event,'entry':entry})
                words = shlex.split(entry['hooks'][0]['command'])
                if words[0] not in expected:
                    continue
                item = {'event':event,'entry':entry}
                if item in entries:
                    raise RuntimeError('Ambiguous duplicate native hooks')
                entries.append(item)
            except ValueError:
                continue
    return entries


def install(context, selection, runner, *, dry_run=False):
    try:
        expected_receipt = _load(context)
        previous = expected_receipt or _empty()
    except (ValueError,OSError):
        return _problem(None)
    invalid = [f for f in validate(selection,context) if f.code in {'invalid_agents','invalid_features','invalid_shortcuts','invalid_parent'}]
    if invalid:
        return Outcome(previous,invalid)
    # A receipt selection is cumulative; explicit removals belong to uninstall.
    if previous.selection.features and (previous.selection.parent_profile != selection.parent_profile):
        return _problem(previous,'selection_conflict','Keep the recorded parent profile, or uninstall profile features before changing it.')
    findings = [f for f in validate(selection,context) if f.code=='codex_only' and 'codex' not in selection.agents]
    working = previous
    processed = set()
    migration_group = set()
    if selection.adopt_legacy:
        try:
            path = context.paths.zshrc
            blocks = zshrc.blocks(path.read_bytes() if path.exists() else b'')
            migration_group = {feature for name,feature in {'legacy-status':'status','legacy-restore':'restore'}.items() if name in blocks}
        except (ValueError,OSError):
            pass
    # Migrate an existing visible writer before any other consumer switches the
    # shared runtime. A failed status checkpoint must also gate later consumers.
    native_pending = migration.pending_native_status(previous,context)
    order = ('status',)+tuple(f for f in ORDER if f!='status') if native_pending else ORDER
    for feature, agent in [(f,a) for f in order for a in sorted(selection.agents_for(f))]:
        if feature+':'+agent in processed:
            continue
        active = migration_group if feature in migration_group and migration_group <= selection.features else {feature}
        processed.update(f+':'+agent for f in active)
        requested = replace(selection, agents=frozenset({agent}))
        chosen = working.selection.merge(requested, active)
        active_pairs = frozenset(agent+':'+f for f in active)
        prepared = plan(_context(context),chosen)
        # Codex-only means Claude is untouched when both agents were requested.
        shared_codes = {'shell_conflict','hook_conflict','no_daemon'} if feature in {'status','notifications','restore'} else set()
        if feature in {'clipboard','shortcuts'}:
            shared_codes |= {'missing_parent','invalid_parent_keyboard_map','prevent_aps','competing_aps','binding_conflict','profile_conflict'}
        # One profile edit replaces both agents' profiles. Keep blockers for
        # every retained consumer, even if a failed builder emitted no consumers.
        # Non-profile checkpoints never rewrite this document and stay independent.
        profile_blockers = []
        if feature in {'clipboard','shortcuts'}:
            profile_consumers = {p for p in working.selection.pairs
                                 if p.split(':',1)[1] in {'clipboard','shortcuts'}}
            profile_consumers |= set(prepared.changes.consumers.get('shared:agent-profiles', ()))
            profile_blockers = [f for f in prepared.changes.findings if f.state in BLOCKING
                and any(p.endswith(':'+f.feature) and (f.agent is None or p.startswith(f.agent+':'))
                        for p in profile_consumers)]
        prepared.changes.findings = [f for f in prepared.changes.findings
            if (f.feature in (active | {'selection'}) or f.code in shared_codes)
            and f.agent in {None, agent}
            and not (f.code=='codex_only' and 'codex' in selection.agents)]
        prepared.changes.findings.extend(f for f in profile_blockers if f not in prepared.changes.findings)
        prepared.changes.edits = [edit for edit in prepared.changes.edits
            if edit.owner in active_pairs or active_pairs & set(prepared.changes.consumers.get(edit.owner,()))]
        prepared.changes.ui = [step for step in prepared.changes.ui if step.feature in active and step.agent in {None, agent}]
        if (native_pending and 'codex:status' not in active_pairs
                and any(edit.owner=='shared:runtime' for edit in prepared.changes.edits)):
            findings.append(Finding(feature,agent,'status_migration_required','conflict',
                'The owned Codex status migration must succeed before another consumer can switch its shared runtime; run update and resolve its status conflicts.'))
            continue
        if feature in working.selection.features_for(agent):
            pending_codes = {step.code for step in working.pending_ui}
            try:
                prepared.changes.ui = [step for step in prepared.changes.ui if step.code in pending_codes or
                    (step.code == 'claude-native-status' and not native_entries(context))]
            except (ValueError,OSError,RuntimeError):
                findings.append(Finding(feature,None,'ui_verification_failed','pending_ui','Native integration could not be verified; no checkpoint was applied.'))
                continue
            if not prepared.changes.ui:
                prepared.changes.findings = [f for f in prepared.changes.findings if f.state != 'pending_ui']
        for edit in prepared.changes.edits:
            if (edit.owner == 'shared:agent-profiles' and edit.before is not None and edit.before != edit.after
                    and not any(r['target']==str(edit.path.resolve()) and edit.owner in r['owners'] for r in working.resources)):
                prepared.changes.findings.append(Finding(feature,None,'profile_conflict','conflict','The existing dedicated profile is externally owned; choose a profile conflict resolution before replacing it.'))
        blocking = [f for f in prepared.changes.findings if f.state in BLOCKING]
        if blocking:
            findings.extend(blocking)
            continue
        snapshots = copy.deepcopy(working.ui_snapshots)
        if any(s.code=='claude-native-status' for s in prepared.changes.ui) and 'claude-native-status' not in snapshots:
            try:
                snapshots['claude-native-status'] = native_entries(context)
            except (ValueError,OSError,RuntimeError):
                findings.append(Finding(feature,None,'ui_snapshot_conflict','conflict','Native integration snapshot could not be verified.'))
                continue
        # Preserve a pending native step across repeats even if its hooks appeared;
        # only explicit reconcile may claim ownership or clear the pending state.
        for step in working.pending_ui:
            if step not in prepared.changes.ui:
                prepared.changes.ui.append(step)
        if dry_run:
            if 'codex:status' in active_pairs:
                native_pending = False
            findings.extend(prepared.changes.findings)
            working = Receipt(state.VERSION,chosen,working.resources,prepared.changes.ui,snapshots)
            continue
        result = engine.apply(prepared,context,runner,ui_snapshots=snapshots,expected_receipt=expected_receipt)
        findings.extend(result.findings)
        if not any(f.state in BLOCKING for f in result.findings):
            working = result.receipt
            native_pending = migration.pending_native_status(working,context)
            expected_receipt = working
            for completed in sorted(active):
                pending = any(s.feature==completed for s in working.pending_ui)
                findings.append(Finding(completed,None,'feature_checkpoint','pending_ui' if pending else 'ready','Resources committed; explicit UI verification remains pending.' if pending else 'Feature checkpoint committed.'))
        else:
            # Engine may retain a previous receipt after a failed write.
            expected_receipt = _load(context)
            working = expected_receipt or working
    return Outcome(working,findings)


def update(context, runner, *, dry_run=False):
    try:
        receipt = _load(context)
    except (ValueError,OSError):
        receipt = None
    if receipt is None:
        return _problem(None)
    if not receipt.selection.features:
        return Outcome(receipt,[])
    return install(context,receipt.selection,runner,dry_run=dry_run)


def uninstall(context, owners, runner, *, dry_run=False, agents=None):
    try:
        receipt = _load(context)
    except (ValueError,OSError):
        receipt = None
    if receipt is None:
        return _problem(None)
    if not owners or owners - FEATURES:
        return _problem(receipt,'invalid_selection','Choose supported features explicitly.')
    agents = receipt.selection.agents if agents is None else agents
    selection = receipt.selection.without(owners, agents)
    remove_pairs = receipt.selection.pairs - selection.pairs
    if not remove_pairs:
        return Outcome(receipt, [])
    normalized = engine.pair_resources(receipt.resources, receipt.selection, context)
    refreshed = _context(context)
    if (refreshed.installed.get('codex-native-status')
            and migration.restores_legacy_status(normalized,remove_pairs,context)):
        return _problem(receipt,'legacy_status_restore_conflict',
            'External native hooks prevent restoring the adopted legacy status writer; resolve the competing integration before uninstalling.')
    # Recompose shared files and remove exclusive resources in ONE transaction.
    prepared = plan(refreshed,selection) if selection.features else Plan(selection,ChangeSet([],[],[]),'uninstall')
    affected_shared = {owner for r in normalized if set(r['owners']) & remove_pairs
                       for owner in r['owners'] if owner.startswith('shared:')}
    # Ordinarily runtime files need only consumer removal. If recomposition
    # migrates a retained old status writer, switch its runtime in this same
    # transaction so native settings never point at the beta.1 driver.
    migrate_runtime = (migration.pending_native_status(receipt,context)
                       and 'codex:status' in selection.pairs
                       and 'shared:hooks' in affected_shared)
    if not migrate_runtime:
        affected_shared.discard('shared:runtime')
    prepared.changes.edits = [e for e in prepared.changes.edits if e.owner in affected_shared]
    # Required consumers come from the committed checkpoint, not from a builder
    # that may have failed before emitting its consumer map.
    retained_consumers = {owner:set() for owner in affected_shared}
    for resource in normalized:
        for owner in affected_shared & set(resource['owners']):
            retained_consumers[owner].update(set(resource['owners']) & selection.pairs)
    related = set().union(*retained_consumers.values())
    emitted = {edit.owner for edit in prepared.changes.edits}
    for owner, consumers in retained_consumers.items():
        if consumers and owner not in emitted:
            prepared.changes.findings.append(Finding(sorted(consumers)[0].split(':',1)[-1],None,'recomposition_unavailable','conflict',
                'A retained shared resource could not be rebuilt; the previous selection and ownership are preserved.'))
    prepared.changes.findings = [f for f in prepared.changes.findings
                                if any(p.endswith(':'+f.feature) and (f.agent is None or p.startswith(f.agent+':')) for p in related) or f.code in {'shell_conflict','hook_conflict'} and affected_shared]
    prepared.changes.ui = [s for s in receipt.pending_ui if (s.agent+':'+s.feature not in remove_pairs if s.agent else s.feature in selection.features)]
    if dry_run:
        return Outcome(receipt,prepared.changes.findings+[Finding(f,None,'uninstall_preview','ready','Only unchanged owned values will be removed.') for f in sorted(owners)])
    snapshots = {k:v for k,v in receipt.ui_snapshots.items() if any(s.code==k for s in prepared.changes.ui)}
    result = engine.apply(prepared,context,runner,ui_snapshots=snapshots,remove_owners=remove_pairs,expected_receipt=receipt)
    if any(f.state in BLOCKING and f.code != 'uninstall_changed' for f in result.findings):
        result.receipt = _load(context) or receipt
    return result


def reconcile_ui(context, code, runner):
    try:
        if _load(context) is None:
            return _problem(None)
        with engine._lock(context):
            recovery = engine._recover(context,runner)
            receipt = _load(context)
            if receipt is None:
                return _problem(None)
            if recovery:
                return Outcome(receipt,recovery)
            steps = [s for s in receipt.pending_ui if s.code==code]
            if not steps:
                return _problem(receipt,'unknown_ui_step','No such pending UI step exists in the receipt.')
            result = copy.deepcopy(receipt)
            findings = []
            if code == 'claude-native-status':
                if code not in receipt.ui_snapshots:
                    return _problem(receipt,'missing_ui_snapshot','A pre-UI snapshot is required; do not infer ownership from current settings.')
                current = native_entries(context)
                if not current:
                    return Outcome(receipt,[Finding('status','claude','native_status','pending_ui','Native cc-status hooks are not yet verified; the UI step remains pending.')])
                before = receipt.ui_snapshots[code]
                for item in current:
                    if item in before:
                        continue
                    entry = item['entry']
                    resource = engine._resource('hook',context.paths.claude_settings.resolve(),{'pointer':['hooks',item['event']],'entry':entry,'mode':0o600},engine._value(exists=False),engine._value(entry),'claude:status' if receipt.selection.agent_features is not None else 'status')
                    if not engine._same(engine._read(resource,runner,context),resource['installed']):
                        raise ValueError('Changed native hook')
                    if not any(engine._identity(r)==engine._identity(resource) for r in result.resources):
                        result.resources.append(resource)
                findings.append(Finding('status','claude','native_status','ready','Native hooks verified; pre-existing entries remain externally owned.'))
            elif code in {'mcp_authorize','python_api'}:
                findings = [mcp.probe(context,runner,s.agent) for s in steps if s.agent]
                if not findings or any(f.state != 'ready' for f in findings):
                    return Outcome(receipt,findings or [Finding('mcp',None,code,'pending_ui','Live MCP verification remains pending.')])
            else:
                return _problem(receipt,'unknown_ui_step','This pending step has no automatic verifier.')
            result.pending_ui = [s for s in result.pending_ui if s.code!=code]
            result.ui_snapshots.pop(code,None)
            ok, failed = engine._transaction([],result,context,runner)
            return Outcome(result if ok else receipt,findings+failed)
    except (ValueError,OSError,RuntimeError):
        try:
            receipt = _load(context)
        except (ValueError,OSError):
            receipt = None
        return Outcome(receipt or _empty(),[Finding('status',None,'ui_verification_failed','pending_ui','Verification was inconclusive; the UI step remains pending and was not retried.')])


def doctor(context, receipt, runner):
    """Read-only verification; never recover journals or reconcile UI implicitly."""
    prepared = plan(_context(context), receipt.selection)
    findings = [f for f in prepared.changes.findings if f.state in BLOCKING or f.state == 'limited'
                or f.code in {'status_backend','native_status_capability'}
                or f.code == 'native_status' and f.state == 'pending_ui']
    # Reused configuration carries no ownership receipt. Check the selected
    # declarative addresses too, without applying the generated edits.
    for edit in prepared.changes.edits:
        if not isinstance(edit, FileEdit):
            continue
        if edit.path not in {context.paths.codex_home/'hooks.json', context.paths.claude_settings}:
            continue
        agent = 'codex' if edit.path == context.paths.codex_home/'hooks.json' else 'claude'
        feature = sorted(receipt.selection.features_for(agent) & {'status','notifications','restore'})[0]
        try:
            changed_hooks = engine._compile(edit)
            if any(r['kind']=='hook' and r['installed']['exists'] for r in changed_hooks):
                findings.append(Finding(feature, agent, 'selected_hook_missing', 'conflict',
                    'A selected hook is absent; inspect the installation before updating.'))
        except (OSError, ValueError, TypeError):
            findings.append(Finding(feature, agent, 'resource_unavailable', 'conflict',
                'Selected hook configuration could not be verified.'))
    for resource in receipt.resources:
        owner = next((o for o in resource['owners'] if not o.startswith('shared:')), 'selection')
        agent, feature = owner.split(':', 1) if ':' in owner else (None, owner)
        try:
            current = engine._read(resource, runner, context)
            if not engine._same(current, resource['installed']):
                missing = resource['installed']['exists'] and not current['exists']
                findings.append(Finding(feature, agent, 'owned_resource_missing' if missing else 'owned_resource_changed',
                    'conflict', 'Owned resource is missing: ' + resource['target'] if missing else 'Owned resource differs from the receipt: ' + resource['target']))
        except (OSError, ValueError, TypeError, RuntimeError):
            findings.append(Finding(feature, agent, 'resource_unavailable', 'unavailable',
                'Owned resource could not be inspected: '+resource['target']))
    # Identical external registrations may be reused without receipt ownership.
    for agent in sorted(receipt.selection.agents_for('mcp')):
        try:
            actual = mcp.inspect(agent, mcp.NAME, context, runner)
            if actual != mcp.definition():
                findings.append(Finding('mcp', agent, 'registration_missing' if actual is None else 'registration_changed',
                    'conflict', 'Selected MCP registration is missing or differs from the pinned definition.'))
        except (ValueError, OSError, RuntimeError):
            findings.append(Finding('mcp', agent, 'registration_unavailable', 'unavailable', 'Selected MCP registration could not be verified.'))
    return findings
