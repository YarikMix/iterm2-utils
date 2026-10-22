import tomllib
import unittest
from iterm2_utils.config import jsonfile, tomlfile, zshrc


class ConfigTests(unittest.TestCase):
    def test_multiline_toml_does_not_change_neighbor_values(self):
        content = b'[tui]\nneighbor = """hello\ncopy_on_select = \'inside text\'\nworld"""\ncopy_on_select = "always"\nother = [1, 2]\n'
        result = tomlfile.set_tui_key(content,'copy_on_select','never')
        before, after = tomllib.loads(content.decode()), tomllib.loads(result.decode())
        self.assertEqual(after['tui'].pop('copy_on_select'), 'never')
        before['tui'].pop('copy_on_select')
        unrelated_toml_before, unrelated_toml_after = before, after
        assert unrelated_toml_before == unrelated_toml_after

    def test_unsupported_inline_and_dotted_tui_conflict(self):
        for content in (b'tui = { copy_on_select = "always" }\n', b'tui.copy_on_select = "always"\n'):
            with self.assertRaises(ValueError):
                tomlfile.set_tui_key(content,'copy_on_select','never')

    def test_json_pointer_and_zsh_block(self):
        self.assertIn(b'false', jsonfile.patch(b'{"tui":{}}',('tui','copy'),False))
        original = b'export USER_THING=yes\n'
        installed = zshrc.block(original,'shell','source /fixture/script')
        self.assertEqual(zshrc.block(installed,'shell',None), original)

    def test_preference_calls_are_bounded_and_typed(self):
        import plistlib
        import subprocess
        from iterm2_utils.config import preferences
        class Fake:
            def __init__(self): self.calls=[]
            def run(self,argv,*,timeout,stdin=None):
                self.calls.append((argv,timeout))
                return subprocess.CompletedProcess(argv,0,plistlib.dumps({'CopySelection':True}).decode(),'')
        runner=Fake()
        self.assertEqual(preferences.read(runner,'fixture.domain','CopySelection'),{'exists':True,'value':True})
        preferences.write(runner,'fixture.domain','CopySelection',{'exists':True,'value':False})
        self.assertEqual(runner.calls[-1][0],['defaults','write','fixture.domain','CopySelection','-bool','false'])
        self.assertTrue(all(timeout==5 for _,timeout in runner.calls))
