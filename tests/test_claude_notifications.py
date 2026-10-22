import unittest
from runtime.events import normalize
from tests.test_notifier import UUID
from runtime import notifier
class ClaudeTests(unittest.TestCase):
    def event(self,name,agent="claude",**kw):
        return normalize(dict(session_id="s",hook_event_name=name,**kw),agent,UUID)
    def test_claude_stop_once_per_prompt(self):
        state={};seen=[]
        for name in ['UserPromptSubmit','Stop','Stop','UserPromptSubmit','Stop']:
            state,notice=notifier.transition(state,self.event(name,'claude'));seen.extend([notice] if notice else [])
        self.assertEqual([n.kind for n in seen],['complete','complete'])
    def test_claude_interrupt_session_end_and_stop_failure_do_not_complete(self):
        for end in ['Interrupt','SessionEnd','StopFailure','SubagentStop']:
            state,_=notifier.transition({},self.event('UserPromptSubmit','claude'))
            state,notice=notifier.transition(state,self.event(end,'claude'))
            self.assertIsNone(notice)
    def test_claude_background_and_prompt_identity(self):
        state={}
        for name,kw in [('UserPromptSubmit',{'prompt_id':'a'}),('Stop',{'prompt_id':'old'}),('Stop',{'prompt_id':'a','background_tasks':[{'status':'running'}]}),('SubagentStop',{})]:
            state,notice=notifier.transition(state,self.event(name,'claude',**kw));self.assertIsNone(notice)
        state,notice=notifier.transition(state,self.event('Stop','claude',prompt_id='a'));self.assertEqual(notice.kind,'complete')
    def test_claude_permission_notification_is_not_permission_decision(self):
        state,notice=notifier.transition({},self.event('Notification','claude',notification_type='permission_prompt',prompt='SECRET',tool_input={'x':'SECRET'}))
        self.assertEqual(notice.kind,'attention');self.assertNotIn('SECRET',str(state))

    def test_background_tasks_unknown_status_and_shape_suppress_completion(self):
        for tasks in ([{'id':'x','status':'future-status','description':'SECRET','command':'SECRET'}], {'unknown':'SECRET'}, 'UNKNOWN'):
            state,_=notifier.transition({},self.event('UserPromptSubmit'))
            state,notice=notifier.transition(state,self.event('Stop',background_tasks=tasks))
            self.assertIsNone(notice);self.assertNotIn('SECRET',str(state))
            state,notice=notifier.transition(state,self.event('Stop',background_tasks=[]))
            self.assertEqual(notice.kind,'complete')
    def test_stop_hook_active_cannot_complete(self):
        state,_=notifier.transition({},self.event('UserPromptSubmit'))
        state,notice=notifier.transition(state,self.event('Stop',stop_hook_active=True))
        self.assertIsNone(notice)
        state,notice=notifier.transition(state,self.event('Stop'))
        self.assertEqual(notice.kind,'complete')
    def test_distinct_permissions_and_duplicate_retransmission(self):
        state,_=notifier.transition({},self.event('UserPromptSubmit'))
        seen=[]
        for message in ['PRIVATE_ONE','PRIVATE_ONE','PRIVATE_TWO']:
            state,notice=notifier.transition(state,self.event('Notification',notification_type='permission_prompt',title='Permission',message=message))
            if notice:seen.append(notice)
        self.assertEqual([n.kind for n in seen],['attention','attention'])
        self.assertNotIn('PRIVATE',str(state))
    def test_same_permission_after_resolution_is_new_request(self):
        for boundary in ('PostToolUse','PostToolUseFailure'):
            state,_=notifier.transition({},self.event('UserPromptSubmit'))
            seen=[]
            for name in ['Notification','Notification',boundary,'Notification','Notification']:
                state,notice=notifier.transition(state,self.event(name,notification_type='permission_prompt',title='Permission',message='PRIVATE'))
                if notice:seen.append(notice.kind)
            self.assertEqual(seen,['attention','attention'])
            self.assertNotIn('PRIVATE',str(state))
    def test_resolution_does_not_reset_completion(self):
        state,_=notifier.transition({},self.event('UserPromptSubmit'))
        state,notice=notifier.transition(state,self.event('Stop'));self.assertEqual(notice.kind,'complete')
        for name in ('PostToolUse','PostToolUseFailure','Stop'):
            state,notice=notifier.transition(state,self.event(name));self.assertIsNone(notice)
