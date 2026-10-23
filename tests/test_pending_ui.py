import json
from tests.test_lifecycle import LifecycleFixture
from iterm2_utils import lifecycle

class PendingUiTests(LifecycleFixture):
    def test_native_ui_reconcile_claims_only_new_cc_status_hooks(self):
        p=self.context.paths.claude_settings;p.parent.mkdir()
        native=str(self.context.paths.home/'.config/iterm2/cc-status')
        old={'hooks':[{'type':'command','command':native+' start'}]}
        p.write_text(json.dumps({'hooks':{'Stop':[old]},'workgroup':'before'}))
        result=self.install('status',agents=('claude',))
        self.assertTrue(result.receipt.pending_ui)
        new={'hooks':[{'type':'command','command':native+' stop'}]}
        foreign={'hooks':[{'type':'command','command':'/other/cc-status stop'}]}
        p.write_text(json.dumps({'hooks':{'Stop':[old,new,foreign]},'workgroup':'after'}))
        result=lifecycle.reconcile_ui(self.context,'claude-native-status',self.runner)
        self.assertSuccess(result);self.assertFalse(result.receipt.pending_ui)
        owned=[r['locator']['entry'] for r in result.receipt.resources if r['kind']=='hook']
        self.assertEqual(owned,[new])
        self.assertNotIn(old,owned);self.assertNotIn(foreign,owned)
        lifecycle.uninstall(self.context,frozenset({'status'}),self.runner)
        data=json.loads(p.read_text());self.assertEqual(data['workgroup'],'after');self.assertEqual(data['hooks']['Stop'],[old,foreign])

    def test_failed_verification_remains_pending(self):
        self.install('status',agents=('claude',))
        result=lifecycle.reconcile_ui(self.context,'claude-native-status',self.runner)
        self.assertTrue(result.receipt.pending_ui)
        self.assertTrue(any(f.state=='pending_ui' for f in result.findings))

    def test_pending_repeat_update_preserves_original_snapshot(self):
        result=self.install('status',agents=('claude',))
        p=self.context.paths.claude_settings;p.parent.mkdir(exist_ok=True)
        entry={'hooks':[{'type':'command','command':str(self.context.paths.home/'.config/iterm2/cc-status')+' stop'}]}
        p.write_text(json.dumps({'hooks':{'Stop':[entry]}}))
        self.install('status',agents=('claude',))
        result=lifecycle.update(self.context,self.runner)
        self.assertEqual(result.receipt.ui_snapshots['claude-native-status'],[])
        self.assertTrue(result.receipt.pending_ui)
        result=lifecycle.reconcile_ui(self.context,'claude-native-status',self.runner)
        self.assertFalse(result.receipt.pending_ui)
        lifecycle.uninstall(self.context,frozenset({'status'}),self.runner)
        self.assertEqual(json.loads(p.read_text())['hooks']['Stop'],[])

    def test_duplicate_native_entries_remain_pending_without_claiming(self):
        self.install('status',agents=('claude',))
        p=self.context.paths.claude_settings;p.parent.mkdir(exist_ok=True)
        entry={'hooks':[{'type':'command','command':str(self.context.paths.home/'.config/iterm2/cc-status')+' stop'}]}
        p.write_text(json.dumps({'hooks':{'Stop':[entry,entry]}}));before=p.read_bytes()
        result=lifecycle.reconcile_ui(self.context,'claude-native-status',self.runner)
        self.assertTrue(result.receipt.pending_ui);self.assertEqual(p.read_bytes(),before)
        self.assertFalse(any(r['kind']=='hook' for r in result.receipt.resources))

    def test_mcp_timeout_is_unconfirmed_and_not_retried(self):
        from unittest.mock import patch
        import subprocess
        self.install('mcp')
        with patch.object(self.runner,'mcp_probe',create=True,side_effect=subprocess.TimeoutExpired('fake',1)) as probe:
            result=lifecycle.reconcile_ui(self.context,'mcp_authorize',self.runner)
        self.assertEqual(probe.call_count,1);self.assertTrue(result.receipt.pending_ui)

    def test_reconciled_native_update_does_not_reopen_ui_or_change_inverse(self):
        self.install('status',agents=('claude',))
        p=self.context.paths.claude_settings;p.parent.mkdir(exist_ok=True)
        entry={'hooks':[{'type':'command','command':str(self.context.paths.home/'.config/iterm2/cc-status')+' stop'}]}
        p.write_text(json.dumps({'hooks':{'Stop':[entry]}}))
        result=lifecycle.reconcile_ui(self.context,'claude-native-status',self.runner)
        owned=[r for r in result.receipt.resources if r['kind']=='hook']
        result=lifecycle.update(self.context,self.runner)
        self.assertFalse(result.receipt.pending_ui)
        self.assertEqual([r for r in result.receipt.resources if r['kind']=='hook'],owned)
