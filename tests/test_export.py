"""Public beta export is allowlisted, provenance checked and independently usable."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools import build_release, check_export

ROOT = Path(__file__).resolve().parents[1]


class ExportTests(unittest.TestCase):
    def test_export_requires_unique_native_contract_paths(self):
        required = {'runtime/native_status.py', 'tests/test_native_status.py',
                    'tests/test_native_status_migration.py', 'tests/fixtures/beta1-status.json',
                    'docs/native-status-events.md'}
        self.assertTrue(required <= set(check_export.EXPORT_FILES))
        self.assertEqual(len(check_export.EXPORT_FILES), len(set(check_export.EXPORT_FILES)))
        sources = {entry['path']: entry for entry in json.loads((ROOT/'sources.lock.json').read_text())['sources']}
        for name in ('vendor/codex_status/status.py', 'vendor/codex_status/iterm_support.py'):
            self.assertIn(name, check_export.EXPORT_FILES)
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), sources[name]['sha256'])
            self.assertEqual(sources[name]['license_file'], 'vendor/codex_status/LICENSE')
            self.assertEqual(sources[name]['attribution_file'], 'THIRD_PARTY_NOTICES.md')
        self.assertFalse(any(Path(name).name in {'cc-status', 'it2'} for name in sources))
        with patch.object(check_export, 'EXPORT_FILES',
                          (*check_export.EXPORT_FILES, 'runtime/native_status.py')):
            self.assertIn('Duplicate export path: runtime/native_status.py', check_export.check(ROOT))

    def fixture(self, folder):
        repo = folder/'repo'
        for name in check_export.EXPORT_FILES:
            target = repo/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/name, target)
        return repo

    def test_export_excludes_state_and_secret_fixtures(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); repo = self.fixture(root)
            for name in ('.env', '.env.production', '.git/config', 'tests/fixtures/private.json',
                         'runtime/.env.py', 'runtime/receipt.json', 'runtime/backup.py',
                         'logs/transcript.jsonl', 'auth/token', 'runtime/__pycache__/secret.pyc',
                         'runtime/raw-event.json', 'runtime/cc-status', 'runtime/it2',
                         'Applications/iTerm.app/Contents/Resources/utilities/cc-status',
                         'Applications/iTerm.app/Contents/Resources/utilities/it2'):
                path = repo/name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((b'PRIVATE_' + b'FIXTURE_MARKER'))
            archive = build_release.build(repo, root/'dist')
            self.assertNotIn((b'PRIVATE_' + b'FIXTURE_MARKER'), archive.read_bytes())
            with tarfile.open(archive) as tar:
                members = tar.getmembers()
                self.assertEqual(len(members), len(check_export.EXPORT_FILES))
                names = {m.name.split('/', 1)[1] for m in members if '/' in m.name}
                self.assertEqual(len(names), len(members))
                self.assertIn('skills/iterm2-setup/SKILL.md', names)
                self.assertIn('vendor/codex_status/LICENSE', names)
                for member in members:
                    self.assertTrue(member.isfile())
                    self.assertNotIn((b'PRIVATE_' + b'FIXTURE_MARKER'), tar.extractfile(member).read())
                self.assertEqual(names, set(check_export.EXPORT_FILES))
                self.assertTrue({'runtime/native_status.py', 'tests/test_native_status.py',
                                 'tests/test_native_status_migration.py',
                                 'tests/fixtures/beta1-status.json',
                                 'docs/native-status-events.md'} <= names)
            checksum = archive.with_name(archive.name+'.sha256').read_text()
            self.assertEqual(checksum, hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
            self.assertNotIn(str(root), checksum)
            repeated = build_release.build(repo, root/'repeat')
            self.assertEqual(archive.read_bytes(), repeated.read_bytes())

    def test_missing_notice_or_source_hash_fails(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); repo = self.fixture(root)
            notice = repo/'THIRD_PARTY_NOTICES.md'; original = notice.read_bytes(); notice.unlink()
            self.assertTrue(check_export.check(repo))
            with self.assertRaises(ValueError):
                build_release.build(repo, root/'dist')
            notice.write_bytes(original)
            lock = repo/'sources.lock.json'; data = json.loads(lock.read_text())
            del data['sources'][0]['sha256']; lock.write_text(json.dumps(data))
            self.assertTrue(check_export.check(repo))
            data['sources'][0]['sha256'] = '0'*64; lock.write_text(json.dumps(data))
            self.assertTrue(check_export.check(repo))
            data['sources'][0]['ref'] = 'main'; lock.write_text(json.dumps(data))
            self.assertTrue(check_export.check(repo))

    def test_scanner_redacts_private_content_and_rejects_symlinks(self):
        with TemporaryDirectory() as tmp:
            repo = self.fixture(Path(tmp)); file = repo/'README.md'
            for value in ('https://'+'.'.join(('example','vk','team'))+'/private-secret',
                          'git@'+'.'.join(('gitlab','corp','mail','ru'))+':private-secret',
                          '/'+'Users/example/private-secret'):
                file.write_text(value)
                errors = check_export.check(repo)
                self.assertTrue(errors)
                self.assertNotIn('private-secret', '\n'.join(errors))
            file.unlink(); file.symlink_to(ROOT/'README.md')
            self.assertTrue(check_export.check(repo))

    def extract(self, archive, destination):
        with tarfile.open(archive) as tar:
            # Every generated member is a regular file under one fixed root.
            for member in tar.getmembers():
                self.assertTrue(member.isfile())
                self.assertTrue((destination/member.name).resolve().is_relative_to(destination.resolve()))
            for member in tar.getmembers():
                path = destination/member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(tar.extractfile(member).read())
                path.chmod(member.mode)
        return destination/'iterm2-utils-v0.1.0-beta.1'

    def isolated_env(self, home):
        return {'HOME': str(home), 'PATH': '/usr/bin:/bin', 'PYTHONNOUSERSITE': '1',
                'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': '', 'TMUX': '',
                'ITERM_SESSION_ID': '12345678-1234-1234-1234-123456789abc',
                'TERM_SESSION_ID': 'w0t0p0:12345678-1234-1234-1234-123456789abc'}

    def run_python(self, extracted, home, *args):
        home.mkdir(exist_ok=True)
        return subprocess.run([sys.executable, *args], cwd=extracted, env=self.isolated_env(home),
                              text=True, capture_output=True, timeout=120)

    def test_fresh_extract_has_no_source_checkout_dependency(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); repo = self.fixture(root)
            archive = build_release.build(repo, root/'dist')
            extracted = self.extract(archive, root/'extract')
            repo.rename(root/'checkout-unavailable')
            script = '''import importlib, pathlib
for root in ('iterm2_utils', 'runtime', 'vendor/codex_status'):
    for path in pathlib.Path(root).rglob('*.py'):
        if path.name == '__main__.py':
            continue
        name = '.'.join(path.with_suffix('').parts)
        importlib.import_module(name)
from tools.check_export import check
assert not check(pathlib.Path.cwd())
'''
            result = self.run_python(extracted, root/'home', '-c', script)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_release_cli_scenarios_are_hermetic(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); repo = self.fixture(root)
            archive = build_release.build(repo, root/'dist')
            extracted = self.extract(archive, root/'extract')
            repo.rename(root/'checkout-unavailable')
            result = self.run_python(extracted, root/'home', '-m', 'unittest',
                                    'tests.test_cli', 'tests.test_agent_workflow',
                                    'tests.test_skill_install', 'tests.test_lifecycle', '-v')
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            # Runtime installed into a fixture must survive removal of its extracted source too.
            script = r'''import json, os, pathlib, subprocess, sys
from tests.test_lifecycle import LifecycleFixture
f=LifecycleFixture(); f.setUp()
try:
    result=f.install('status','notifications','restore','shell')
    assert not [x for x in result.findings if x.state in {'conflict','unavailable','missing_dependency'}]
    current=f.context.paths.data/'current'
    settings=f.context.paths.config/'runtime.json'
    configured=json.loads(settings.read_text())
    assert configured['status_backend']=='cc-status'
    app=pathlib.Path(configured['iterm2_app'])
    utilities=app/'Contents/Resources/utilities'
    utilities.mkdir(parents=True)
    capture=f.context.paths.home/'native-calls.jsonl'
    trap=f.context.paths.home/'path-fallback'
    fake_path=f.context.paths.home/'fake-path'
    fake_path.mkdir()
    for name in ('cc-status','it2'):
        path=fake_path/name
        path.write_text('#!'+sys.executable+'\nfrom pathlib import Path\nPath('+repr(str(trap))+').touch()\n')
        path.chmod(0o700)
    def replace_utilities(version):
        native=utilities/'cc-status'
        native.write_text('#!'+sys.executable+'\n'+
            'import json, os, pathlib, subprocess, sys\n'+
            'sibling=subprocess.check_output([str(pathlib.Path(__file__).with_name("it2"))],text=True).strip()\n'+
            'record={"version":'+repr(version)+',"sibling":sibling,"argv":sys.argv,"payload":json.load(sys.stdin),'+
            '"terminal":os.environ["TERM_SESSION_ID"],"iterm":os.environ["ITERM_SESSION_ID"]}\n'+
            'with open('+repr(str(capture))+',"a") as stream: stream.write(json.dumps(record)+"\\n")\n')
        native.chmod(0o700)
        sibling=utilities/'it2'
        sibling.write_text('#!'+sys.executable+'\nprint('+repr(version)+')\n')
        sibling.chmod(0o700)
    replace_utilities('before-update')
    runtime_bytes={str(p.relative_to(current)):p.read_bytes() for p in current.rglob('*') if p.is_file()}
    assert not {'cc-status','it2','receipt.json','raw-event.json'} & {pathlib.Path(p).name for p in runtime_bytes}
    assert all(not pathlib.Path(r['target']).is_relative_to(app) for r in result.receipt.resources)
    notices={name: pathlib.Path(name).read_bytes() for name in ('LICENSE','THIRD_PARTY_NOTICES.md')}
    import shutil
    shutil.rmtree(pathlib.Path.cwd())
    for name, expected in notices.items():
        assert (current/name).read_bytes()==expected
    env=dict(os.environ, HOME=str(f.context.paths.home),PATH=str(fake_path),PYTHONPATH='',TMUX='')
    uuid='12345678-1234-1234-1234-123456789abc'
    env['TERM_SESSION_ID']=env['ITERM_SESSION_ID']='w0t0p0:'+uuid
    raw={'hook_event_name':'UserPromptSubmit','session_id':'fixture-session','prompt':'PRIVATE_EVENT_SENTINEL'}
    def invoke():
        r=subprocess.run([sys.executable,str(current/'hook.py'),'--settings',str(settings),'--agent','codex'],
                         input=json.dumps(raw),cwd=f.context.paths.home,env=env,
                         capture_output=True,text=True,timeout=3)
        assert (r.returncode,r.stdout,r.stderr)==(0,'{}\n',''), (r.returncode,r.stdout,r.stderr)
    invoke()
    replace_utilities('after-update')
    invoke()
    calls=[json.loads(line) for line in capture.read_text().splitlines()]
    assert len(calls)==2, calls
    assert [c['version'] for c in calls]==['before-update','after-update']
    assert [c['sibling'] for c in calls]==['before-update','after-update']
    for call in calls:
        assert call['argv']==[str(utilities/'cc-status'),'--agent','codex'], call
        assert call['payload']=={'hook_event_name':'UserPromptSubmit'}, call
        assert call['terminal']==call['iterm']=='w0t0p0:'+uuid.upper()
    for missing in ('cc-status','it2'):
        replace_utilities('unavailable')
        (utilities/missing).unlink()
        invoke()
        assert len(capture.read_text().splitlines())==2
    assert not trap.exists(), 'Native transport searched PATH'
    configured['status']=False
    settings.write_text(json.dumps(configured))
    replace_utilities('disabled')
    invoke()
    assert len(capture.read_text().splitlines())==2
    assert runtime_bytes=={str(p.relative_to(current)):p.read_bytes() for p in current.rglob('*') if p.is_file()}
    for folder in (f.context.paths.config, f.context.paths.cache, f.context.paths.data):
        assert all(b'PRIVATE_EVENT_SENTINEL' not in p.read_bytes() for p in folder.rglob('*') if p.is_file())
    r=subprocess.run([sys.executable,str(current/'codex_restore/codex-sessions'),'--help'],cwd=f.context.paths.home,capture_output=True,text=True)
    assert r.returncode==0, r.stderr
finally:
    f.doCleanups()
'''
            result = self.run_python(extracted, root/'runtime-home', '-c', script)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main()
