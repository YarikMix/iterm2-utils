"""Portable beta.1 evidence and single-writer migration regressions."""
import base64
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

from iterm2_utils import engine, lifecycle, state
from iterm2_utils.config import tomlfile
from runtime.events import normalize
from runtime.hook import dispatch
from tests.test_lifecycle import LifecycleFixture

FIXTURE = Path(__file__).parent/'fixtures/beta1-status.json'
FIXTURE_SHA256 = 'c7f8ac9159698f2c4b9277b6d101bc1eb95b193f83f6d9a47ed1b239139e1534'


class NativeMigrationTests(LifecycleFixture):
    def beta1(self):
        raw=FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),FIXTURE_SHA256)
        p=self.context.paths
        def expand(text):
            return text.replace('@HOME@',str(p.home.resolve())).replace('@SOURCE@',str(p.repo))
        fixture=json.loads(raw)
        self.assertEqual(fixture['source_commit'],'8c5643ed574f016bca46952ae6cd804d09195580')
        document=fixture['receipt']
        for resource in document['resources']:
            if resource['kind']=='file':
                for key in ('before','installed'):
                    if resource[key]['exists']:
                        value=base64.b64decode(resource[key]['value']).decode()
                        resource[key]['value']=base64.b64encode(expand(value).encode()).decode()
        receipt_path=p.data/'receipt.json';receipt_path.parent.mkdir(parents=True)
        receipt_path.write_text(expand(json.dumps(document)))
        receipt=state.load(receipt_path)
        state.validate(receipt)  # Validate real beta.1 ownership BEFORE installation.
        state.save(receipt_path,receipt)
        for name,item in fixture['files'].items():
            path=p.home/name;path.parent.mkdir(parents=True,exist_ok=True)
            if 'symlink' in item:path.symlink_to(expand(item['symlink']))
            else:path.write_text(expand(item['text']));path.chmod(item['mode'])
        for resource in receipt.resources:
            self.assertEqual(engine._read(resource,self.runner,self.context),resource['installed'])
        return receipt

    def live_snapshot(self):
        p=self.context.paths
        result={name:value for name,value in self.snapshot().items()
                if not name.startswith(('data/backups/','data/journal/','data/releases/','data/.','data/transaction.lock'))}
        current=p.data/'current'
        result['current-link']=os.readlink(current) if current.is_symlink() else None
        return result

    def settings(self):
        return json.loads((self.context.paths.config/'runtime.json').read_bytes())

    def test_beta1_update_is_native_and_preserves_selection(self):
        old=self.beta1()
        cache=self.context.paths.cache/'old-status.json';cache.parent.mkdir();cache.write_text('{"status":"working","session_id":"old"}')
        result=lifecycle.update(self.context,self.runner);self.assertSuccess(result)
        self.assertEqual(result.receipt.version,'1')
        self.assertEqual(result.receipt.selection,old.selection)
        settings=self.settings();self.assertEqual(settings['status_backend'],'cc-status')
        self.assertTrue(settings['status'])
        self.assertNotEqual(settings['native_identity_cache'],settings.get('cache'))
        self.assertFalse(Path(settings['native_identity_cache']).exists())
        self.assertEqual(json.loads(cache.read_bytes())['status'],'working')
        owned=[r for r in result.receipt.resources if r['kind']=='hook' and r['target']==str((self.context.paths.codex_home/'hooks.json').resolve()) and r['installed']['exists']]
        self.assertEqual(len(owned),12)
        hooks=json.loads((self.context.paths.codex_home/'hooks.json').read_bytes())['hooks']
        self.assertEqual(sum(len(entries) for entries in hooks.values()),12)

    def test_beta1_cas_conflict_preserves_previous_installation(self):
        self.beta1()
        for target in ('hook','settings'):
            with self.subTest(target=target):
                path=(self.context.paths.codex_home/'hooks.json' if target=='hook' else self.context.paths.config/'runtime.json')
                original=path.read_bytes();document=json.loads(original)
                if target=='hook':document['hooks']['Stop'][0]['hooks'][0]['command']+=' --foreign-edit'
                else:document['status']=False
                path.write_text(json.dumps(document));before=self.live_snapshot()
                result=lifecycle.update(self.context,self.runner)
                self.assertTrue(any(f.state=='conflict' for f in result.findings))
                self.assertEqual(self.live_snapshot(),before)
                path.write_bytes(original)

    def legacy(self):
        p=self.context.paths
        p.codex_home.mkdir(exist_ok=True)
        config=p.codex_home/'config.toml'
        config.write_text((config.read_text() if config.exists() else '')+'\n[plugins."iterm2-status@local"]\nenabled = true\n')
        return config

    def assert_legacy_collision(self):
        config=self.legacy();before=self.live_snapshot()
        receipt=state.load(self.context.paths.data/'receipt.json')
        findings=lifecycle.doctor(self.context,receipt,self.runner)
        backend=next(f for f in findings if f.code=='status_backend')
        self.assertEqual(backend.state,'conflict')
        for dry_run in (True,False):
            result=lifecycle.update(self.context,self.runner,dry_run=dry_run)
            self.assertTrue(any(f.code=='legacy_hook_conflict' and f.state=='conflict' for f in result.findings))
            self.assertEqual(self.live_snapshot(),before)
        self.assertTrue(self.settings()['status'])
        self.assertTrue(tomlfile.parse(config.read_bytes())['plugins']['iterm2-status@local']['enabled'])
        return config

    def test_legacy_collision_diagnostics_do_not_trust_corrupt_ownership(self):
        from iterm2_utils.planner import plan
        self.assertSuccess(self.install('status'));self.legacy()
        (self.context.paths.data/'receipt.json').write_text('{broken')
        before=self.live_snapshot()
        result=plan(lifecycle._context(self.context),self.selection('status'))
        self.assertTrue(any(f.code=='status_backend' and f.state=='conflict' for f in result.changes.findings))
        self.assertEqual(self.live_snapshot(),before)

    def test_external_legacy_after_owned_native_is_conflict_until_explicit_adoption(self):
        self.assertSuccess(self.install('status'))
        config=self.assert_legacy_collision()
        # Independent Claude native UI work can still complete.
        self.assertSuccess(self.install('status',agents=('claude',)))
        for feature,agent in (('notifications','codex'),('restore','codex'),('notifications','claude')):
            before=self.live_snapshot()
            result=self.install(feature,agents=(agent,))
            self.assertTrue(any(f.code=='legacy_hook_conflict' for f in result.findings))
            self.assertEqual(self.live_snapshot(),before)
        choice=self.selection('status');choice.adopt_legacy=True
        self.assertSuccess(lifecycle.install(self.context,choice,self.runner))
        self.assertFalse(tomlfile.parse(config.read_bytes())['plugins']['iterm2-status@local']['enabled'])
        self.assertTrue(self.settings()['status'])
        hooks=json.loads((self.context.paths.codex_home/'hooks.json').read_bytes())['hooks']
        self.assertEqual(sum(map(len,hooks.values())),12)

    def test_external_legacy_after_beta1_blocks_update_and_retained_status_recomposition(self):
        self.beta1();self.assert_legacy_collision();before=self.live_snapshot()
        result=lifecycle.uninstall(self.context,{'notifications'},self.runner,agents={'claude'})
        self.assertTrue(any(f.state=='conflict' for f in result.findings))
        self.assertEqual(self.live_snapshot(),before)
        choice=self.selection('status');choice.adopt_legacy=True
        self.assertSuccess(lifecycle.install(self.context,choice,self.runner))
        self.assertEqual(self.settings()['status_backend'],'cc-status')

    def test_external_legacy_allows_removing_owned_status_and_retaining_consumers(self):
        choice=self.selection('status','notifications','restore');choice.coexist_notifications=True
        self.assertSuccess(lifecycle.install(self.context,choice,self.runner))
        config=self.legacy();before=config.read_bytes()
        result=lifecycle.uninstall(self.context,{'status'},self.runner)
        self.assertSuccess(result)
        self.assertEqual(config.read_bytes(),before)
        self.assertFalse(self.settings()['status'])
        self.assertTrue(self.settings()['restore'])
        self.assertTrue(self.settings()['notifications'])

    def test_executing_nice_and_leading_redirection_block_install_without_mutation(self):
        import shlex
        import subprocess
        from iterm2_utils.discovery import native_codex_hook_state
        p=self.context.paths
        binary=self.context.executables['iterm2']/'Contents/Resources/utilities/cc-status'
        binary.parent.mkdir(parents=True)
        marker=p.home/'native-input'
        binary.write_text('#!/bin/sh\n/bin/cat > '+shlex.quote(str(marker))+'\n');binary.chmod(0o700)
        p.codex_home.mkdir()
        path=p.codex_home/'hooks.json'
        for prefix in ('/usr/bin/nice -n 5 ', '> /dev/null '):
            with self.subTest(prefix=prefix):
                command=prefix+shlex.join([str(binary),'--agent','codex'])
                subprocess.run(['/bin/sh','-c',command],input='{"synthetic":true}',text=True,check=True,
                               env={'HOME':str(p.home)},capture_output=True,timeout=2)
                self.assertEqual(marker.read_text(),'{"synthetic":true}')
                path.write_text(json.dumps({'hooks':{'UserPromptSubmit':[{'hooks':[{'type':'command','command':command}]}]}}))
                before=self.live_snapshot()
                self.assertEqual(native_codex_hook_state(p,self.context.executables['iterm2']),'conflict')
                result=self.install('status')
                self.assertTrue(any(f.state=='conflict' for f in result.findings))
                self.assertEqual(self.live_snapshot(),before)

    def test_adoption_write_failure_restores_legacy_writer(self):
        self.assertSuccess(self.install('shell'))
        config=self.legacy()
        hooks=self.context.paths.codex_home/'hooks.json'
        hooks.write_text(json.dumps({'hooks':{name:[] for name in ('PreToolUse','PermissionRequest','PostToolUse','PreCompact','PostCompact','SessionStart','SessionEnd','UserPromptSubmit','SubagentStart','SubagentStop','Stop','Interrupt')}} ,sort_keys=True,indent=2)+'\n')
        selection=self.selection('status');selection.adopt_legacy=True
        original=engine._write_file
        for target in (self.context.paths.config/'runtime.json',self.context.paths.codex_home/'hooks.json'):
            with self.subTest(target=target.name):
                before=self.live_snapshot();observed=[]
                def fail(path,*args,**kwargs):
                    if path==target.resolve() and not observed:
                        observed.append(tomlfile.parse(config.read_bytes())['plugins']['iterm2-status@local']['enabled'])
                        raise OSError('injected write failure')
                    return original(path,*args,**kwargs)
                with patch.object(engine,'_write_file',side_effect=fail):
                    result=lifecycle.install(self.context,selection,self.runner)
                self.assertTrue(any(f.state=='conflict' for f in result.findings))
                self.assertEqual(observed,[False])
                self.assertEqual(self.live_snapshot(),before)
                self.assertTrue(tomlfile.parse(config.read_bytes())['plugins']['iterm2-status@local']['enabled'])

    def test_uninstall_status_preserves_other_consumers(self):
        self.assertSuccess(self.install('status','notifications','restore'))
        self.assertSuccess(self.install('status','notifications',agents=('claude',)))
        result=lifecycle.uninstall(self.context,{'status'},self.runner,agents={'codex'})
        self.assertSuccess(result)
        self.assertEqual(result.receipt.selection.pairs,{'codex:notifications','codex:restore','claude:status','claude:notifications'})
        settings=self.settings();self.assertFalse(settings['status']);self.assertTrue(settings['restore'])
        self.assertEqual(settings['notification_agents'],['claude','codex'])
        event=normalize({'hook_event_name':'PreToolUse','session_id':'session'},'codex','00000000-0000-0000-0000-000000000001')
        with patch('runtime.native_status.forward',side_effect=AssertionError('unselected writer invoked')):
            dispatch(event,settings,self.runner)
        self.assertSuccess(self.install('status'))
        result=lifecycle.uninstall(self.context,{'notifications'},self.runner)
        self.assertSuccess(result);self.assertTrue(self.settings()['status']);self.assertFalse(self.settings()['notifications'])

    def test_external_native_reuse_survives_uninstall(self):
        native=self.external_native();p=self.context.paths;path=p.codex_home/'hooks.json'
        before=path.read_bytes()
        self.assertSuccess(self.install('status'))
        receipt=state.load(p.data/'receipt.json')
        self.assertFalse(self.settings()['status'])
        self.assertFalse(any(r['target']==str(path.resolve()) for r in receipt.resources))
        self.assertFalse(any(r['target'].startswith(str(self.context.executables['iterm2'])) for r in receipt.resources))
        self.assertSuccess(lifecycle.uninstall(self.context,{'status'},self.runner))
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(sum(map(len,json.loads(path.read_bytes())['hooks'].values())),10)
        for duplicate in (False,True):
            document={'hooks':dict(native)}
            document['hooks']['Stop']=native['Stop']*2 if duplicate else []
            path.write_text(json.dumps(document));before=self.live_snapshot()
            result=self.install('status')
            self.assertTrue(any(f.state=='conflict' for f in result.findings))
            self.assertEqual(self.live_snapshot(),before)

    def test_native_inventory_refresh_drops_stale_marker(self):
        self.context.installed['codex-native-status']={'conflict':True}
        result=self.install('status');self.assertSuccess(result)
        self.assertTrue(self.settings()['status'])

    def test_external_native_after_adoption_blocks_legacy_inverse(self):
        config=self.legacy();selection=self.selection('status','restore');selection.adopt_legacy=True
        self.assertSuccess(lifecycle.install(self.context,selection,self.runner))
        self.external_native();before=self.live_snapshot()
        for owners in ({'status'},{'status','restore'}):
            with self.subTest(owners=owners):
                result=lifecycle.uninstall(self.context,owners,self.runner)
                self.assertTrue(any(f.state=='conflict' for f in result.findings))
                self.assertEqual(self.live_snapshot(),before)
                self.assertFalse(tomlfile.parse(config.read_bytes())['plugins']['iterm2-status@local']['enabled'])

    def test_external_native_allows_removing_owned_writer_without_legacy_inverse(self):
        self.assertSuccess(self.install('status'))
        native=self.external_native()
        result=lifecycle.uninstall(self.context,{'status'},self.runner);self.assertSuccess(result)
        hooks=json.loads((self.context.paths.codex_home/'hooks.json').read_bytes())['hooks']
        self.assertEqual({event:entries for event,entries in hooks.items() if entries},native)

    def test_beta1_selective_uninstall_switches_retained_status_runtime_atomically(self):
        self.beta1()
        self.assertFalse((self.context.paths.data/'current/native_status.py').exists())
        result=lifecycle.uninstall(self.context,{'notifications'},self.runner,agents={'claude'})
        self.assertSuccess(result)
        self.assertEqual(self.settings()['status_backend'],'cc-status')
        self.assertTrue(self.settings()['status'])
        self.assertTrue((self.context.paths.data/'current/native_status.py').exists())
        self.assertIn('codex:status',result.receipt.selection.pairs)
        self.assertNotIn('claude:notifications',result.receipt.selection.pairs)

    def test_beta1_failed_native_switch_does_not_allow_later_consumer_switch(self):
        self.beta1();before=self.live_snapshot();original=engine._write_file
        def fail_settings(path,*args,**kwargs):
            if path==(self.context.paths.config/'runtime.json').resolve():
                raise OSError('injected beta.1 settings failure')
            return original(path,*args,**kwargs)
        with patch.object(engine,'_write_file',side_effect=fail_settings):
            result=lifecycle.update(self.context,self.runner)
        self.assertTrue(any(f.state=='conflict' for f in result.findings))
        self.assertEqual(self.live_snapshot(),before)

    def test_beta1_other_runtime_consumer_requires_status_update(self):
        self.beta1()
        for agent in ('codex','claude'):
            with self.subTest(agent=agent):
                before=self.live_snapshot()
                result=self.install('notifications',agents=(agent,))
                required=[f for f in result.findings if f.code=='status_migration_required']
                self.assertEqual(len(required),1)
                self.assertEqual(required[0].state,'conflict')
                self.assertIn('update',required[0].message)
                self.assertEqual(self.live_snapshot(),before)
        result=lifecycle.update(self.context,self.runner);self.assertSuccess(result)
        checkpoints=[f.feature for f in result.findings if f.code=='feature_checkpoint']
        self.assertEqual(checkpoints[0],'status')
        for feature in ('shell','notifications','restore','shortcuts'):
            self.assertIn(feature,checkpoints)

    def test_beta1_profile_mcp_and_claude_status_remain_independent(self):
        self.beta1()
        current=os.readlink(self.context.paths.data/'current')
        settings=(self.context.paths.config/'runtime.json').read_bytes()
        self.assertSuccess(self.install('shortcuts',shortcuts=('ctrl-q',)))
        self.assertSuccess(self.install('mcp'))
        result=self.install('status',agents=('claude',));self.assertSuccess(result)
        self.assertIn('claude:status',result.receipt.selection.pairs)
        self.assertTrue(any(s.code=='claude-native-status' for s in result.receipt.pending_ui))
        self.assertEqual(os.readlink(self.context.paths.data/'current'),current)
        self.assertEqual((self.context.paths.config/'runtime.json').read_bytes(),settings)

    def test_beta1_update_dry_run_previews_all_consumers_without_mutation(self):
        self.beta1();before=self.live_snapshot()
        result=lifecycle.update(self.context,self.runner,dry_run=True)
        self.assertSuccess(result)
        self.assertEqual(self.live_snapshot(),before)
