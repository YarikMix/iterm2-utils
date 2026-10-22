import json
import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from iterm2_utils import state
from iterm2_utils.models import Receipt, Selection


class StateTests(unittest.TestCase):
    def test_unknown_or_corrupt_receipt_is_not_ownership(self):
        with TemporaryDirectory() as root:
            path = Path(root)/'receipt.json'
            for raw in ('{broken', '{"version":"999","resources":[]}', '{"version":"1","resources":[{}]}'):
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    state.load(path)
            self.assertIsNone(state.load(Path(root)/'missing'))

    def test_private_roundtrip(self):
        with TemporaryDirectory() as root:
            path = Path(root)/'state'/'receipt.json'
            receipt = Receipt('1',Selection(frozenset({'codex'}),frozenset({'clipboard'}),frozenset(),'Default'),[],[])
            state.save(path,receipt)
            self.assertEqual(state.load(path), receipt)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode),0o700)

    def test_corrupt_resource_payload_is_rejected(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'receipt.json'
            raw={'version':'1','selection':{'agents':['codex'],'features':['clipboard'],'shortcuts':[],'parent_profile':'Default','adopt_legacy':False},'resources':[{'kind':'file','target':str(Path(root)/'target'),'locator':{'mode':384},'before':{'exists':False,'value':None},'installed':{'exists':True,'value':'NOT VALID BASE64'},'owners':['clipboard'],'version':'1'}],'pending_ui':[]}
            path.write_text(json.dumps(raw))
            with self.assertRaises(ValueError):
                state.load(path)
