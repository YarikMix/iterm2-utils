import contextlib
import io
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from tests.support import Fixture
from iterm2_utils import skill_install
from iterm2_utils.cli import main
from iterm2_utils.discovery import resolve_paths
from iterm2_utils.models import Context


class SkillInstallTests(unittest.TestCase):
    def context(self):
        return Context(resolve_paths(), {}, {}, frozenset(), {}, {})

    def invoke(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['bootstrap-skill', *args, '--json'])
        return code, json.loads(out.getvalue())

    def test_skill_install_does_not_replace_foreign_directory(self):
        with Fixture() as f:
            dest = f.home/'.codex/skills/iterm2-setup'
            dest.mkdir(parents=True)
            (dest/'mine').write_text('foreign')
            before = f.snapshot()
            changes = skill_install.build(self.context(), frozenset({'codex'}))
            self.assertEqual(changes.edits, [])
            self.assertTrue(any(x.state == 'conflict' for x in changes.findings))
            self.assertEqual(before, f.snapshot())

    def test_bootstrap_uses_actual_home_and_codex_home(self):
        with Fixture() as f, patch.dict('os.environ', {'CODEX_HOME': str(f.home/'custom-codex')}):
            code, output = self.invoke('--agent', 'codex')
            self.assertEqual(code, 0, output)
            self.assertTrue((f.home/'custom-codex/skills/iterm2-setup/SKILL.md').is_file())
            self.assertFalse((f.home/'.codex').exists())
            self.assertFalse((f.home/'.claude').exists())
            self.assertEqual(output['selection']['features'], [])

    def test_dry_run_has_no_writes_or_agent_probes(self):
        with Fixture() as f:
            before = f.snapshot()
            with patch('iterm2_utils.cli.Runner', return_value=f.runner):
                code, output = self.invoke('--agent', 'both', '--dry-run')
            self.assertEqual(code, 0, output)
            self.assertEqual(before, f.snapshot())
            self.assertEqual(f.runner.calls, [])

    def test_owned_update_idempotence_and_user_changes_preserved(self):
        with Fixture() as f:
            self.assertEqual(self.invoke('--agent', 'codex')[0], 0)
            path = f.home/'.codex/skills/iterm2-setup/SKILL.md'
            stamp = path.stat().st_mtime_ns
            self.assertEqual(self.invoke('--agent', 'codex')[0], 0)
            self.assertEqual(stamp, path.stat().st_mtime_ns)
            path.write_text('user edit')
            self.assertEqual(self.invoke('--agent', 'codex', '--dry-run')[0], 2)
            self.assertEqual(self.invoke('--agent', 'codex')[0], 2)
            self.assertEqual(path.read_text(), 'user edit')

    def test_second_agent_is_only_installed_when_selected(self):
        with Fixture() as f:
            self.assertEqual(self.invoke('--agent', 'claude')[0], 0)
            self.assertFalse((f.home/'.codex').exists())
            first = (f.home/'.claude/skills/iterm2-setup/SKILL.md').read_bytes()
            self.assertEqual(self.invoke('--agent', 'codex')[0], 0)
            self.assertEqual((f.home/'.claude/skills/iterm2-setup/SKILL.md').read_bytes(), first)
            self.assertTrue((f.home/'.codex/skills/iterm2-setup/SKILL.md').is_file())

    def test_symlink_target_is_foreign(self):
        with Fixture() as f:
            dest = f.home/'.codex/skills/iterm2-setup'
            dest.parent.mkdir(parents=True)
            target = f.home/'foreign'; target.mkdir()
            dest.symlink_to(target, target_is_directory=True)
            code, _ = self.invoke('--agent', 'codex')
            self.assertEqual(code, 2)
            self.assertEqual(list(target.iterdir()), [])

    def test_bootstrap_does_not_change_feature_receipt(self):
        with Fixture() as f:
            with patch('iterm2_utils.cli.Runner', return_value=f.runner), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['install','--agent','codex','--features','shell','--json']), 0)
            path = resolve_paths().data/'receipt.json'
            before = path.read_bytes()
            self.assertEqual(self.invoke('--agent', 'codex')[0], 0)
            self.assertEqual(path.read_bytes(), before)

    def test_owned_source_update_copies_all_references(self):
        with Fixture() as f:
            context = self.context()
            bundle = f.home/'source/skills/iterm2-setup'
            for name in skill_install.FILES:
                source = context.paths.repo/'skills/iterm2-setup'/name
                target = bundle/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            context.paths = replace(context.paths, repo=f.home/'source')
            self.assertEqual(skill_install.install(context, frozenset({'codex'}), f.runner)[0].state, 'ready')
            (bundle/'references/features.md').write_text('updated reference\n')
            findings = skill_install.install(context, frozenset({'codex'}), f.runner)
            self.assertFalse(any(x.state == 'conflict' for x in findings), findings)
            target = context.paths.codex_home/'skills/iterm2-setup'
            self.assertEqual((target/'references/features.md').read_text(), 'updated reference\n')
            self.assertEqual(sorted(str(p.relative_to(target)) for p in target.rglob('*') if p.is_file()), sorted(skill_install.FILES))

    def test_corrupt_bootstrap_receipt_blocks_copy(self):
        with Fixture() as f:
            path = resolve_paths().data/'bootstrap-skill/receipt.json'
            path.parent.mkdir(parents=True)
            path.write_text('{BROKEN')
            before = f.snapshot()
            code, output = self.invoke('--agent', 'codex')
            self.assertEqual(code, 2)
            self.assertEqual(before, f.snapshot())
            self.assertNotIn('BROKEN', str(output))

    def test_foreign_reference_symlink_and_file_are_not_adopted(self):
        with Fixture() as f:
            self.assertEqual(self.invoke('--agent', 'codex')[0], 0)
            target = f.home/'.codex/skills/iterm2-setup/references/features.md'
            target.unlink()
            foreign = f.home/'foreign.md'; foreign.write_text('foreign')
            target.symlink_to(foreign)
            code, _ = self.invoke('--agent', 'codex')
            self.assertEqual(code, 2)
            self.assertEqual(foreign.read_text(), 'foreign')
