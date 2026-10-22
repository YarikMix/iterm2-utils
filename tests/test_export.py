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

from tools import build_release, check_export

ROOT = Path(__file__).resolve().parents[1]


class ExportTests(unittest.TestCase):
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
                         'logs/transcript.jsonl', 'auth/token', 'runtime/__pycache__/secret.pyc'):
                path = repo/name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((b'PRIVATE_' + b'FIXTURE_MARKER'))
            archive = build_release.build(repo, root/'dist')
            self.assertNotIn((b'PRIVATE_' + b'FIXTURE_MARKER'), archive.read_bytes())
            with tarfile.open(archive) as tar:
                members = tar.getmembers()
                names = {m.name.split('/', 1)[1] for m in members if '/' in m.name}
                self.assertIn('skills/iterm2-setup/SKILL.md', names)
                self.assertIn('vendor/codex_status/LICENSE', names)
                for member in members:
                    self.assertTrue(member.isfile())
                    self.assertNotIn((b'PRIVATE_' + b'FIXTURE_MARKER'), tar.extractfile(member).read())
                self.assertEqual(names, set(check_export.EXPORT_FILES))
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
                'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': ''}

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
            script = '''import json, pathlib, subprocess, sys
from tests.test_lifecycle import LifecycleFixture
f=LifecycleFixture(); f.setUp()
try:
    result=f.install('status','notifications','restore','shell')
    assert not [x for x in result.findings if x.state in {'conflict','unavailable','missing_dependency'}]
    current=f.context.paths.data/'current'
    notices={name: pathlib.Path(name).read_bytes() for name in ('LICENSE','THIRD_PARTY_NOTICES.md')}
    import shutil
    shutil.rmtree(pathlib.Path.cwd())
    for name, expected in notices.items():
        assert (current/name).read_bytes()==expected
    smoke = """import importlib, pathlib
for path in pathlib.Path('.').rglob('*.py'):
    importlib.import_module('.'.join(path.with_suffix('').parts))
from events import normalize
from hook import dispatch
class Runner:
    def __init__(self): self.calls=[]
    def run(self,argv,**kwargs):
        from subprocess import CompletedProcess
        self.calls.append(argv)
        return CompletedProcess(argv,0,'','')
r=Runner()
e=normalize({'hook_event_name':'UserPromptSubmit','session_id':'fixture-session'},'codex','w0t0p0:12345678-1234-1234-1234-123456789abc')
assert e is not None
import tempfile
with tempfile.TemporaryDirectory() as cache:
    dispatch(e,{'status':True,'it2':'fixture-it2','cache':cache},r)
assert r.calls, 'Installed dispatcher did not reach fake transport'
"""
    r=subprocess.run([sys.executable,'-c',smoke],cwd=current,capture_output=True,text=True)
    assert r.returncode==0, r.stdout+r.stderr
    r=subprocess.run([sys.executable,str(current/'codex_restore/codex-sessions'),'--help'],cwd=f.context.paths.home,capture_output=True,text=True)
    assert r.returncode==0, r.stderr
finally:
    f.doCleanups()
'''
            result = self.run_python(extracted, root/'runtime-home', '-c', script)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main()
