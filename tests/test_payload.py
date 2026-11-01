import shutil
import json
from pathlib import Path
import subprocess
import sys
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
        self.assertTrue((self.context.paths.data/'current/native_status.py').is_file())
        self.assertFalse(any(e.path.name in {'cc-status','it2'} for e in changes.edits))
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


class AppearancePayloadTests(test_shell.ShellFixture, unittest.TestCase):
    def checkout(self):
        checkout = self.root/'checkout'
        checkout.mkdir()
        for name in ('runtime', 'vendor'):
            shutil.copytree(self.context.paths.repo/name, checkout/name)
        for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
            shutil.copy2(self.context.paths.repo/name, checkout/name)
        self.context.paths = replace(self.context.paths, repo=checkout)
        return checkout

    def test_known_assets_and_helpers_are_installed_without_arbitrary_images(self):
        checkout = self.checkout()
        (checkout/'runtime/assets/appearance/private.png').write_bytes(b'PRIVATE_FIXTURE')
        changes = runtime_payload(self.context, self.selection(('appearance',)))
        release = Path(next(e.after for e in changes.edits if isinstance(e, SymlinkEdit)))
        files = {str(e.path.relative_to(release)): e.after
                 for e in changes.edits if isinstance(e, FileEdit)}
        names = {'ios', 'android', 'kotlett', 'ios-mail', 'ios-cloud', 'android-mail', 'android-cloud',
                 'chrome-mail', 'chrome-cloud'}
        self.assertEqual({p for p in files if p.startswith('assets/')},
                         {f'assets/appearance/{name}.{ext}' for name in names for ext in ('png', 'svg')})
        self.assertTrue({'appearance.py', 'appearance.zsh', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
                         'vendor/shell_integration/LICENSE', 'vendor/codex_status/LICENSE'} <= files.keys())

    def test_builtin_bytes_change_release_and_appearance_plan_identity(self):
        from iterm2_utils.planner import plan
        checkout = self.checkout()
        self.context.capabilities |= {'macos', 'python:iterm2'}
        self.context.appearance_config = self.root/'rules.json'
        self.context.appearance_config.write_text(json.dumps({'projects': [dict(root=str(self.root), color='#123456', icon='ios')]}))
        selection = self.selection(('appearance',))
        first = runtime_payload(self.context, selection)
        fingerprint = plan(self.context, selection).fingerprint
        target = checkout/'runtime/assets/appearance/android-mail.png'
        target.write_bytes((checkout/'runtime/assets/appearance/ios.png').read_bytes())
        second = runtime_payload(self.context, selection)
        self.assertNotEqual(next(e.after for e in first.edits if isinstance(e, SymlinkEdit)),
                            next(e.after for e in second.edits if isinstance(e, SymlinkEdit)))
        self.assertNotEqual(fingerprint, plan(self.context, selection).fingerprint)

    def test_missing_or_symlink_assets_are_rejected(self):
        checkout = self.checkout()
        for relative in ('assets/appearance/ios.png', 'assets/appearance/ios.svg'):
            target = checkout/'runtime'/relative
            before = target.read_bytes()
            target.unlink()
            with self.assertRaises(ValueError): runtime_payload(self.context, self.selection(('appearance',)))
            target.symlink_to(checkout/'LICENSE')
            with self.assertRaises(ValueError): runtime_payload(self.context, self.selection(('appearance',)))
            target.unlink(); target.write_bytes(before)
        folder = checkout/'runtime/assets/appearance'
        folder.rename(folder.with_name('original'))
        folder.symlink_to(folder.with_name('original'), target_is_directory=True)
        with self.assertRaises(ValueError): runtime_payload(self.context, self.selection(('appearance',)))

    def test_installed_icons_selected_after_all_sources_removed(self):
        from tests.test_lifecycle import LifecycleFixture
        fixture = LifecycleFixture(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        checkout = self.checkout()
        fixture.context.paths = replace(fixture.context.paths, repo=checkout)
        fixture.context.capabilities |= {'python:iterm2'}
        home = fixture.context.paths.home
        names = ('ios-mail', 'ios-cloud', 'android-mail', 'android-cloud',
                 'chrome-mail', 'chrome-cloud', 'kotlett')
        projects = []
        expected = {}
        for name in names:
            project = home/name; project.mkdir()
            projects.append(dict(root=str(project), color='#123456', icon=name))
            asset = checkout/f'runtime/assets/appearance/{name}.png'
            self.assertTrue(asset.is_file(), f'Missing builtin asset: {name}')
            expected[name] = asset.read_bytes().hex()
        custom_root = home/'custom'; custom_root.mkdir()
        original_png = home/'original.png'
        custom_bytes = (checkout/'runtime/assets/appearance/ios.png').read_bytes()
        original_png.write_bytes(custom_bytes)
        projects.append(dict(root=str(custom_root), color='#654321', icon=str(original_png)))
        expected['custom'] = custom_bytes.hex()
        source = home/'source-rules.json'
        source.write_text(json.dumps({'projects': projects}))
        fixture.context.appearance_config = source
        result = fixture.install('appearance'); fixture.assertSuccess(result)
        current = fixture.context.paths.data/'current'
        config = fixture.context.paths.config/'appearance.json'
        source.unlink(); original_png.unlink(); shutil.rmtree(checkout)
        script = """import hashlib, json, pathlib, sys
current, config, home = map(pathlib.Path, sys.argv[1:4])
expected = json.loads(sys.argv[4])
sys.path.insert(0, str(current))
import appearance
rules = appearance.load_rules(config)
assert len(rules) == 8
seen = []
async def worker(request):
    cwd = pathlib.Path(request['cwd'])
    if cwd == home:
        assert request.get('reset') is True, request
        assert not {'color', 'icon', 'preserve'} & request.keys()
        seen.append(None)
        return 'applied'
    name = cwd.name
    wanted_bytes = bytes.fromhex(expected[name])
    icon = pathlib.Path(request['icon'])
    assert icon.is_file() and icon.read_bytes() == wanted_bytes, name
    wanted_path = (current/'assets/appearance'/(name+'.png') if name != 'custom' else
                   current.parent/'appearance/icons'/(hashlib.sha256(wanted_bytes).hexdigest()+'.png'))
    assert icon == wanted_path, (icon, wanted_path)
    seen.append(name)
    return 'applied'
appearance._operate = worker
for cwd in [*(home/name for name in expected), home]:
    assert appearance._run_request(dict(config=str(config), cwd=str(cwd), phase='shell', terminal='12345678-1234-4234-8234-123456789abc')) == 'applied'
assert seen == [*expected, None], seen
assert (current/'LICENSE').is_file() and (current/'THIRD_PARTY_NOTICES.md').is_file()
"""
        result = subprocess.run([sys.executable, '-c', script, str(current), str(config), str(home), json.dumps(expected)],
                                cwd=home, env={'PATH':'/usr/bin:/bin', 'PYTHONNOUSERSITE':'1'},
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_installed_chpwd_hook_survives_source_removal(self):
        from tests.test_lifecycle import LifecycleFixture
        fixture = LifecycleFixture(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        checkout = self.checkout()
        fixture.context.paths = replace(fixture.context.paths, repo=checkout)
        fixture.context.capabilities |= {'python:iterm2'}
        home = fixture.context.paths.home
        project = home/'project'; project.mkdir()
        alias = home/'alias'; alias.symlink_to(project, target_is_directory=True)
        source = home/'source-rules.json'
        source.write_text(json.dumps({'projects': [dict(root=str(project), color='#123456', icon='ios')]}))
        fixture.context.appearance_config = source
        fixture.assertSuccess(fixture.install('appearance'))
        current = fixture.context.paths.data/'current'
        config = fixture.context.paths.config/'appearance.json'
        source.unlink(); shutil.rmtree(checkout)
        boundary = home/'python-boundary'
        boundary.write_text(f'#!{sys.executable}\n'+"""import json, os, pathlib, sys
helper = pathlib.Path(sys.argv[1])
assert helper.is_file() and helper.name == 'appearance.py'
arguments = dict(zip(sys.argv[2::2], sys.argv[3::2]))
assert pathlib.Path(arguments['--config']).is_file()
with open(os.environ['CALLS'], 'a') as stream:
    stream.write(json.dumps([str(helper), arguments])+'\\n')
""")
        boundary.chmod(0o700)
        calls = home/'calls.jsonl'
        script = """function await_calls {
  local n
  for n in {1..200}; do
    [[ -f $CALLS && $(/usr/bin/wc -l < "$CALLS") -ge $1 ]] && return 0
    /bin/sleep 0.01
  done
  return 1
}
source "$1/appearance.zsh"
await_calls 1 || exit 11
cd "$2" || exit 12
await_calls 2 || exit 13
cd "$HOME" || exit 14
await_calls 3 || exit 15
"""
        result = subprocess.run(['/bin/zsh', '-dfi', '-c', script, 'fixture', str(current), str(alias)],
                                cwd=home, env={'HOME': str(home), 'ZDOTDIR': str(home), 'PATH': '/usr/bin:/bin',
                                              'TERM_PROGRAM': 'iTerm.app', 'ITERM_SESSION_ID': '12345678-1234-4234-8234-123456789abc',
                                              'ITERM2_UTILS_PYTHON': str(boundary), 'ITERM2_UTILS_APPEARANCE_CONFIG': str(config),
                                              'CALLS': str(calls)},
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(result.stdout+result.stderr, '')
        records = [json.loads(line) for line in calls.read_text().splitlines()]
        self.assertEqual(records, [[str(current.resolve()/'appearance.py'),
                                   {'--config': str(config), '--cwd': str(cwd.resolve()), '--phase': 'shell'}]
                                  for cwd in (home, project, home)])
