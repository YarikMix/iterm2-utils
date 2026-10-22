import shutil
import unittest
from dataclasses import replace
from iterm2_utils.features.shell import runtime_payload
from iterm2_utils.models import FileEdit, SymlinkEdit
from tests import test_shell

class PayloadTests(test_shell.ShellFixture, unittest.TestCase):
    def test_payload_survives_checkout_move(self):
        checkout=self.root/'checkout'; checkout.mkdir()
        for name in ('runtime','vendor'):
            shutil.copytree(self.context.paths.repo/name,checkout/name)
        for name in ('LICENSE','THIRD_PARTY_NOTICES.md'):
            shutil.copy2(self.context.paths.repo/name,checkout/name)
        self.context.paths=replace(self.context.paths,repo=checkout)
        changes=runtime_payload(self.context,self.selection(('status',)))
        for edit in changes.edits:
            edit.path.parent.mkdir(parents=True,exist_ok=True)
            if isinstance(edit,SymlinkEdit): edit.path.symlink_to(edit.after)
            else: edit.path.write_bytes(edit.after)
        shutil.rmtree(checkout)
        self.assertTrue((self.context.paths.data/'current/codex.zsh').is_file())
        self.assertFalse(any(str(checkout).encode() in e.after for e in changes.edits if isinstance(e,FileEdit)))
        self.assertTrue(changes.consumers)
        import subprocess
        result=subprocess.run(['/bin/zsh','-dfc','source "$1"; whence -w codex','fixture',str(self.context.paths.data/'current/codex.zsh')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'codex: function')
    def test_release_identity_changes_with_payload_not_in_place(self):
        checkout=self.root/'checkout'; checkout.mkdir()
        for name in ('runtime','vendor'):
            shutil.copytree(self.context.paths.repo/name,checkout/name)
        for name in ('LICENSE','THIRD_PARTY_NOTICES.md'):
            shutil.copy2(self.context.paths.repo/name,checkout/name)
        self.context.paths=replace(self.context.paths,repo=checkout)
        first=runtime_payload(self.context,self.selection())
        (checkout/'runtime/new_helper.py').write_text('VALUE = 42\n')
        second=runtime_payload(self.context,self.selection())
        a=next(e.after for e in first.edits if isinstance(e,SymlinkEdit))
        b=next(e.after for e in second.edits if isinstance(e,SymlinkEdit))
        self.assertNotEqual(a,b)
        self.assertTrue(any(isinstance(e,FileEdit) and e.path.name=='new_helper.py' for e in second.edits))
    def test_source_symlink_is_rejected_before_edits(self):
        checkout=self.root/'checkout'; checkout.mkdir()
        for name in ('runtime','vendor'):
            shutil.copytree(self.context.paths.repo/name,checkout/name)
        (checkout/'runtime/foreign.py').symlink_to('/not-read')
        for name in ('LICENSE','THIRD_PARTY_NOTICES.md'):
            shutil.copy2(self.context.paths.repo/name,checkout/name)
        self.context.paths=replace(self.context.paths,repo=checkout)
        with self.assertRaises(ValueError): runtime_payload(self.context,self.selection())
