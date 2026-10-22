import unittest
from runtime.events import normalize
from runtime import notifier
UUID='11111111-2222-3333-4444-555555555555'
class NotifierTests(unittest.TestCase):
    def event(self,name,agent='codex',**kw):
        return normalize(dict(session_id='s',hook_event_name=name,**kw),agent,UUID)
    def test_codex_permission_request_never_sends_custom_banner(self):
        state,notice=notifier.transition({},self.event('PermissionRequest'))
        self.assertIsNone(notice)
    def test_codex_complete_waits_for_pending_subagent(self):
        state={}; notices=[]
        for name,extra in [('UserPromptSubmit',{}),('SubagentStart',{'agent_id':'a'}),('Stop',{}),('SubagentStop',{'agent_id':'a'}),('Stop',{})]:
            state,notice=notifier.transition(state,self.event(name,**extra));notices.append(notice)
        self.assertIsNone(notices[2]);self.assertEqual(notices[3].kind,'complete');self.assertIsNone(notices[4])
    def test_foreground_tab_suppresses_banner(self):
        from tests.support import FakeRunner
        from pathlib import Path
        notice=notifier.Notice('codex',UUID,'s','t','complete')
        for result in ['true','unknown','','false']:
            runner=FakeRunner();runner.responses['osascript']=result
            sent=notifier.deliver(notice,{'terminal_notifier':'/fake/notifier','it2':'/fake/it2','osascript':'/fake/osascript'},runner)
            self.assertEqual(sent,result=='false');self.assertEqual(len(runner.calls),2 if result=='false' else 1)
            self.assertLessEqual(max(c[1] for c in runner.calls),0.5)
    def test_focus_unknown_and_closed_tab_do_nothing(self):
        from runtime.focus import focus
        from pathlib import Path
        from tests.support import FakeRunner
        import subprocess
        runner=FakeRunner()
        self.assertFalse(focus('active',Path('/fake/it2'),runner));self.assertEqual(runner.calls,[])
        class Closed(FakeRunner):
            def run(self,argv,**kw):
                super().run(argv,**kw)
                return subprocess.CompletedProcess(argv,1,'','')
        runner=Closed();self.assertFalse(focus(UUID,Path('/fake/it2'),runner))
        self.assertEqual([c[0][1:3] for c in runner.calls],[['session','focus']])
    def test_notification_only_never_sets_status(self):
        from runtime import hook
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from tests.support import FakeRunner
        import json
        with TemporaryDirectory() as tmp:
            runner=FakeRunner();runner.responses['osascript']='false'
            settings={'notifications':True,'status':False,'notification_cache':tmp,'terminal_notifier':'/fake/notifier','it2':'/fake/it2','osascript':'/fake/osascript'}
            hook.dispatch(self.event('PreToolUse',tool_name='request_user_input',prompt='SECRET'),settings,runner)
            self.assertEqual(len(runner.calls),2)
            self.assertFalse(any('set-status' in c[0] for c in runner.calls))
            value=json.loads(next(Path(tmp).glob('*.json')).read_text())
            self.assertTrue(set(value).isdisjoint({'prompt','last_assistant_message','tool_input'}))
            self.assertNotIn('SECRET',str(value))
    def test_notifier_timeout_does_not_hang_hook(self):
        import subprocess
        from tests.support import FakeRunner
        class Timeout(FakeRunner):
            def run(self,argv,**kw):
                self.calls.append((argv,kw['timeout'],None))
                raise subprocess.TimeoutExpired(argv,kw['timeout'])
        runner=Timeout()
        self.assertFalse(notifier.deliver(notifier.Notice('codex',UUID,'s','t','input'),{'terminal_notifier':'/fake/n','it2':'/fake/it2','osascript':'/fake/osascript'},runner))
        self.assertLessEqual(runner.calls[0][1],0.5)
    def test_installed_notifications_without_checkout(self):
        from dataclasses import replace
        from pathlib import Path
        import json,shutil,subprocess,sys,time
        from iterm2_utils.discovery import discover,resolve_paths
        from iterm2_utils.features.shell import runtime_payload
        from iterm2_utils.models import Selection,FileEdit,SymlinkEdit
        from tests.support import Fixture
        with Fixture() as f:
            context=discover(resolve_paths(),f.runner)
            repo=f.home/'source';repo.mkdir()
            for tree in ('runtime','vendor'):
                shutil.copytree(context.paths.repo/tree,repo/tree,ignore=shutil.ignore_patterns('__pycache__'))
            context=replace(context,paths=replace(context.paths,repo=repo))
            payload=runtime_payload(context,Selection(frozenset({'codex'}),frozenset({'notifications'}),frozenset(),'Default'))
            for edit in payload.edits:
                edit.path.parent.mkdir(parents=True,exist_ok=True)
                if isinstance(edit,FileEdit):edit.path.write_bytes(edit.after)
                elif isinstance(edit,SymlinkEdit):edit.path.symlink_to(edit.after)
            shutil.rmtree(repo)
            marker=f.home/'banner';osascript=f.home/'osascript';sender=f.home/'sender';it2=f.home/'it2'
            osascript.write_text('#!'+sys.executable+'\nprint("false")\n');osascript.chmod(0o700)
            sender.write_text('#!'+sys.executable+'\nimport sys,json\nfrom pathlib import Path\ntarget=Path('+repr(str(marker))+');temp=target.with_suffix(".tmp");temp.write_text(json.dumps(sys.argv));temp.replace(target)\n');sender.chmod(0o700)
            settings=f.home/'runtime.json';settings.write_text(json.dumps({'notifications':True,'notification_cache':str(f.home/'cache'),'it2':str(it2),'terminal_notifier':str(sender),'osascript':str(osascript)}))
            cmd=[sys.executable,str(context.paths.data/'current/hook.py'),'--agent','codex','--settings',str(settings)]
            env={'HOME':str(f.home),'ITERM_SESSION_ID':UUID}
            for name in ['PreToolUse','PreToolUse']:
                result=subprocess.run(cmd,input=json.dumps({'hook_event_name':name,'session_id':'s','tool_name':'request_user_input','prompt':'SECRET'}),env=env,cwd=f.home,text=True,capture_output=True,timeout=3)
                self.assertEqual((result.returncode,result.stdout,result.stderr),(0,'{}\n',''))
            deadline=time.monotonic()+2
            while not marker.exists() and time.monotonic()<deadline:time.sleep(0.02)
            self.assertTrue(marker.exists())
            argv=json.loads(marker.read_text());self.assertIn(UUID,argv[argv.index('-execute')+1]);self.assertNotIn('SECRET',marker.read_text())
            self.assertTrue((f.home/'cache'/('codex-'+UUID+'.json')).exists())
    def test_distinct_concurrent_questions_and_duplicate_retransmission(self):
        state,_=notifier.transition({},self.event('UserPromptSubmit'))
        seen=[]
        for question in ['PRIVATE_ONE','PRIVATE_ONE','PRIVATE_TWO']:
            state,notice=notifier.transition(state,self.event('PreToolUse',tool_name='request_user_input',tool_input={'question':question}))
            if notice:seen.append(notice)
        self.assertEqual([n.kind for n in seen],['input','input'])
        self.assertNotIn('PRIVATE',str(state))
    def test_same_question_after_resolution_is_new_request(self):
        state,_=notifier.transition({},self.event('UserPromptSubmit'))
        for name in ['PreToolUse','PostToolUse','PreToolUse']:
            state,notice=notifier.transition(state,self.event(name,tool_name='request_user_input',tool_input={'question':'PRIVATE'}))
            self.assertEqual(notice.kind if notice else None,'input' if name=='PreToolUse' else None)
    def test_unmatched_tool_resolution_keeps_other_question_claims(self):
        state,_=notifier.transition({},self.event('UserPromptSubmit'))
        for question in ('one','two'):
            state,notice=notifier.transition(state,self.event('PreToolUse',tool_name='request_user_input',tool_input={'question':question}))
            self.assertIsNotNone(notice)
        state,_=notifier.transition(state,self.event('PostToolUse',tool_name='request_user_input',tool_input={'question':'unrelated'}))
        state,notice=notifier.transition(state,self.event('PreToolUse',tool_name='request_user_input',tool_input={'question':'one'}));self.assertIsNone(notice)
        state,_=notifier.transition(state,self.event('PostToolUse',tool_name='request_user_input',tool_input={'question':'one'}))
        state,notice=notifier.transition(state,self.event('PreToolUse',tool_name='request_user_input',tool_input={'question':'two'}));self.assertIsNone(notice)
        state,notice=notifier.transition(state,self.event('PreToolUse',tool_name='request_user_input',tool_input={'question':'one'}));self.assertEqual(notice.kind,'input')
