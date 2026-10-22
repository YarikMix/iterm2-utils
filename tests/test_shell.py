import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import replace
from iterm2_utils.models import Context, Paths, Selection, FileEdit
from iterm2_utils.features.shell import build

REPO = Path(__file__).resolve().parents[1]

class ShellFixture:
    def setUp(self):
        tmp = TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "Юникод space ' $(touch INJECTED)"
        p.mkdir(); self.root=p
        self.context=Context(Paths(p,p/'zshrc',p/'codex',p/'claude.json',p/'config',p/'cache',p/'data',p/'profiles',REPO),{'python3':Path('/usr/bin/python3')},{},frozenset({'codex:no-daemon'}),{}, {})
    def selection(self, features=('shell',)):
        return Selection(frozenset({'codex'}),frozenset(features),frozenset(),'Default')

class ShellTests(ShellFixture, unittest.TestCase):
    def test_alias_codex_conflict(self):
        self.context.paths.zshrc.write_text("alias codex='other'\n")
        changes=build(self.context,self.selection(('status',)))
        self.assertEqual(changes.edits,[])
        self.assertTrue(any(f.state=='conflict' for f in changes.findings))
    def test_arbitrary_function_conflict(self):
        self.context.paths.zshrc.write_text('function codex() { echo other; }\n')
        self.assertEqual(build(self.context,self.selection(('status',))).edits,[])
    def test_existing_integration_is_reused(self):
        self.context.paths.zshrc.write_text('source ~/.iterm2_shell_integration.zsh\n')
        changes=build(self.context,self.selection())
        self.assertTrue(any(f.code=='existing_integration' for f in changes.findings))
        self.assertFalse(any(isinstance(e,FileEdit) and e.path==self.context.paths.zshrc for e in changes.edits))
    def test_dispatcher_does_not_enable_marks(self):
        changes=build(self.context,self.selection(('status',)))
        text=next(e.after.decode() for e in changes.edits if isinstance(e,FileEdit) and e.path==self.context.paths.zshrc)
        self.assertNotIn('shell_integration',text)
        self.assertIn('codex.zsh',text)
    def test_unicode_source_path_is_literal(self):
        import subprocess
        changes=build(self.context,self.selection(('status',)))
        from iterm2_utils.features.shell import runtime_payload
        from iterm2_utils.models import SymlinkEdit
        for e in runtime_payload(self.context,self.selection(('status',))).edits:
            e.path.parent.mkdir(parents=True,exist_ok=True)
            if isinstance(e,SymlinkEdit): e.path.symlink_to(e.after)
            else: e.path.write_bytes(e.after)
        text=next(e.after for e in changes.edits if isinstance(e,FileEdit) and e.path==self.context.paths.zshrc)
        startup=self.root/'startup'; startup.write_bytes(text)
        result=subprocess.run(['/bin/zsh','-dfc','source "$1"', 'test',str(startup)],cwd=self.root,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse((self.root/'INJECTED').exists())
    def test_shell_marks_only_inside_iterm(self):
        import subprocess
        changes=build(self.context,self.selection())
        startup=next(e.after.decode() for e in changes.edits if isinstance(e,FileEdit) and e.path==self.context.paths.zshrc)
        integration=self.context.paths.data/'current/vendor/shell_integration/iterm2_shell_integration.zsh'
        integration.parent.mkdir(parents=True)
        integration.write_text('typeset -g FIXTURE_MARKS=loaded\n')
        for terminal,preloaded,expected in [('other','', 'absent'),('iTerm.app','', 'loaded'),('iTerm.app','Yes','absent')]:
            script='TERM_PROGRAM='+terminal+'; ITERM_SHELL_INTEGRATION_INSTALLED='+preloaded+'; '+startup+'\nprint -r -- ${FIXTURE_MARKS-absent}'
            result=subprocess.run(['/bin/zsh','-dfc',script],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),expected)
    def test_legacy_managed_wrapper_requires_migration(self):
        self.context.paths.zshrc.write_text('# >>> codex-no-daemon >>>\nfunction codex() { command codex "$@"; }\n# <<< codex-no-daemon <<<\n')
        self.assertEqual(build(self.context,self.selection(('status',))).edits,[])
    def test_shell_block_named_block_inverse_and_malformed_rejected(self):
        from iterm2_utils.config import zshrc
        original=b'export KEEP=yes\n'
        named=zshrc.block(original,'legacy','echo named')
        both=zshrc.block(named,'root','echo root')
        self.assertEqual(zshrc.block(both,'root',None),named)
        self.assertEqual(zshrc.block(zshrc.block(both,'legacy',None),'root',None),original)
        for malformed in (b'# >>> iterm2-utils >>>\n', b'# <<< iterm2-utils <<<\n',b'# >>> iterm2-utils BAD >>>\n',both+ b'# <<< iterm2-utils:bad <<<\n'):
            with self.assertRaises(ValueError): zshrc.blocks(malformed)
    def test_recompose_marks_removal_keeps_status_dispatcher(self):
        from iterm2_utils import engine
        from iterm2_utils.models import Plan
        from tests.support import FakeRunner
        first=self.selection(('shell','status'))
        from iterm2_utils.features.shell import runtime_payload
        changes=build(self.context,first); payload=runtime_payload(self.context,first)
        changes.edits.extend(payload.edits); changes.consumers.update(payload.consumers)
        outcome=engine.apply(Plan(first,changes,'fixture'),self.context,FakeRunner())
        self.assertTrue(outcome.receipt.resources, [f.code for f in outcome.findings])
        remaining=self.selection(('status',))
        changes=build(self.context,remaining)
        outcome=engine.apply(Plan(remaining,changes,'fixture'),self.context,FakeRunner())
        outcome=engine.revert(outcome.receipt,self.context,FakeRunner(),frozenset({'shell'}))
        startup=self.context.paths.zshrc.read_text()
        self.assertNotIn('shell_integration',startup)
        self.assertIn('codex.zsh',startup)
        self.assertTrue((self.context.paths.data/'current/codex.zsh').exists())
        self.assertFalse(any(f.state=='conflict' for f in outcome.findings))
    def test_restore_sources_after_dispatcher(self):
        changes=build(self.context,self.selection(('restore',)))
        text=next(e.after.decode() for e in changes.edits if isinstance(e,FileEdit) and e.path==self.context.paths.zshrc)
        self.assertLess(text.index("/codex.zsh"),text.index('/codex_restore/codex-resume.zsh'))
