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
from tests.support import FakeRunner

UUID='11111111-2222-3333-4444-555555555555'
class RuntimeTests(unittest.TestCase):
    def event(self,name,**extra):
        return events.normalize(dict(session_id='s',hook_event_name=name,**extra),'codex',UUID)
    def test_wrong_uuid_is_noop(self):
        for terminal in ('active','all','',UUID+';bad'):
            self.assertIsNone(events.normalize({'session_id':'s','hook_event_name':'Stop'},'codex',terminal))
        runner=FakeRunner()
        hook.dispatch(events.Event('codex','Stop','s','active',None,None,None,False),{'status':True},runner)
        self.assertEqual(runner.calls,[])
    def test_late_stop_does_not_idle_new_turn(self):
        with TemporaryDirectory() as tmp:
            runner=FakeRunner(); settings={'status':True,'cache':tmp,'it2':'/fake/it2'}
            for name,turn in [('UserPromptSubmit','one'),('UserPromptSubmit','two'),('Stop','one')]:
                hook.dispatch(self.event(name,turn_id=turn),settings,runner)
            self.assertEqual(len(runner.calls),2)
            self.assertEqual(runner.calls[-1][0][runner.calls[-1][0].index('--status')+1],'working')
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
    def test_private_payload_does_not_enter_cache_and_approval_pairs(self):
        with TemporaryDirectory() as tmp:
            runner=FakeRunner();settings={'status':True,'cache':tmp,'it2':'/fake/it2'}
            for name,tool in [('UserPromptSubmit',{}),('PermissionRequest',{'command':'SECRET_COMMAND','description':'SECRET_DESCRIPTION'}),('PostToolUse',{'command':'SECRET_COMMAND'})]:
                hook.dispatch(self.event(name,tool_name='Bash',tool_input=tool,prompt='SECRET_PROMPT',transcript_path='/SECRET_PATH'),settings,runner)
            state=(Path(tmp)/(UUID+'.json')).read_text()
            for secret in ('SECRET_COMMAND','SECRET_DESCRIPTION','SECRET_PROMPT','SECRET_PATH'):
                self.assertNotIn(secret,state)
            self.assertEqual(json.loads(state)['status'],'working')
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
            fake=f.home/'fake-it2'
            fake.write_text('#!'+sys.executable+'\nimport sys\nfrom pathlib import Path\nPath('+repr(str(f.home/'called'))+').write_text(repr(sys.argv))\n')
            fake.chmod(0o700)
            settings=f.home/'runtime.json';settings.write_text(json.dumps({'status':True,'cache':str(f.home/'cache'),'it2':str(fake)}))
            env={'HOME':str(f.home),'ITERM_SESSION_ID':'w0t0p0:'+UUID}
            result=subprocess.run([sys.executable,str(context.paths.data/'current/hook.py'),'--agent','codex','--settings',str(settings)],input=json.dumps({'hook_event_name':'UserPromptSubmit','session_id':'s'}),text=True,capture_output=True,env=env,cwd=f.home,timeout=3)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(0,'{}\n',''))
            self.assertIn(UUID,(f.home/'called').read_text())
    def test_timeout_and_failures_process_budget(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);fake=root/'it2';cache=root/'cache'
            settings=root/'runtime.json';settings.write_text(json.dumps({'status':True,'cache':str(cache),'it2':str(fake)}))
            command=[sys.executable,'-m','runtime.hook','--settings',str(settings)]
            for script in ('raise RuntimeError()','import time;time.sleep(9)'):
                fake.write_text('#!'+sys.executable+'\n'+script+'\n');fake.chmod(0o700)
                start=time.monotonic()
                result=subprocess.run(command,input=json.dumps({'session_id':'s','hook_event_name':'UserPromptSubmit'}),env={'ITERM_SESSION_ID':UUID},text=True,capture_output=True,timeout=3)
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
