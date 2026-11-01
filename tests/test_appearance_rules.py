import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from runtime.appearance import BUILTIN_ICONS, load_rules, select_rule


class AppearanceRulesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.config = self.root / 'rules.json'
        (self.root / 'mail' / 'nested' / 'src').mkdir(parents=True)

    def rule(self, name='mail', color='#31ad64', icon='android-mail'):
        return {'root': str(self.root / name), 'color': color, 'icon': icon}

    def load(self, projects):
        self.config.write_text(json.dumps({'projects': projects}), encoding='utf-8')
        return load_rules(self.config)

    def test_five_project_variants_and_color_normalization(self):
        icons = ('android-mail', 'android-cloud', 'ios-mail', 'ios-cloud', 'kotlett')
        projects = []
        for icon in icons:
            (self.root / icon).mkdir()
            projects.append(self.rule(icon, icon=icon))
        rules = self.load(projects)
        self.assertEqual(len(rules), 5)
        for icon in icons:
            with self.subTest(icon=icon):
                selected = select_rule(rules, self.root / icon)
                self.assertEqual(selected['icon'], icon)
                self.assertEqual(selected['color'], '#31AD64')

    def test_root_boundary_and_nested_precedence(self):
        rules = self.load([self.rule()])
        self.assertEqual(select_rule(rules, self.root / 'mail')['icon'], 'android-mail')
        self.assertEqual(select_rule(rules, self.root / 'mail' / 'nested' / 'src')['icon'], 'android-mail')
        (self.root / 'mail-copy').mkdir()
        self.assertIsNone(select_rule(rules, self.root / 'mail-copy'))
        nested = self.rule('mail/nested', '#568DCE', 'ios-cloud')
        for projects in ([self.rule(), nested], [nested, self.rule()]):
            rules = self.load(projects)
            self.assertEqual(select_rule(rules, self.root / 'mail' / 'nested')['color'], '#568DCE')

    def test_physical_symlinks_match_and_duplicate_aliases_fail(self):
        (self.root / 'alias').symlink_to(self.root / 'mail', target_is_directory=True)
        rules = self.load([self.rule('alias')])
        self.assertEqual(rules[0]['root'], str(self.root / 'mail'))
        self.assertEqual(select_rule(rules, self.root / 'alias' / 'nested')['icon'], 'android-mail')
        with self.assertRaises(ValueError):
            self.load([self.rule(), self.rule('alias')])

    def test_duplicate_root_fails_even_with_different_appearance(self):
        with self.assertRaises(ValueError):
            self.load([self.rule(), self.rule(color='#568DCE', icon='ios-cloud')])

    def test_case_insensitive_physical_alias_matches_root_and_child(self):
        alias = self.root / 'MAIL'
        if not alias.is_dir() or not alias.samefile(self.root / 'mail'):
            self.skipTest('fixture filesystem is case-sensitive')
        rules = self.load([self.rule('MAIL')])
        for cwd in (self.root / 'mail', self.root / 'mail/nested/src'):
            self.assertEqual(select_rule(rules, cwd), rules[0])

    def test_case_insensitive_physical_duplicates_are_rejected(self):
        alias = self.root / 'MAIL'
        if not alias.is_dir() or not alias.samefile(self.root / 'mail'):
            self.skipTest('fixture filesystem is case-sensitive')
        with self.assertRaises(ValueError):
            self.load([self.rule(), self.rule('MAIL')])

    def test_directory_identity_selects_nearest_ancestor_and_rejects_duplicates(self):
        # Model aliases at the filesystem stat boundary on every host filesystem.
        aliases = {self.root / 'root-alias': self.root / 'mail',
                   self.root / 'nested-alias': self.root / 'mail/nested'}
        for alias in aliases:
            alias.mkdir()
        original_stat = Path.stat
        def stat(path, *args, **kwargs):
            return original_stat(aliases.get(path, path), *args, **kwargs)
        with patch.object(Path, 'stat', stat):
            for names in (('root-alias', 'nested-alias'), ('nested-alias', 'root-alias')):
                rules = self.load([self.rule(name) for name in names])
                self.assertEqual(select_rule(rules, self.root / 'mail/nested/src'), self.rule('nested-alias', '#31AD64'))
            with self.assertRaises(ValueError):
                self.load([self.rule(), self.rule('root-alias')])

    def test_distinct_case_sensitive_directories_remain_distinct(self):
        upper = self.root / 'MAIL'
        if upper.exists():
            self.skipTest('fixture filesystem is case-insensitive')
        upper.mkdir()
        rules = self.load([self.rule(), self.rule('MAIL', '#568DCE', 'ios-cloud')])
        self.assertEqual(select_rule(rules, self.root / 'mail')['icon'], 'android-mail')
        self.assertEqual(select_rule(rules, upper)['icon'], 'ios-cloud')

    def test_missing_roots_are_preserved_but_never_selected_or_created(self):
        missing = self.root / 'unmounted' / 'repository'
        rules = self.load([self.rule('unmounted/repository'), self.rule()])
        self.assertEqual(len(rules), 2)
        self.assertIsNone(select_rule(rules, missing))
        self.assertIsNone(select_rule(rules, missing / 'src'))
        self.assertEqual(select_rule(rules, self.root / 'mail')['icon'], 'android-mail')
        self.assertFalse(missing.parent.exists())

    def test_disappeared_root_missing_cwd_and_file_cwd_do_not_match(self):
        (self.root / 'gone').mkdir()
        rules = self.load([self.rule('gone'), self.rule()])
        (self.root / 'gone').rmdir()
        self.assertIsNone(select_rule(rules, self.root / 'gone'))
        self.assertIsNone(select_rule(rules, self.root / 'mail' / 'missing'))
        file_path = self.root / 'mail' / 'file'
        file_path.write_text('fixture', encoding='utf-8')
        self.assertIsNone(select_rule(rules, file_path))

    def test_shell_metacharacters_are_literal_data(self):
        name = 'space ; $(touch INJECTED) `touch INJECTED`'
        (self.root / name).mkdir()
        rules = self.load([self.rule(name)])
        self.assertEqual(select_rule(rules, self.root / name)['root'], str(self.root / name))
        self.assertFalse((self.root / 'INJECTED').exists())
        self.assertFalse(Path('INJECTED').exists())

    def test_absolute_custom_png_is_accepted_without_reading_source(self):
        icon = self.root / 'not present ; $(touch INJECTED).png'
        rules = self.load([self.rule(icon=str(icon))])
        self.assertEqual(rules[0]['icon'], str(icon))
        self.assertFalse(icon.exists())

    def test_empty_project_list_fails(self):
        with self.assertRaises(ValueError):
            self.load([])

    def test_invalid_json_schema_colors_roots_and_icons_fail(self):
        valid = self.rule()
        bad_documents = [None, [], {}, {'projects': {}}, {'projects': [], 'other': 1},
                         {'projects': [None]}, {'projects': ['mail']}]
        for field, values in {
            'root': [None, 7, '', 'relative/root', '~/mail', 'bad\x00root'],
            'color': [None, 7, '#abc', '123456', '#12345G', '#123456\n'],
            'icon': [None, 7, '', 'unknown', 'relative.png', 'https://example.org/a.png', '/bad.svg', '/bad\x00.png'],
        }.items():
            for value in values:
                bad_documents.append({'projects': [{**valid, field: value}]})
        bad_documents.extend({'projects': [{key: value for key, value in valid.items() if key != missing}]}
                             for missing in valid)
        bad_documents.append({'projects': [{**valid, 'command': 'touch INJECTED'}]})
        for document in bad_documents:
            with self.subTest(document=document):
                self.config.write_text(json.dumps(document), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_rules(self.config)
        self.config.write_text('{not json', encoding='utf-8')
        with self.assertRaises(ValueError):
            load_rules(self.config)


class AppearanceAssetsTests(unittest.TestCase):
    def test_all_builtin_icons_have_rgba_png_and_original_svg(self):
        assets = Path(__file__).resolve().parents[1] / 'runtime' / 'assets' / 'appearance'
        expected = {'ios', 'android', 'kotlett', 'ios-mail', 'ios-cloud', 'android-mail', 'android-cloud'}
        self.assertEqual(BUILTIN_ICONS, expected)
        self.assertEqual({path.stem for path in assets.glob('*.png')}, expected)
        self.assertEqual({path.stem for path in assets.glob('*.svg')}, expected)
        for icon in sorted(expected):
            with self.subTest(icon=icon):
                png = (assets / f'{icon}.png').read_bytes()
                self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
                width, height, depth, color = struct.unpack('>IIBB', png[16:26])
                self.assertEqual((width, height, depth, color), (128, 128, 8, 6))
                offset = 8
                compressed = bytearray()
                while offset < len(png):
                    length = struct.unpack('>I', png[offset:offset + 4])[0]
                    kind = png[offset + 4:offset + 8]
                    data = png[offset + 8:offset + 8 + length]
                    crc = struct.unpack('>I', png[offset + 8 + length:offset + 12 + length])[0]
                    self.assertEqual(zlib.crc32(kind + data), crc)
                    if kind == b'IDAT':
                        compressed.extend(data)
                    offset += length + 12
                raw = zlib.decompress(compressed)
                self.assertEqual(len(raw), height * (1 + width * 4))
                # The transparent top-left pixel is zero under every PNG filter.
                self.assertEqual(raw[1:5], bytes(4))
                self.assertIn('<svg', (assets / f'{icon}.svg').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
