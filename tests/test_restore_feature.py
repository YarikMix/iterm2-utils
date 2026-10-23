"""Portable restore integration; all installs and terminal calls are fixtures."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from iterm2_utils.discovery import discover, resolve_paths
from iterm2_utils.models import Selection, FileEdit, SymlinkEdit
from iterm2_utils.features import shell
from tests.support import Fixture

class RestoreFeatureTests(unittest.TestCase):
    def hook_environment(self, fixture, hook):
        # A synthetic panel must not inherit the developer's terminal/tmux address.
        environment={**fixture.environ,'HOME':str(fixture.root),'PYTHONPATH':str(hook.parent.parent)}
        environment['TERM_SESSION_ID']=environment['ITERM_SESSION_ID']
        for key in ('TMUX','TMUX_PANE'):
            environment.pop(key,None)
        return environment

    def context(self, fixture):
        context=discover(resolve_paths(),fixture.runner)
        return replace(context,executables={**context.executables,'fzf':fixture.bin/'fzf','python3':Path(sys.executable)},versions={**context.versions,'fzf':'0.60.0'})

    def test_installed_restore_survives_checkout_move(self):
        from iterm2_utils.features import restore
        with Fixture() as f:
            context=self.context(f)
            selection=Selection(frozenset({'codex'}),frozenset({'restore'}),frozenset(),'Default')
            self.assertFalse(restore.build(context,selection).findings)
            for edit in shell.runtime_payload(context,selection).edits:
                edit.path.parent.mkdir(parents=True,exist_ok=True)
                if isinstance(edit,FileEdit):
                    edit.path.write_bytes(edit.after);edit.path.chmod(edit.mode)
                elif isinstance(edit,SymlinkEdit):edit.path.symlink_to(edit.after)
            entry=context.paths.data/'current/codex_restore/codex-sessions'
            relocated=f.home/'relocated';shutil.copytree(entry.parent,relocated)
            shutil.rmtree(context.paths.data)
            result=subprocess.run([sys.executable,str(relocated/'codex-sessions'),'--help'],capture_output=True,text=True,cwd=f.home)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('restore-list',result.stdout)
            self.assertTrue((relocated/'codex-sessions').stat().st_mode & 0o100)

    def test_claude_only_restore_is_unavailable(self):
        from iterm2_utils.features import restore
        with Fixture() as f:
            changes=restore.build(self.context(f),Selection(frozenset({'claude'}),frozenset({'restore'}),frozenset(),'Default'))
            self.assertFalse(changes.edits)
            self.assertEqual(changes.findings[0].state,'unavailable')

    def test_restore_requires_modern_fzf(self):
        from iterm2_utils.features import restore
        with Fixture() as f:
            c=self.context(f);c=replace(c,versions={**c.versions,'fzf':'0.59.0'})
            self.assertEqual(restore.build(c,Selection(frozenset({'codex'}),frozenset({'restore'}),frozenset(),'Default')).findings[0].state,'missing_dependency')

    def test_unknown_new_tab_outcome_is_not_retried(self):
        from tests.restore.test_restore import RestoreTests, TERM
        from codexlib import restore, store
        from codexlib.iterm import ITerm
        from tests.restore.helpers import TerminalTools
        import contextlib,io,os
        fixture=RestoreTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        tools=TerminalTools(fixture.root)
        tools.set_inventory([{'id':TERM,'tab_id':'T1','window_id':'W1'}],[{'id':'T1','index':0,'window_id':'W1'}],[{'id':'W1'}])
        tools.it2.write_text(tools.it2.read_text().replace('print("Created new tab: T-new")','print("unrecognized response")'))
        client=ITerm(str(tools.it2),str(tools.ps));client.launch_id=lambda:'new-launch'
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            restore.prepare(fixture.paths,client,[s.session_id for s in fixture.sessions[:2]],TERM,101)
            restore.prepare(fixture.paths,client,[s.session_id for s in fixture.sessions[:2]],TERM,102)
        new_tab_calls_after_uncertain_result=sum(row[1:3]==['tab','new'] for row in tools.calls())
        self.assertEqual(new_tab_calls_after_uncertain_result,1)
        self.assertIn('Проверьте',errors.getvalue())

    def test_other_codex_home_is_preserved(self):
        from iterm2_utils.features import status
        with Fixture() as f:
            c=self.context(f); other=f.home/'other-codex'
            c=replace(c,paths=replace(c.paths,codex_home=other))
            selection=Selection(frozenset({'codex'}),frozenset({'restore'}),frozenset(),'Default')
            edits=status.build(c,selection).edits
            settings=json.loads(next(e.after for e in edits if e.path.name=='runtime.json'))
            self.assertEqual(settings['restore_codex_home'],str(other))
            text=shell.build(c,selection).edits[0].after.decode()
            self.assertIn('[[ -n ${CODEX_HOME+x} ]]',text)
            self.assertIn(str(other),text)

    def test_restore_only_uses_no_daemon_without_status(self):
        with Fixture() as f:
            c=self.context(f)
            binary=f.bin/'codex';capture=f.home/'argv'
            binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "'+str(capture)+'"\n');binary.chmod(0o700)
            selection=Selection(frozenset({'codex'}),frozenset({'restore'}),frozenset(),'Default')
            # Source actual shared + restore dispatcher twice, without user startup.
            script='source "$1"; source "$2"; source "$1"; source "$2"; codex hello; codex resume --all; codex agents; codex -m resume exec task'
            environment={'HOME':str(f.home),'PATH':str(f.bin)+':/usr/bin:/bin','ITERM2_UTILS_CODEX_NO_DAEMON':'1','_codex_restore_no_daemon':'1','CODEX_RESTORE_NO_AUTO':'1'}
            result=subprocess.run(['/bin/zsh','-f','-c',script,'test',str(c.paths.repo/'runtime/codex.zsh'),str(c.paths.repo/'runtime/codex_restore/codex-resume.zsh')],env=environment,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(capture.read_text().splitlines(),['--no-daemon','hello','--no-daemon','resume','--all','agents','-m','resume','exec','task'])

    def test_no_automatic_launch_before_fzf_confirmation(self):
        from tests.restore.test_cli import CLITests, SID
        from codexlib import snapshots,store
        from codexlib.models import Session,SavedTab,Snapshot
        fixture=CLITests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        session=Session(SID,fixture.root,Path(fixture.event['transcript_path']),fixture.paths.codex_home)
        store.write(fixture.paths,'tabs.json',snapshots._encode(Snapshot('old',1,[SavedTab((1,1),session)])))
        fzf=fixture.root/'fzf';fzf.write_text('#!/bin/sh\ncat >/dev/null\nexit 130\n');fzf.chmod(0o700)
        env={**fixture.environ,'HOME':str(fixture.root),'PATH':str(fixture.root)+':/usr/bin:/bin','CODEX_RESTORE_NO_AUTO':'1'}
        source=Path(__file__).resolve().parents[1]/'runtime/codex_restore/codex-resume.zsh'
        result=subprocess.run(['/bin/zsh','-f','-c','source "$1"; codex resume --restore','test',str(source)],env=env,cwd=fixture.root,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        launched_before_confirmation=[row for row in fixture.tools.calls() if row[1:3] in (['tab','new'],['session','run'])]
        self.assertEqual(launched_before_confirmation,[])
        self.assertFalse((fixture.paths.state_dir/'pending.json').exists())

    def test_combined_slow_restore_preserves_outer_hook_budget(self):
        from tests.restore.test_cli import CLITests
        import time
        fixture=CLITests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.register()
        (fixture.tools.root/'delay').write_text('10')
        settings=fixture.root/'runtime.json'
        settings.write_text(json.dumps({'restore':True,'status':True,'it2':str(fixture.tools.it2),'cache':str(fixture.root/'status'),'restore_codex_home':str(fixture.home),'restore_cache':str(fixture.root/'cache'),'restore_process':'/Applications/iTerm.app/Contents/MacOS/iTerm2'}))
        hook=Path(__file__).resolve().parents[1]/'runtime/hook.py'
        start=time.monotonic()
        result=subprocess.run([sys.executable,str(hook),'--agent','codex','--settings',str(settings)],input=json.dumps(fixture.event),env=self.hook_environment(fixture,hook),text=True,capture_output=True,timeout=4)
        self.assertEqual((result.returncode,result.stdout,result.stderr),(0,'{}\n',''))
        self.assertLess(time.monotonic()-start,3.2)
        pid=int(fixture.tools.pid.read_text())
        with self.assertRaises(ProcessLookupError):
            import os
            os.kill(pid,0)

    def test_metadata_bridge_preserves_source_registry_without_raw_payload(self):
        from tests.restore.test_cli import CLITests,SID
        from codexlib import store
        fixture=CLITests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.register()
        settings=fixture.root/'runtime.json'
        settings.write_text(json.dumps({'restore':True,'it2':str(fixture.tools.it2),'restore_codex_home':str(fixture.home),'restore_cache':str(fixture.root/'cache'),'restore_process':'/Applications/iTerm.app/Contents/MacOS/iTerm2'}))
        hook=Path(__file__).resolve().parents[1]/'runtime/hook.py'
        result=subprocess.run([sys.executable,str(hook),'--agent','codex','--settings',str(settings)],input=json.dumps(fixture.event),env=self.hook_environment(fixture,hook),text=True,capture_output=True,timeout=4)
        self.assertEqual((result.returncode,result.stdout,result.stderr),(0,'{}\n',''))
        self.assertEqual(store.read(fixture.paths,'tabs.json')['tabs'][0]['session']['session_id'],SID)
        for path in fixture.paths.state_dir.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertNotIn(b'PRIVATE_PROMPT_MARKER',path.read_bytes())
