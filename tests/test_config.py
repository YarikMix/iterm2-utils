import tomllib
import unittest
from iterm2_utils.config import jsonfile, tomlfile, zshrc


class ConfigTests(unittest.TestCase):
    def test_plugin_toggle_preserves_unrelated_quoted_multiline_statements(self):
        for token in ('"model.example"', "'model.example'", '"model=example"',
                      '"model'+chr(92)+'"example"', "'model\"example'"):
            with self.subTest(token=token):
                content = ('# foreign configuration\n[aliases]\n'+token+
                    ' = """keep\nenabled = true\n[not.a.table]\ntext""" # keep comment\n'+
                    "'literal.value' = '''keep\nmore text'''\n"+
                    '[plugins."iterm2-status@known"]\nenabled = true\nother = [1, 2]\n').encode()
                result = tomlfile.patch(content, ('plugins', 'iterm2-status@known', 'enabled'), False)
                expected = content.replace(b'\nenabled = true\nother', b'\nenabled = false\nother')
                self.assertEqual(result, expected)
                self.assertFalse(tomlfile.parse(result)['plugins']['iterm2-status@known']['enabled'])

    def test_quoted_scalar_replacement_and_removal_keep_single_component_keys(self):
        cases = (('"copy.on.select"', 'copy.on.select'),
                 ("'copy.on.select'", 'copy.on.select'),
                 ('"copy'+chr(92)+'"on=select"', 'copy"on=select'),
                 ("'copy\"on=select'", 'copy"on=select'),
                 ('"copy'+chr(92)+'u002eon"', 'copy.on'))
        for token, key in cases:
            with self.subTest(token=token):
                prefix = b'[tui]\n# keep neighbor\nother = """a\nb"""\n'
                original = prefix+(token+' = "always" # old policy\n').encode()
                installed = tomlfile.patch(original, ('tui', key), 'never')
                self.assertEqual(tomlfile.parse(installed), {'tui': {'other': 'a\nb', key: 'never'}})
                self.assertTrue(installed.startswith(prefix))
                restored = tomlfile.patch(installed, ('tui', key), 'always')
                self.assertEqual(tomlfile.parse(restored), {'tui': {'other': 'a\nb', key: 'always'}})
                self.assertEqual(tomlfile.patch(installed, ('tui', key), None, remove=True), prefix)

    def test_multiline_toml_does_not_change_neighbor_values(self):
        content = b'[tui]\nneighbor = """hello\ncopy_on_select = \'inside text\'\nworld"""\ncopy_on_select = "always"\nother = [1, 2]\n'
        result = tomlfile.set_tui_key(content,'copy_on_select','never')
        before, after = tomllib.loads(content.decode()), tomllib.loads(result.decode())
        self.assertEqual(after['tui'].pop('copy_on_select'), 'never')
        before['tui'].pop('copy_on_select')
        unrelated_toml_before, unrelated_toml_after = before, after
        assert unrelated_toml_before == unrelated_toml_after

    def test_unsupported_inline_and_dotted_tui_conflict(self):
        for content in (b'tui = { copy_on_select = "always" }\n', b'tui.copy_on_select = "always"\n',
                        b'"tui"."copy_on_select" = "always"\n',
                        b"'tui'.'copy_on_select' = 'always'\n",
                        b'"tui" = { "copy_on_select" = "always", other = true }\n'):
            with self.subTest(content=content), self.assertRaises(ValueError):
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
