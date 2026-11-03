"""Project launcher behavior on private temporary files and synthetic SDK state."""
import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from unittest.mock import patch

from iterm2_utils import engine, lifecycle, state
from iterm2_utils.config import iterm
from iterm2_utils.models import FileEdit, ProfileBarEdit
from iterm2_utils.planner import FEATURES, plan
from tests.test_lifecycle import LifecycleFixture


class ProjectLauncherTests(LifecycleFixture):
    def setUp(self):
        super().setUp()
        self.context.capabilities |= {'python:iterm2'}
        self.bar = {'Show Status Bar': False, 'Status Bar Layout': {
            'components': [{'class': 'foreign', 'knobs': {}}], 'advanced configuration': {'margin': 7}}}
        self.native = {'complete': True, 'profiles': [dict(guid='parent-guid', name='Default',
            bar=copy.deepcopy(self.bar), working_directory=None, references=[])],
            'sessions': [], 'default_guid': 'parent-guid', 'position': 0}
        self.config = self.context.paths.home/'projects.json'
        self.folder = self.context.paths.home/'project-a'; self.folder.mkdir()
        self.folder_b = self.context.paths.home/'project-b'; self.folder_b.mkdir()
        self.document = {'profiles': ['Default'], 'projects': [
            {'id': 'project-a', 'name': 'Проект A', 'path': str(self.folder)},
            {'id': 'project-b', 'name': 'Проект B', 'path': str(self.folder_b)}]}
        self.write_config()
        self.context.project_launcher_config = self.config
        self.calls = []
        p = patch.object(iterm, '_request', side_effect=self.request); p.start(); self.addCleanup(p.stop)

    @property
    def dynamic(self):
        return self.context.paths.profiles/'iterm2-utils-project-launcher.json'

    def write_config(self):
        self.config.write_text(json.dumps(self.document))

    def request(self, context, runner, request):
        self.calls.append(copy.deepcopy(request))
        operation = request['operation']
        if operation == 'inspect':
            snapshot = copy.deepcopy(self.native)
            if self.dynamic.exists():
                for row in json.loads(self.dynamic.read_text())['Profiles']:
                    snapshot['profiles'].append(dict(guid=row['Guid'], name=row['Name'],
                        bar={k:row[k] for k in iterm.BAR_KEYS}, working_directory=row['Working Directory'], references=[]))
            guids = set(request.get('reference_guids', ())) | {p['guid'] for p in snapshot['profiles']}
            replacements = {r['guid']:r['bar'] for r in request.get('replaced_bars',())}
            for row in snapshot['profiles']:
                bar = row['bar']
                if row['guid'] in replacements:
                    if not iterm.same(bar,replacements[row['guid']]): raise ValueError()
                    bar = {}
                row['references'] = sorted(set(row['references']) | {g for g in guids if g in json.dumps(bar)})
            return snapshot
        if operation.endswith('_bar'):
            row = next(p for p in self.native['profiles'] if p['guid'] == request['guid'])
            value = row['bar']
        else:
            value = self.native['position']
        if operation.startswith('write_'):
            if not iterm.same(request['expected'], {'exists': True, 'value': value}): raise ValueError()
            if operation.endswith('_bar'):
                row['bar'] = copy.deepcopy(request['value'])
            else:
                self.native['position'] = request['value']
            value = request['value']
        return {'exists': True, 'value': copy.deepcopy(value)}

    def test_feature_is_explicit_and_builder_preserves_foreign_layout(self):
        self.assertIn('project-launcher', FEATURES)
        self.context.profiles['Default'].update({'Custom Command':'Yes','Command':'codex PRIVATE'})
        result = lifecycle.install(self.context, self.selection('project-launcher'), self.runner)
        self.assertSuccess(result)
        rows = json.loads(self.dynamic.read_text())['Profiles']
        self.assertEqual([p['Name'] for p in rows], ['Проект A', 'Проект B'])
        for row in rows:
            self.assertEqual(row['Dynamic Profile Parent GUID'], 'parent-guid')
            self.assertEqual(row['Custom Command'], 'No')
            self.assertEqual(row['Command'], '')
            self.assertEqual(row['Custom Directory'], 'Yes')
            self.assertEqual(row['Status Bar Layout']['advanced configuration'], {'margin': 7})
            components = row['Status Bar Layout']['components']
            self.assertEqual(components[0], {'class': 'foreign', 'knobs': {}})
            self.assertTrue(all('configuration' in c for c in components[1:]),'Native action components require configuration wrapper')
            actions = [c['configuration']['knobs']['action'] for c in components[1:]]
            self.assertTrue(all(c['configuration']['knobs']['base: priority']==5 for c in components[1:]))
            self.assertTrue(all(c['configuration']['layout advanced configuration dictionary value']['algorithm']==0 for c in components[1:]))
            self.assertEqual([a['parameter'] for a in actions], [p['Guid'] for p in rows])
            self.assertEqual([a['title'] for a in actions], ['Проект A', 'Проект B'])
            self.assertTrue(all(a['action']==27 and a['version']==2 and a['applyMode']==0 and a['escaping']==1 for a in actions))
        self.assertEqual(rows[0]['Working Directory'], str(self.folder))
        self.assertEqual(self.native['position'], 1)
        self.assertEqual(self.native['profiles'][0]['bar'], {k:rows[0][k] for k in iterm.BAR_KEYS})
        self.assertEqual(self.dynamic.stat().st_mode & 0o777, 0o600)

    def test_existing_identical_foreign_button_is_not_duplicated_or_erased(self):
        from iterm2_utils.features import project_launcher
        selection=self.selection('project-launcher')
        prepared=plan(project_launcher.prepare(self.context,selection,self.runner),selection)
        bar=next(e.after for e in prepared.changes.edits if isinstance(e,ProfileBarEdit))
        component=copy.deepcopy(bar['Status Bar Layout']['components'][1])
        self.native['profiles'][0]['bar']['Status Bar Layout']['components'].append(component)
        self.assertSuccess(self.install('project-launcher'))
        components=self.native['profiles'][0]['bar']['Status Bar Layout']['components']
        self.assertEqual(len(components),3)
        result=lifecycle.uninstall(self.context,{'project-launcher'},self.runner)
        self.assertTrue(any(f.state=='conflict' for f in result.findings))
        self.assertTrue(self.dynamic.exists());self.assertIn(component,self.native['profiles'][0]['bar']['Status Bar Layout']['components'])


    def test_removing_project_preserves_identical_baseline_foreign_button_and_checkpoint(self):
        from iterm2_utils.features.project_launcher import _component
        component=_component(self.document['projects'][0])
        baseline=self.native['profiles'][0]['bar']['Status Bar Layout']['components']
        baseline.extend([copy.deepcopy(component),{'class':'foreign-last','knobs':{}}])
        installed=self.install('project-launcher');self.assertSuccess(installed)
        native=copy.deepcopy(self.native);dynamic=self.dynamic.read_bytes()
        owned_config=self.context.paths.config/'iterm2-utils-project-launcher.json'
        config_before=owned_config.read_bytes()
        self.document['projects'].pop(0);self.write_config()
        result=self.install('project-launcher')
        self.assertTrue(any(f.state=='conflict' for f in result.findings),result.findings)
        self.assertEqual(self.native,native)
        self.assertEqual(self.native['profiles'][0]['bar']['Status Bar Layout']['components'][:3],baseline)
        self.assertEqual(self.dynamic.read_bytes(),dynamic)
        self.assertEqual(owned_config.read_bytes(),config_before)
        self.assertEqual(result.receipt,installed.receipt)
        self.assertEqual(state.load(self.context.paths.data/'receipt.json'),installed.receipt)

    def test_foreign_generated_guid_is_rejected_before_writes_for_same_or_different_name(self):
        from iterm2_utils.features.project_launcher import guid
        for name in ('Проект A','Project A'):
            with self.subTest(name=name):
                fixture=ProjectLauncherTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
                fixture.native['profiles'].append(dict(guid=guid('project-a'),name=name,
                    bar=copy.deepcopy(fixture.bar),working_directory=None,references=[]))
                before=fixture.snapshot();native=copy.deepcopy(fixture.native)
                result=fixture.install('project-launcher')
                self.assertTrue(any(f.state=='conflict' for f in result.findings),result.findings)
                self.assertEqual(fixture.snapshot(),before)
                self.assertEqual(fixture.native,native)
                self.assertFalse(fixture.dynamic.exists())
                self.assertFalse((fixture.context.paths.data/'receipt.json').exists())


    def test_schema_errors_block_every_effect_and_do_not_publish_config(self):
        variants = [{}, dict(self.document, unknown='PRIVATE'), dict(self.document, profiles=[]),
            dict(self.document, profiles=['Default','Default']), dict(self.document, projects=[])]
        for field, value in [('id',''),('id',None),('name',''),('name','PRIVATE\n'),('path','relative'),
                             ('path',str(self.folder/'missing')),('path',str(self.config)),('unknown','PRIVATE')]:
            doc = copy.deepcopy(self.document); doc['projects'][0][field] = value; variants.append(doc)
        for field in ('id','name'):
            doc = copy.deepcopy(self.document); doc['projects'][1][field] = doc['projects'][0][field]; variants.append(doc)
        for document in variants:
            with self.subTest(document=document):
                self.config.write_text(json.dumps(document)); before=self.snapshot()
                result=lifecycle.install(self.context,self.selection('project-launcher'),self.runner)
                self.assertTrue(any(f.state=='conflict' for f in result.findings), result)
                self.assertEqual(self.snapshot(),before)
                self.assertNotIn('PRIVATE',str(result)); self.assertEqual(self.calls,[])
        self.config.write_text('{PRIVATE'); before=self.snapshot()
        result=lifecycle.install(self.context,self.selection('project-launcher'),self.runner)
        self.assertEqual(self.snapshot(),before); self.assertNotIn('PRIVATE',str(result))

    def test_missing_ambiguous_profile_and_prerequisites_block_without_files(self):
        cases = ['missing','duplicate','version','sdk','inventory','sessions']
        original=copy.deepcopy(self.native)
        for case in cases:
            with self.subTest(case=case):
                self.native=copy.deepcopy(original)
                context=replace(self.context)
                if case=='missing': self.native['profiles'][0]['name']='Project A'
                if case=='duplicate': self.native['profiles'].append(dict(self.native['profiles'][0],guid='second'))
                if case=='version': context.versions=dict(context.versions,iterm2='3.8.0')
                if case=='sdk': context.capabilities -= {'python:iterm2'}
                if case=='inventory': self.native['complete']=False
                if case=='sessions': self.native['sessions']=[dict(id='s',profile_guid='parent-guid',bar=dict(self.bar,**{'Show Status Bar':True}),references=[],provenance=True)]
                before=self.snapshot()
                result=lifecycle.install(context,self.selection('project-launcher'),self.runner)
                self.assertTrue(any(f.state in lifecycle.BLOCKING for f in result.findings),result)
                self.assertEqual(self.snapshot(),before)

    def test_repeat_update_without_source_stable_guid_and_dryrun(self):
        before=self.snapshot()
        self.assertSuccess(lifecycle.install(self.context,self.selection('project-launcher'),self.runner,dry_run=True))
        self.assertEqual(self.snapshot(),before)
        self.assertSuccess(self.install('project-launcher'))
        rows=json.loads(self.dynamic.read_text())['Profiles']; guid=rows[0]['Guid']
        self.config.unlink(); self.context.project_launcher_config=None
        self.assertSuccess(lifecycle.update(self.context,self.runner))
        self.assertEqual(json.loads(self.dynamic.read_text())['Profiles'],rows)
        self.document['projects'][0].update(name='Project A',path=str(self.folder_b));self.write_config()
        self.context.project_launcher_config=self.config
        self.assertSuccess(self.install('project-launcher'))
        row=json.loads(self.dynamic.read_text())['Profiles'][0]
        self.assertEqual(row['Guid'],guid);self.assertEqual(row['Name'],'Project A');self.assertEqual(row['Working Directory'],str(self.folder_b))

    def test_shared_consumers_partial_then_full_uninstall_restores_panel(self):
        self.assertSuccess(self.install('project-launcher',agents=('codex','claude')))
        result=lifecycle.uninstall(self.context,{'project-launcher'},self.runner,agents={'codex'})
        self.assertSuccess(result);self.assertTrue(self.dynamic.exists())
        self.assertEqual(result.receipt.selection.pairs,{'claude:project-launcher'})
        result=lifecycle.uninstall(self.context,{'project-launcher'},self.runner)
        self.assertSuccess(result);self.assertFalse(self.dynamic.exists())
        self.assertEqual(self.native['profiles'][0]['bar'],self.bar);self.assertEqual(self.native['position'],0)

    def test_moved_directory_keeps_project_guid(self):
        self.assertSuccess(self.install('project-launcher'))
        guid=json.loads(self.dynamic.read_text())['Profiles'][0]['Guid']
        moved=self.folder.with_name('project-a-moved');self.folder.rename(moved)
        self.document['projects'][0]['path']=str(moved);self.write_config()
        self.assertSuccess(self.install('project-launcher'))
        row=json.loads(self.dynamic.read_text())['Profiles'][0]
        self.assertEqual(row['Guid'],guid);self.assertEqual(row['Working Directory'],str(moved))

    def test_removed_missing_directory_does_not_block_valid_config(self):
        self.assertSuccess(self.install('project-launcher'))
        self.folder.rmdir();self.document['projects'].pop(0);self.write_config()
        self.assertSuccess(self.install('project-launcher'))
        rows=json.loads(self.dynamic.read_text())['Profiles']
        self.assertEqual([p['Name'] for p in rows],['Проект B'])
        self.assertEqual(len(self.native['profiles'][0]['bar']['Status Bar Layout']['components']),2)

    def test_whole_file_late_edit_preserved_with_receipt(self):
        self.assertSuccess(self.install('project-launcher'))
        document=json.loads(self.dynamic.read_text());document['foreign']='keep'
        self.dynamic.write_text(json.dumps(document));before=self.dynamic.read_bytes()
        result=lifecycle.uninstall(self.context,{'project-launcher'},self.runner)
        self.assertTrue(any(f.state=='conflict' for f in result.findings))
        self.assertEqual(self.dynamic.read_bytes(),before)
        self.assertTrue(any(r['target']==str(self.dynamic.resolve()) for r in result.receipt.resources))

    def test_late_one_bar_field_conflict_keeps_panel_targets_and_receipt(self):
        self.assertSuccess(self.install('project-launcher'))
        self.native['profiles'][0]['bar']['Show Status Bar']=False
        bar=copy.deepcopy(self.native['profiles'][0]['bar']);before=self.dynamic.read_bytes()
        result=lifecycle.uninstall(self.context,{'project-launcher'},self.runner)
        self.assertTrue(any(f.state=='conflict' for f in result.findings))
        self.assertEqual(self.native['profiles'][0]['bar'],bar);self.assertEqual(self.dynamic.read_bytes(),before)
        self.assertTrue(any(r['kind']=='profile_bar' for r in result.receipt.resources))

    def test_fresh_reference_guard_blocks_update_and_uninstall_with_live_session(self):
        self.assertSuccess(self.install('project-launcher'))
        guid=json.loads(self.dynamic.read_text())['Profiles'][1]['Guid']
        self.native['sessions']=[dict(id='s',profile_guid=guid,bar=copy.deepcopy(self.bar),references=[],provenance=True)]
        before=self.dynamic.read_bytes()
        result=lifecycle.uninstall(self.context,{'project-launcher'},self.runner)
        self.assertTrue(any(f.state=='conflict' for f in result.findings));self.assertEqual(self.dynamic.read_bytes(),before)
        self.document['projects'].pop();self.write_config()
        result=self.install('project-launcher')
        self.assertTrue(any(f.state=='conflict' for f in result.findings));self.assertEqual(self.dynamic.read_bytes(),before)
        self.native['sessions']=[]
        self.assertSuccess(self.install('project-launcher'))
        self.assertEqual(len(json.loads(self.dynamic.read_text())['Profiles']),1)

    def test_uninstall_changed_file_keeps_full_checkpoint_for_retry(self):
        original=self.install('project-launcher');self.assertSuccess(original)
        self.dynamic.write_bytes(self.dynamic.read_bytes()+b' ')
        before=self.snapshot();bar=copy.deepcopy(self.native)
        result=lifecycle.uninstall(self.context,{'project-launcher'},self.runner)
        self.assertEqual(result.receipt,original.receipt)
        self.assertEqual(self.snapshot(),before);self.assertEqual(self.native,bar)

    def interrupted_install(self):
        request=self.request
        def uncertain(context,runner,payload):
            value=request(context,runner,payload)
            if payload['operation']=='write_bar': raise iterm.MutationUnknown()
            return value
        with patch.object(iterm,'_request',side_effect=uncertain):
            result=self.install('project-launcher')
        self.assertTrue(any(f.code=='native_outcome_unknown' for f in result.findings))
        self.assertTrue((self.context.paths.data/'journal/intent.json').exists())
        self.assertTrue(self.dynamic.exists());self.assertNotEqual(self.native['profiles'][0]['bar'],self.bar)
        self.assertIsNone(state.load(self.context.paths.data/'receipt.json'))

    def resume(self, command, *, dry_run=False):
        if command=='install':
            return lifecycle.install(self.context,self.selection('project-launcher'),self.runner,dry_run=dry_run)
        if command=='update':
            return lifecycle.update(self.context,self.runner,dry_run=dry_run)
        return lifecycle.uninstall(self.context,{'project-launcher'},self.runner,dry_run=dry_run)

    def test_public_mutations_recover_first_unknown_install_before_planning(self):
        for command in ('install','update','uninstall'):
            with self.subTest(command=command):
                fixture=ProjectLauncherTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
                fixture.interrupted_install();fixture.calls.clear()
                result=fixture.resume(command)
                self.assertFalse((fixture.context.paths.data/'journal').exists())
                writes=[c for c in fixture.calls if c['operation']=='write_bar']
                self.assertEqual(writes[0]['value'],fixture.bar)
                if command=='install':
                    fixture.assertSuccess(result)
                    self.assertTrue(fixture.dynamic.exists())
                    self.assertIsNotNone(state.load(fixture.context.paths.data/'receipt.json'))
                    self.assertEqual(writes[1]['expected']['value'],fixture.bar)
                else:
                    self.assertFalse(fixture.dynamic.exists())
                    self.assertEqual(fixture.native['profiles'][0]['bar'],fixture.bar)
                    self.assertEqual([f.code for f in result.findings],['ownership_unavailable'])

    def test_public_recovery_preserves_late_bar_edits_and_external_references(self):
        for command in ('install','update','uninstall'):
            for change in ('bar','file','reference'):
                with self.subTest(command=command,change=change):
                    fixture=ProjectLauncherTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
                    fixture.interrupted_install()
                    if change=='bar':
                        fixture.native['profiles'][0]['bar']['Show Status Bar']=False
                    elif change=='file':
                        fixture.dynamic.write_bytes(fixture.dynamic.read_bytes()+b' ')
                    else:
                        guid=json.loads(fixture.dynamic.read_text())['Profiles'][0]['Guid']
                        fixture.native['sessions']=[dict(id='s',profile_guid=guid,bar=copy.deepcopy(fixture.bar),references=[],provenance=True)]
                    bar=copy.deepcopy(fixture.native['profiles'][0]['bar']);before=fixture.dynamic.read_bytes()
                    result=fixture.resume(command)
                    self.assertTrue(any(f.code=='rollback_unresolved' for f in result.findings),result.findings)
                    self.assertTrue((fixture.context.paths.data/'journal').exists())
                    self.assertEqual(fixture.dynamic.read_bytes(),before)
                    if change=='bar': self.assertEqual(fixture.native['profiles'][0]['bar'],bar)
                    self.assertIsNone(state.load(fixture.context.paths.data/'receipt.json'))

    def test_public_mutations_reload_receipt_after_pending_commit(self):
        for command in ('install','update','uninstall'):
            with self.subTest(command=command):
                fixture=ProjectLauncherTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
                receipt_path=fixture.context.paths.data/'receipt.json';save=state.save
                def interrupted_save(path,receipt):
                    if path==receipt_path: raise OSError('interrupted receipt commit')
                    save(path,receipt)
                with patch.object(state,'save',side_effect=interrupted_save):
                    result=fixture.install('project-launcher')
                self.assertTrue(any(f.code=='commit_pending' for f in result.findings))
                self.assertFalse(receipt_path.exists())
                fixture.config.unlink();fixture.context.project_launcher_config=None
                result=fixture.resume(command);fixture.assertSuccess(result)
                self.assertFalse((fixture.context.paths.data/'journal').exists())
                self.assertEqual(state.load(receipt_path),result.receipt)
                self.assertEqual(fixture.dynamic.exists(),command!='uninstall')

    def test_pending_recovery_dry_runs_plan_and_doctor_never_write(self):
        from iterm2_utils.features.project_launcher import prepare
        self.interrupted_install();before=self.snapshot();native=copy.deepcopy(self.native)
        for command in ('install','update','uninstall'):
            self.resume(command,dry_run=True)
        selection=self.selection('project-launcher')
        plan(prepare(self.context,selection,self.runner),selection)
        lifecycle.doctor(self.context,replace(lifecycle._empty(),selection=selection),self.runner)
        self.assertEqual(self.snapshot(),before);self.assertEqual(self.native,native)

    def test_public_recovery_respects_transaction_lock(self):
        self.interrupted_install();before=self.snapshot();native=copy.deepcopy(self.native)
        with engine._lock(self.context):
            result=self.resume('install')
        self.assertEqual([f.code for f in result.findings],['recovery_unavailable'])
        self.assertEqual(self.snapshot(),before);self.assertEqual(self.native,native)

    def test_historical_config_keeps_schema_and_path_type_validation(self):
        from iterm2_utils.features.project_launcher import _config
        self.folder.rmdir()
        self.assertEqual(_config(self.config.read_bytes(),historical=True),self.document)
        with self.assertRaises(ValueError): _config(self.config.read_bytes())
        variants=[dict(self.document,unknown=True),dict(self.document,profiles=['Default','Default'])]
        for field,value in [('path',None),('path','relative'),('path','/invalid\n'),('name',''),('id',7),('extra',True)]:
            document=copy.deepcopy(self.document);document['projects'][0][field]=value;variants.append(document)
        for document in variants:
            with self.subTest(document=document),self.assertRaises(ValueError):
                _config(json.dumps(document).encode(),historical=True)
        with self.assertRaises(ValueError):
            _config(b'{"profiles":[],"profiles":[],"projects":[]}',historical=True)

    def test_guard_runs_in_actual_set_inverse_and_recovery(self):
        self.assertSuccess(self.install('project-launcher'))
        receipt=state.load(self.context.paths.data/'receipt.json')
        resource=next(r for r in receipt.resources if r['target']==str(self.dynamic.resolve()))
        guid=json.loads(self.dynamic.read_text())['Profiles'][0]['Guid']
        self.native['sessions']=[dict(id='s',profile_guid=guid,bar=copy.deepcopy(self.bar),references=[],provenance=True)]
        before=self.dynamic.read_bytes()
        with self.assertRaises(ValueError):
            engine._set(resource,resource['before'],self.runner,self.context,expected=resource['installed'])
        unresolved, findings=engine._inverse([resource],self.runner,self.context)
        self.assertTrue(unresolved);self.assertTrue(findings)
        journal=self.context.paths.data/'journal';journal.mkdir()
        state.save(journal/'intent.json',replace(receipt,resources=[resource]))
        self.assertTrue(engine._recover(self.context,self.runner));self.assertTrue(journal.exists())
        self.assertEqual(self.dynamic.read_bytes(),before)
        self.assertNotIn(str(self.folder),str(findings))
        self.assertNotIn(str(self.dynamic),str(findings))

    def test_fresh_external_hidden_reference_preserves_targets(self):
        self.assertSuccess(self.install('project-launcher'))
        guid=json.loads(self.dynamic.read_text())['Profiles'][0]['Guid']
        self.native['profiles'].append(dict(guid='foreign',name='Project A',bar=copy.deepcopy(self.bar),working_directory=None,references=[guid]))
        before=self.dynamic.read_bytes()
        result=lifecycle.uninstall(self.context,{'project-launcher'},self.runner)
        self.assertTrue(any(f.state=='conflict' for f in result.findings));self.assertEqual(self.dynamic.read_bytes(),before)

    def test_owned_project_target_is_updated_atomically_with_its_dynamic_file(self):
        self.assertSuccess(self.install('project-launcher'))
        self.document['profiles']=['Проект A'];self.document['projects'].pop();self.write_config()
        self.assertSuccess(self.install('project-launcher'))
        rows=json.loads(self.dynamic.read_text())['Profiles']
        self.assertEqual(len(rows),1)
        self.assertEqual(len(rows[0]['Status Bar Layout']['components']),2)
        self.assertEqual(self.native['profiles'][0]['bar'],self.bar)


    def test_changed_target_selection_restores_only_original_owned_fields(self):
        self.native['profiles'].append(dict(guid='another',name='Project A',bar=copy.deepcopy(self.bar),working_directory=None,references=[]))
        self.assertSuccess(self.install('project-launcher'))
        self.document['profiles']=['Project A'];self.write_config()
        self.assertSuccess(self.install('project-launcher'))
        self.assertEqual(self.native['profiles'][0]['bar'],self.bar)
        self.assertTrue(self.native['profiles'][1]['bar']['Show Status Bar'])

    def test_foreign_config_and_duplicate_json_keys_are_not_adopted(self):
        self.config.write_text('{"profiles":["Default"],"profiles":["Default"],"projects":[]}')
        before=self.snapshot();result=self.install('project-launcher')
        self.assertTrue(any(f.state=='conflict' for f in result.findings));self.assertEqual(self.snapshot(),before)
        self.write_config()
        path=self.context.paths.config/'iterm2-utils-project-launcher.json';path.parent.mkdir()
        path.write_text(json.dumps(self.document));before=self.snapshot()
        result=self.install('project-launcher')
        self.assertTrue(any(f.state=='conflict' for f in result.findings));self.assertEqual(self.snapshot(),before)


    def test_unavailable_native_helper_has_no_partial_effect(self):
        before=self.snapshot()
        with patch.object(iterm,'inspect',side_effect=ValueError('PRIVATE')):
            result=self.install('project-launcher')
        self.assertTrue(any(f.state=='conflict' for f in result.findings));self.assertEqual(self.snapshot(),before)
        self.assertNotIn('PRIVATE',str(result))

    def test_cli_plan_install_update_and_doctor_hide_private_values(self):
        from iterm2_utils.cli import main
        commands=[['plan','--agent','codex','--features','project-launcher','--project-launcher-config',str(self.config)],
                  ['install','--agent','codex','--features','project-launcher','--project-launcher-config',str(self.config)],
                  ['update'],['doctor'],['uninstall','--features','project-launcher']]
        for command in commands:
            output=io.StringIO()
            with patch('iterm2_utils.cli.discover',side_effect=lambda *a,**kw:replace(self.context,project_launcher_config=None)), \
                 patch('iterm2_utils.cli.resolve_paths',return_value=self.context.paths), \
                 patch('iterm2_utils.cli.Runner',return_value=self.runner), redirect_stdout(output):
                code=main(command+['--json'])
            self.assertEqual(code,0,output.getvalue())
            self.assertNotIn(str(self.folder),output.getvalue());self.assertNotIn('Проект A',output.getvalue())
            if command[0]=='install': self.config.unlink()
        self.assertFalse(self.dynamic.exists())

    def test_unrelated_feature_has_no_native_helper_calls(self):
        self.context.project_launcher_config=None
        self.assertSuccess(self.install('shell'))
        self.assertEqual(self.calls,[])


    def test_builder_is_pure_and_fingerprint_tracks_native_targets(self):
        from iterm2_utils.features import project_launcher
        selection=self.selection('project-launcher')
        context=project_launcher.prepare(self.context,selection,self.runner)
        before=self.snapshot();self.calls.clear()
        one=plan(context,selection)
        context.project_launcher_snapshot=copy.deepcopy(context.project_launcher_snapshot)
        context.project_launcher_snapshot['profiles'][0]['guid']='different-parent'
        context.project_launcher_snapshot['default_guid']='different-parent'
        two=plan(context,selection)
        self.assertNotEqual(one.fingerprint,two.fingerprint)
        self.assertEqual(self.calls,[]);self.assertEqual(self.snapshot(),before)


class ProjectLauncherCliTests(unittest.TestCase):
    def test_flag_without_feature_rejected_before_discovery(self):
        from iterm2_utils.cli import main
        output=io.StringIO()
        with patch('iterm2_utils.cli.discover') as discovery, redirect_stdout(output):
            code=main(['plan','--agent','codex','--features','shell','--project-launcher-config','/unused.json','--json'])
        self.assertEqual(code,2);self.assertIn('project_launcher_config_selection',output.getvalue())
        discovery.assert_not_called()
