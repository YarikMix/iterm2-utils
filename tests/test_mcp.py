import json
import subprocess
import unittest
from pathlib import Path
from iterm2_utils.config import mcp
from iterm2_utils.features import mcp as feature
from iterm2_utils.models import Context, Selection, RegistrationEdit
from iterm2_utils.discovery import resolve_paths
from tests.support import Fixture


class CLI:
    def __init__(self):
        self.calls=[]
        self.value=None
        self.timeout=False
    def run(self, argv, *, timeout, stdin=None, env=None):
        self.calls.append(argv)
        if '--help' in argv:
            return subprocess.CompletedProcess(argv,0,'--json --transport --scope stdio user','')
        if 'get' in argv:
            return subprocess.CompletedProcess(argv,0,json.dumps(self.value),'')
        if 'add' in argv:
            self.value={'enabled':True,'transport':{'type':'stdio','command':'uvx','args':mcp.ARGS,'env':{}}}
            if self.timeout:
                raise subprocess.TimeoutExpired(argv,timeout)
        if 'remove' in argv:self.value=None
        return subprocess.CompletedProcess(argv,0,'','')
    def mcp_probe(self,argv,*,timeout,env=None):
        return {'tools':sorted(mcp.TOOLS),'sessions':True}


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.fixture=Fixture().__enter__()
        self.addCleanup(self.fixture.__exit__,None,None,None)
        self.context=Context(resolve_paths(),{'codex':Path('/fake/codex'),'claude':Path('/fake/claude'),'uvx':Path('/fake/uvx')},{},frozenset(),{}, {})
        self.cli=CLI()
    def build(self,features={'mcp'},agents={'codex'}):
        return feature.build(self.context,Selection(frozenset(agents),frozenset(features),frozenset(),'Default'))
    def test_pinned_server_argv(self):
        edit=self.build().edits[0]
        self.assertEqual(edit.after['command'],'uvx')
        self.assertEqual(edit.after['args'],['--with','mcp<2','mcp-server-iterm2==0.1.1'])
    def test_foreign_same_name_is_not_overwritten(self):
        self.cli.value={'enabled':True,'transport':{'type':'stdio','command':'foreign','args':[],'env':{'TOKEN':'secret'}}}
        with self.assertRaises(ValueError):mcp.apply(self.build().edits[0],self.context,self.cli)
        self.assertFalse(any('add' in a for a in self.cli.calls))
        self.assertNotIn('secret',repr(mcp.inspect('codex',mcp.NAME,self.context,self.cli)))
    def test_disabled_or_other_scope_server_is_a_conflict(self):
        self.cli.value={'enabled':False,'transport':{'type':'stdio','command':'uvx','args':mcp.ARGS,'env':{}}}
        with self.assertRaises(ValueError):mcp.apply(self.build().edits[0],self.context,self.cli)
    def test_claude_only_does_not_edit_codex(self):
        self.assertEqual([e.agent for e in self.build(agents={'claude'}).edits],['claude'])
    def test_installed_process_without_connection_is_not_ready(self):
        mcp.apply(self.build().edits[0],self.context,self.cli)
        self.cli.mcp_probe=lambda *a,**k: {'tools':['list_sessions'],'sessions':False}
        self.assertEqual(mcp.probe(self.context,self.cli,'codex').state,'unavailable')
    def test_timeout_after_add_is_reconciled_not_repeated(self):
        self.cli.timeout=True
        mcp.apply(self.build().edits[0],self.context,self.cli)
        self.assertEqual(sum('add' in a and '--help' not in a for a in self.cli.calls),1)
    def test_python_api_dependency_does_not_enable_mcp_for_status(self):
        self.assertEqual(self.build(features={'status'}).edits,[])
    def test_unknown_tool_is_incompatible(self):
        mcp.apply(self.build().edits[0],self.context,self.cli)
        self.cli.mcp_probe=lambda *a,**k: {'tools':['list_sessions','execute'],'sessions':True}
        self.assertEqual(mcp.probe(self.context,self.cli,'codex').state,'unavailable')

    def test_claude_known_labels_and_exact_argv(self):
        calls=[]
        registered=False
        def run(argv,**kwargs):
            nonlocal registered
            calls.append(argv)
            if '--help' in argv:return subprocess.CompletedProcess(argv,0,'--scope --transport','')
            if 'get' in argv:
                if not registered:return subprocess.CompletedProcess(argv,1,'','No MCP server found with name: iterm2-observe')
                return subprocess.CompletedProcess(argv,0,"iterm2-observe:\nScope: User config (available in all your projects)\nStatus: ✓ Connected\nType: stdio\nCommand: uvx\nArgs: --with mcp<2 mcp-server-iterm2==0.1.1\n",'')
            registered=True
            return subprocess.CompletedProcess(argv,0,'','')
        self.cli.run=run
        mcp.apply(self.build(agents={'claude'}).edits[0],self.context,self.cli)
        self.assertIn(['/fake/claude','mcp','add','--transport','stdio','--scope','user',mcp.NAME,'--','uvx',*mcp.ARGS],calls)
        self.assertFalse(any('--json' in a or a[0]=='/fake/codex' for a in calls))

    def test_claude_scope_env_disabled_and_unknown_formats_conflict(self):
        base="iterm2-observe:\nScope: User config (available in all your projects)\nStatus: ✓ Connected\nType: stdio\nCommand: uvx\nArgs: --with mcp<2 mcp-server-iterm2==0.1.1\n"
        variants=[base.replace('User config (available in all your projects)','Local config'),base+'Environment: TOKEN=secret\n',base.replace('✓ Connected','Disabled'),base+'Unknown: secret\n']
        for output in variants:
            self.assertEqual(mcp._claude(output,mcp.NAME),{'conflict':True})

    def test_arbitrary_failure_is_not_absence(self):
        self.cli.run=lambda argv,**kw:subprocess.CompletedProcess(argv,1,'','Authentication secret failure')
        with self.assertRaisesRegex(ValueError,'MCP inspection'):
            mcp.apply(self.build().edits[0],self.context,self.cli)

    def test_engine_receipt_and_inverse_context(self):
        from iterm2_utils import engine
        from iterm2_utils.models import Plan
        changes=self.build()
        self.assertFalse(changes.findings)
        selection=Selection(frozenset({'codex'}),frozenset({'mcp'}),frozenset(),'Default')
        outcome=engine.apply(Plan(selection,changes,'test'),self.context,self.cli)
        self.assertFalse(outcome.findings)
        self.assertEqual(len(outcome.receipt.resources),1)
        reverted=engine.revert(outcome.receipt,self.context,self.cli,frozenset({'mcp'}))
        self.assertFalse(reverted.findings)
        self.assertIsNone(self.cli.value)

    def test_probe_real_fake_protocol(self):
        import sys
        from iterm2_utils.commands import Runner
        script=self.fixture.home/'server.py'
        script.write_text("tools="+repr(sorted(mcp.TOOLS))+"\n"+"""import sys,json
for line in sys.stdin:
    request=json.loads(line)
    method=request['method']
    if method=='notifications/initialized':continue
    if method=='initialize':result={'protocolVersion':'2024-11-05','capabilities':{}}
    elif method=='tools/list':result={'tools':[{'name':name} for name in tools]}
    else:result={'content':[{'type':'text','text':'{"windows": [], "buried_sessions": []}'}]}
    print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)
""")
        self.assertEqual(Runner().mcp_probe([sys.executable,str(script)],timeout=2),{'tools':sorted(mcp.TOOLS),'sessions':True})

    def test_probe_process_without_protocol_times_out(self):
        import sys
        from iterm2_utils.commands import Runner
        self.assertEqual(Runner().mcp_probe([sys.executable,'-c','import time; time.sleep(20)'],timeout=.05),{'tools':[],'sessions':False})

    def test_custom_codex_home_child_environment(self):
        self.context.paths.codex_home=self.fixture.home/'isolated-codex'
        observed=[]
        original=self.cli.run
        def run(argv,**kwargs):
            observed.append({k:kwargs['env'][k] for k in ('HOME','CODEX_HOME')})
            return original(argv,**kwargs)
        self.cli.run=run
        mcp.apply(self.build().edits[0],self.context,self.cli)
        self.assertTrue(observed)
        self.assertTrue(all(e=={'HOME':str(self.fixture.home),'CODEX_HOME':str(self.context.paths.codex_home)} for e in observed))

    def test_claude_config_dir_mismatch_preserved(self):
        from unittest.mock import patch
        with patch.dict('os.environ',{'CLAUDE_CONFIG_DIR':str(self.fixture.home/'foreign')}):
            with self.assertRaisesRegex(ValueError,'differs'):
                mcp.inspect('claude',mcp.NAME,self.context,self.cli)
        self.assertEqual(self.cli.calls,[])

    def test_existing_exact_registration_is_reused_without_adoption(self):
        from iterm2_utils import engine
        from iterm2_utils.models import Plan
        self.cli.value={'enabled':True,'transport':{'type':'stdio','command':'uvx','args':mcp.ARGS,'env':{}}}
        selection=Selection(frozenset({'codex'}),frozenset({'mcp'}),frozenset(),'Default')
        outcome=engine.apply(Plan(selection,self.build(),'test'),self.context,self.cli)
        self.assertFalse(outcome.findings)
        self.assertEqual(outcome.receipt.resources,[])
        self.assertFalse(any('add' in a or 'remove' in a for a in self.cli.calls))

    def test_changed_registration_is_preserved_on_uninstall(self):
        from iterm2_utils import engine
        from iterm2_utils.models import Plan
        selection=Selection(frozenset({'codex'}),frozenset({'mcp'}),frozenset(),'Default')
        outcome=engine.apply(Plan(selection,self.build(),'test'),self.context,self.cli)
        self.cli.value['transport']['env']={'TOKEN':'private'}
        reverted=engine.revert(outcome.receipt,self.context,self.cli,frozenset({'mcp'}))
        self.assertTrue(reverted.findings)
        self.assertNotIn('private',repr(reverted))
        self.assertFalse(any('remove' in a for a in self.cli.calls))

    def test_timeout_unknown_does_not_repeat(self):
        def run(argv,**kwargs):
            self.cli.calls.append(argv)
            if '--help' in argv:return subprocess.CompletedProcess(argv,0,'--json','')
            if 'add' in argv:raise subprocess.TimeoutExpired(argv,5)
            return subprocess.CompletedProcess(argv,0,'null','')
        self.cli.run=run
        with self.assertRaisesRegex(ValueError,'outcome unknown'):
            mcp.apply(self.build().edits[0],self.context,self.cli)
        self.assertEqual(sum('add' in a and '--help' not in a for a in self.cli.calls),1)

    def test_ready_requires_exact_registration_and_protocol(self):
        self.assertEqual(mcp.probe(self.context,self.cli,'codex').state,'unavailable')
        mcp.apply(self.build().edits[0],self.context,self.cli)
        self.assertEqual(mcp.probe(self.context,self.cli,'codex').state,'ready')

    def test_probe_rejects_generic_error_payload_and_unknown_tools(self):
        import sys
        from iterm2_utils.commands import Runner
        script=self.fixture.home/'bad-server.py'
        for tools,content in [(sorted(mcp.TOOLS),'unavailable: denied'),(['execute'],'{}')]:
            script.write_text("import sys,json\nfor line in sys.stdin:\n r=json.loads(line)\n if 'id' not in r:continue\n m=r['method']\n v={'protocolVersion':'2024-11-05','capabilities':{}} if m=='initialize' else {'tools':[{'name':name} for name in "+repr(tools)+"]} if m=='tools/list' else {'content':[{'type':'text','text':"+repr(content)+"}]}\n print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':v}),flush=True)\n")
            result=Runner().mcp_probe([sys.executable,str(script)],timeout=1)
            self.assertFalse(result['sessions'])
            self.assertNotIn('denied',repr(result))

    def test_real_fake_cli_targets_only_custom_codex_home(self):
        import sys
        from iterm2_utils.commands import Runner
        script=self.fixture.home/'fake-codex'
        script.write_text('#!'+sys.executable+'\n'+'''import json,os,sys
from pathlib import Path
args=sys.argv[1:]
path=Path(os.environ['CODEX_HOME'])/'registration.json'
if '--help' in args:print('--json --scope --transport')
elif 'get' in args:print(path.read_text() if path.exists() else 'null')
elif 'add' in args:
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps({'enabled':True,'transport':{'type':'stdio','command':'uvx','args':['--with','mcp<2','mcp-server-iterm2==0.1.1'],'env':{}}}))
elif 'remove' in args:path.unlink()
''')
        script.chmod(0o755)
        self.context.executables['codex']=script
        self.context.paths.codex_home=self.fixture.home/'custom-target'
        mcp.apply(self.build().edits[0],self.context,Runner())
        self.assertTrue((self.context.paths.codex_home/'registration.json').exists())
        self.assertFalse((self.fixture.home/'.codex').exists())
        mcp.apply(RegistrationEdit('codex',mcp.NAME,mcp.definition(),None,'mcp'),self.context,Runner())
        self.assertFalse((self.context.paths.codex_home/'registration.json').exists())

    def test_adapter_rejects_incomplete_duplicate_or_unknown_inventory(self):
        mcp.apply(self.build().edits[0],self.context,self.cli)
        complete=sorted(mcp.TOOLS)
        self.assertEqual(len(complete),13)
        inventories=[['list_sessions'],complete[:-1],complete+[complete[0]],complete[:-1]+[complete[0]],complete+['execute']]
        for inventory in inventories:
            with self.subTest(inventory=inventory):
                self.cli.mcp_probe=lambda *a,**k: {'tools':inventory,'sessions':True}
                self.assertEqual(mcp.probe(self.context,self.cli,'codex').state,'unavailable')

    def test_protocol_rejects_invalid_inventory_before_sessions_call(self):
        import sys
        from iterm2_utils.commands import Runner
        complete=sorted(mcp.TOOLS)
        self.assertEqual(len(complete),13)
        script=self.fixture.home/'inventory-server.py'
        marker=self.fixture.home/'sessions-called'
        inventories=[['list_sessions'],complete[:-1],complete+[complete[0]],complete[:-1]+[complete[0]],complete+['execute']]
        for inventory in inventories:
            with self.subTest(inventory=inventory):
                marker.unlink(missing_ok=True)
                script.write_text('tools='+repr(inventory)+'\nmarker='+repr(str(marker))+'\n'+"""import sys,json
from pathlib import Path
for line in sys.stdin:
 request=json.loads(line)
 method=request['method']
 if method=='notifications/initialized':continue
 if method=='initialize':result={'protocolVersion':'2024-11-05','capabilities':{}}
 elif method=='tools/list':result={'tools':[{'name':name} for name in tools]}
 else:
  Path(marker).write_text('called')
  result={'content':[{'type':'text','text':'{"windows": [], "buried_sessions": []}'}]}
 print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)
""")
                result=Runner().mcp_probe([sys.executable,str(script)],timeout=2)
                self.assertFalse(result['sessions'])
                self.assertFalse(marker.exists())
