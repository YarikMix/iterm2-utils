import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
from runtime import events, hook
from tests.support import FakeRunner, Fixture

UUID='11111111-2222-3333-4444-555555555555'
class RuntimeTests(unittest.TestCase):
    def event(self,name,**extra):
        return events.normalize(dict(session_id='s',hook_event_name=name,**extra),'codex',UUID)
    def test_codex_events_match_released_schema(self):
        self.assertEqual(set(events.CODEX_EVENTS), {
            'SessionStart', 'SessionEnd', 'UserPromptSubmit', 'PreToolUse',
            'PermissionRequest', 'PostToolUse', 'PreCompact', 'PostCompact',
            'SubagentStart', 'SubagentStop', 'Stop', 'Interrupt'})
        self.assertEqual(len(events.CODEX_EVENTS), 12)
        self.assertIs(events.EVENTS, events.CODEX_EVENTS)
        for name in events.CODEX_EVENTS:
            with self.subTest(name=name):
                self.assertIsNotNone(self.event(name))
        for name in ('Notification', 'StopFailure', 'PostToolUseFailure'):
            self.assertIsNotNone(events.normalize(
                {'session_id': 's', 'hook_event_name': name}, 'claude', UUID))

    def test_terminal_environment_validates_all_present_sources(self):
        other = 'AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'
        lower = other.lower()
        cases = [
            ({'TERM_SESSION_ID': 'w0t0p0:'+UUID}, UUID),
            ({'ITERM_SESSION_ID': UUID}, UUID),
            ({'ITERM_SESSION_ID': lower}, other),
            ({'TERM_SESSION_ID': 'w12t3p4:'+lower}, other),
            ({'ITERM_SESSION_ID': UUID, 'TERM_SESSION_ID': 'w0t0p0:'+UUID}, UUID),
            ({'ITERM_SESSION_ID': 'w1t2p3:'+lower, 'TERM_SESSION_ID': other}, other),
            ({'ITERM_SESSION_ID': UUID, 'TERM_SESSION_ID': 'w0t0p0:'+other}, None),
            ({'ITERM_SESSION_ID': 'bad', 'TERM_SESSION_ID': UUID}, None),
            ({'ITERM_SESSION_ID': UUID, 'TERM_SESSION_ID': 'bad'}, None),
            ({'ITERM_SESSION_ID': '', 'TERM_SESSION_ID': UUID}, None),
            ({'ITERM_SESSION_ID': UUID, 'TERM_SESSION_ID': ''}, None),
            ({'TERM_SESSION_ID': UUID+';touch bad'}, None),
            ({'TERM_SESSION_ID': '$(bad):'+UUID}, None),
            ({}, None),
        ]
        for environment, expected in cases:
            with self.subTest(environment=environment):
                self.assertEqual(events.terminal_from_environment(environment), expected)

    def test_payload_terminal_uuid_must_match_environment(self):
        raw = {'session_id': 's', 'hook_event_name': 'Stop',
               'terminal_uuid': 'AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'}
        self.assertIsNone(events.normalize(raw, 'codex', UUID))

    def test_wrong_uuid_is_noop(self):
        for terminal in ('active','all','',UUID+';bad'):
            self.assertIsNone(events.normalize({'session_id':'s','hook_event_name':'Stop'},'codex',terminal))
        runner=FakeRunner()
        hook.dispatch(events.Event('codex','Stop','s','active',None,None,None,False),{'status':True},runner)
        self.assertEqual(runner.calls,[])
    def test_late_stop_does_not_idle_new_turn(self):
        with Fixture() as f:
            runner=FakeRunner()
            settings={'status':True,'status_backend':'cc-status','iterm2_app':str(f.app),
                      'native_identity_cache':str(f.home/'identity')}
            for name,turn in [('UserPromptSubmit','one'),('UserPromptSubmit','two'),('Stop','one')]:
                hook.dispatch(self.event(name,turn_id=turn),settings,runner,
                              environment={'TERM_SESSION_ID':UUID})
            self.assertEqual(len(runner.calls),2)
            self.assertEqual(json.loads(runner.calls[-1][2])['hook_event_name'],'UserPromptSubmit')
    def test_notifications_only_does_not_call_set_status(self):
        runner=FakeRunner()
        hook.dispatch(self.event('Stop'),{'status':False,'notifications':True,'restore':False},runner)
        self.assertEqual(runner.calls,[])
    def test_all_hook_failures_return_empty_json_zero(self):
        for payload in ('bad','null','[]','{}'):
            out=io.StringIO(); start=time.monotonic()
            with patch('sys.stdin',io.StringIO(payload)),contextlib.redirect_stdout(out):
                self.assertEqual(hook.main([]),0)
            self.assertEqual(out.getvalue(),'{}\n');self.assertLess(time.monotonic()-start,3)
    def test_private_payload_does_not_enter_identity_cache(self):
        with Fixture() as f:
            runner=FakeRunner()
            settings={'status':True,'status_backend':'cc-status','iterm2_app':str(f.app),
                      'native_identity_cache':str(f.home/'identity')}
            for name,tool in [('UserPromptSubmit',{}),('PermissionRequest',{'command':'SECRET_COMMAND','description':'SECRET_DESCRIPTION'}),('PostToolUse',{'command':'SECRET_COMMAND'})]:
                raw=dict(session_id='s',hook_event_name=name,tool_name='Bash',tool_input=tool,
                         prompt='SECRET_PROMPT',transcript_path='/SECRET_PATH')
                hook.dispatch(events.normalize(raw,'codex',UUID),settings,runner,
                              raw_event=raw,environment={'ITERM_SESSION_ID':UUID})
            state=(f.home/'identity'/(UUID+'.json')).read_text()
            for secret in ('SECRET_COMMAND','SECRET_DESCRIPTION','SECRET_PROMPT','SECRET_PATH'):
                self.assertNotIn(secret,state)
            self.assertEqual(json.loads(state),{'session_id':'s','turn_id':None,'ended':False})
            self.assertEqual(len(runner.calls),3)
    def test_installed_process_after_checkout_copy_removed(self):
        from dataclasses import replace
        import shutil
        from iterm2_utils.discovery import discover,resolve_paths
        from iterm2_utils.features.shell import runtime_payload
        from iterm2_utils.models import Selection,FileEdit,SymlinkEdit
        from tests.support import Fixture
        with Fixture() as f:
            context=discover(resolve_paths(),f.runner)
            repo=f.home/'source';repo.mkdir()
            for tree in ('runtime','vendor'):
                shutil.copytree(context.paths.repo/tree,repo/tree,ignore=shutil.ignore_patterns('__pycache__'))
            for name in ('LICENSE','THIRD_PARTY_NOTICES.md'):
                shutil.copy2(context.paths.repo/name,repo/name)
            context=replace(context,paths=replace(context.paths,repo=repo))
            payload=runtime_payload(context,Selection(frozenset({'codex'}),frozenset({'status'}),frozenset(),'Default'))
            for edit in payload.edits:
                edit.path.parent.mkdir(parents=True,exist_ok=True)
                if isinstance(edit,FileEdit):edit.path.write_bytes(edit.after)
                elif isinstance(edit,SymlinkEdit):edit.path.symlink_to(edit.after)
            shutil.rmtree(repo)
            fake=f.app/'Contents/Resources/utilities/cc-status'
            fake.write_text('#!'+sys.executable+'\nimport os,sys,json\nfrom pathlib import Path\nPath('+repr(str(f.home/'called'))+').write_text(json.dumps([sys.argv,os.environ["TERM_SESSION_ID"],json.load(sys.stdin)]))\n')
            fake.chmod(0o700)
            settings=f.home/'runtime.json';settings.write_text(json.dumps({'status':True,'status_backend':'cc-status','iterm2_app':str(f.app),'native_identity_cache':str(f.home/'identity'),'cache':str(f.home/'cache')}))
            env={'HOME':str(f.home),'ITERM_SESSION_ID':'w0t0p0:'+UUID}
            result=subprocess.run([sys.executable,str(context.paths.data/'current/hook.py'),'--agent','codex','--settings',str(settings)],input=json.dumps({'hook_event_name':'UserPromptSubmit','session_id':'s'}),text=True,capture_output=True,env=env,cwd=f.home,timeout=3)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(0,'{}\n',''))
            called=json.loads((f.home/'called').read_text())
            self.assertEqual(called[0],[str(fake),'--agent','codex'])
            self.assertEqual(called[1],'w0t0p0:'+UUID)
            self.assertEqual(called[2],{'hook_event_name':'UserPromptSubmit'})
            self.assertFalse((f.home/'cache').exists())
    def test_timeout_and_failures_process_budget(self):
        with Fixture() as f:
            fake=f.app/'Contents/Resources/utilities/cc-status'
            settings=f.home/'runtime.json'
            settings.write_text(json.dumps({'status':True,'status_backend':'cc-status',
                                           'iterm2_app':str(f.app),'native_identity_cache':str(f.home/'identity')}))
            command=[sys.executable,'-m','runtime.hook','--settings',str(settings)]
            for script in ('raise RuntimeError()','import time;time.sleep(9)'):
                fake.write_text('#!'+sys.executable+'\n'+script+'\n');fake.chmod(0o700)
                start=time.monotonic()
                result=subprocess.run(command,input=json.dumps({'session_id':'s','hook_event_name':'UserPromptSubmit'}),env={'ITERM_SESSION_ID':UUID,'HOME':str(f.home)},text=True,capture_output=True,timeout=3)
                self.assertEqual((result.returncode,result.stdout,result.stderr),(0,'{}\n',''))
                self.assertLess(time.monotonic()-start,3)
    def test_missing_vendor_is_still_empty_json_zero(self):
        import shutil
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('hook.py','events.py'):
                shutil.copy(Path(hook.__file__).parent/name,root/name)
            settings=root/'settings.json';settings.write_text('{"status": true}')
            result=subprocess.run([sys.executable,str(root/'hook.py'),'--settings',str(settings)],input='{}',capture_output=True,text=True,env={},timeout=3)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(0,'{}\n',''))
    def test_overall_budget_bypasses_combined_handler_isolation(self):
        import shutil
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('hook.py','events.py'):
                shutil.copy(Path(hook.__file__).parent/name,root/name)
            shutil.copytree(Path(hook.__file__).resolve().parents[1]/'vendor',root/'vendor',ignore=shutil.ignore_patterns('__pycache__'))
            restore=root/'codex_restore';restore.mkdir()
            settings=root/'settings.json'
            settings.write_text(json.dumps({'notifications':True,'restore':True,'status':False}))
            # Expiry in either handler must escape local ordinary-error isolation.
            for notification_delay,restore_delay in ((9,0.6),(0.6,9)):
                with self.subTest(notification_delay=notification_delay):
                    (root/'notifier.py').write_text('import time\ndef handle(*args):\n    time.sleep('+str(notification_delay)+')\n')
                    (restore/'registry.py').write_text('import time\ndef handle(*args):\n    time.sleep('+str(restore_delay)+')\n')
                    start=time.monotonic()
                    result=subprocess.run([sys.executable,str(root/'hook.py'),'--settings',str(settings)],input=json.dumps({'session_id':'s','hook_event_name':'Stop'}),env={'ITERM_SESSION_ID':UUID},capture_output=True,text=True,cwd=root,timeout=4)
                    elapsed=time.monotonic()-start
                    self.assertEqual((result.returncode,result.stdout,result.stderr),(0,'{}\n',''))
                    self.assertLess(elapsed,3)
    def test_claude_attention_cache_keeps_only_opaque_identity(self):
        with TemporaryDirectory() as tmp:
            runner=FakeRunner();runner.responses['osascript']='false'
            settings={'notifications':True,'status':False,'notification_cache':tmp,'terminal_notifier':'/fake/notifier','it2':'/fake/it2','osascript':'/fake/osascript'}
            for name,message in [('Notification','PRIVATE_ONE'),('Notification','PRIVATE_ONE'),('Notification','PRIVATE_TWO')]:
                event=events.normalize(dict(session_id='s',hook_event_name=name,notification_type='permission_prompt',title='PRIVATE_TITLE',message=message,prompt='PRIVATE_PROMPT',tool_input={'command':'PRIVATE_COMMAND'}),'claude',UUID)
                hook.dispatch(event,settings,runner)
            state=next(Path(tmp).glob('*.json')).read_text()
            self.assertNotIn('PRIVATE',state)
            self.assertTrue(set(json.loads(state)).isdisjoint({'title','message','prompt','tool_input'}))
            self.assertEqual(len(runner.calls),4)
            self.assertFalse(any('set-status' in c[0] for c in runner.calls))
