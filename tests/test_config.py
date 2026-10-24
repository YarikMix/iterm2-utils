import tomllib
import unittest
from iterm2_utils.config import jsonfile, tomlfile, zshrc


class ConfigTests(unittest.TestCase):
    ARRAY_TABLES = (
        b'[plugins."iterm2-status@known"]\nenabled = true\n\n'
        b'[[skills.config]] # first foreign entry\n"skill.name" = "first"\n'
        b'description = """keep\n[[fake.array]]\nenabled = true\ntext"""\n'
        b'[skills.config.options]\nlimits.max = 2\ninline = { other = true }\n'
        b"[[skills.'config']] # repeated entry\n'skill.name' = 'second'\n"
        b"description = '''keep\n[tui]\nnotifications = true\nmore text'''\n"
        b'[skills.config.options]\n"option.name" = false\n\n'
        b'[tui]\nnotifications = true\nother = "preserve"\n'
    )

    def test_unrelated_array_tables_preserve_every_byte_during_scalar_edits(self):
        cases = ((('plugins', 'iterm2-status@known', 'enabled'), False,
                  b'[plugins."iterm2-status@known"]\nenabled = true\n',
                  b'[plugins."iterm2-status@known"]\nenabled = false\n'),
                 (('tui', 'notifications'), ['approval-requested'],
                  b'[tui]\nnotifications = true\nother',
                  b'[tui]\nnotifications = ["approval-requested"]\nother'))
        for pointer, value, before, after in cases:
            with self.subTest(pointer=pointer):
                result = tomlfile.patch(self.ARRAY_TABLES, pointer, value)
                self.assertEqual(result, self.ARRAY_TABLES.replace(before, after))
                original, changed = tomlfile.parse(self.ARRAY_TABLES), tomlfile.parse(result)
                original_parent, changed_parent = original, changed
                for part in pointer[:-1]:
                    original_parent, changed_parent = original_parent[part], changed_parent[part]
                self.assertEqual(changed_parent.pop(pointer[-1]), value)
                original_parent.pop(pointer[-1])
                self.assertEqual(changed, original)

    def test_array_table_descendants_and_ancestors_remain_unsupported(self):
        for pointer in (('skills',), ('skills', 'config'), ('skills', 'config', 'skill.name'),
                        ('skills', 'config', 'options'), ('skills', 'config', 'options', 'option.name'),
                        ('skills', 'config', 'new'), ('skills', 'config', 'new', 'value')):
            for remove in (False, True):
                with self.subTest(pointer=pointer, remove=remove), self.assertRaises(ValueError):
                    tomlfile.patch(self.ARRAY_TABLES, pointer, False, remove=remove)

    def test_inserting_sibling_value_stops_before_array_table_header(self):
        original = b'[skills]\nother = true\n[[skills.config]]\nname = "keep"\n'
        result = tomlfile.patch(original, ('skills', 'extra'), False)
        self.assertEqual(result, b'[skills]\nother = true\nextra = false\n[[skills.config]]\nname = "keep"\n')
        self.assertEqual(tomlfile.parse(result), {'skills': {'other': True, 'extra': False, 'config': [{'name': 'keep'}]}})

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
