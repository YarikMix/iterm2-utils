import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from iterm2_utils.models import *
from iterm2_utils.features.profiles import build

class ProfileTests(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory(); self.addCleanup(t.cleanup); p=Path(t.name)
        self.context=Context(Paths(p,p/'zshrc',p/'codex',p/'claude.json',p/'config',p/'cache',p/'data',p/'profiles',p),{}, {},frozenset({'codex:alt-enter','claude:alt-enter'}),{'Default':{'Name':'Default','Guid':'parent','Keyboard Map':{'custom':{'Action':12,'Text':'x'}}}}, {})
    def selection(self,features=('clipboard',),agents=('codex',),shortcuts=()):
        return Selection(frozenset(agents),frozenset(features),frozenset(shortcuts),'Default')
    def profiles(self,changes):
        return json.loads(next(e.after for e in changes.edits if isinstance(e,FileEdit) and e.path.suffix=='.json'))['Profiles']
    def test_copy_sequences_exactly_one_command(self):
        p=self.profiles(build(self.context,self.selection()))[0]
        self.assertEqual(p['Bound Hosts'],['&codex'])
        for char in ('0x63','0x441'):
            self.assertEqual(p['Keyboard Map'][char+'-0x40000-0x8-0x1'],{'Action':11,'Text':'0x03'})
            self.assertEqual(p['Keyboard Map'][char+'-0x100000-0x8-0x1'],{'Action':11,'Text':'0x1b 0x5b 0x39 0x39 0x3b 0x39 0x75'})
        self.assertNotIn('Command',p)
    def test_hotkeys_only_does_not_disable_copy_on_select(self):
        c=build(self.context,self.selection(('shortcuts',),shortcuts=('resume',)))
        self.assertFalse(any(isinstance(e,PreferenceEdit) for e in c.edits))
        p=self.profiles(c)[0]; self.assertNotIn('0x63-0x40000-0x8-0x1',p['Keyboard Map'])
        self.assertEqual(p['Keyboard Map']['0x52-0x120000-0xf-0x1']['Text'].encode(),b'/resume'+bytes([10]))
    def test_existing_parent_keyboard_map_preserved(self):
        self.assertEqual(self.profiles(build(self.context,self.selection()))[0]['Keyboard Map']['custom'],{'Action':12,'Text':'x'})
    def test_parent_binding_conflict_requires_choice(self):
        self.context.profiles['Default']['Keyboard Map']['0x63-0x40000-0x8-0x1']={'Action':12,'Text':'foreign'}
        c=build(self.context,self.selection()); self.assertTrue(any(f.code=='binding_conflict' for f in c.findings)); self.assertEqual(c.edits,[])
    def test_codex_rule_not_applied_to_claude(self):
        ps=self.profiles(build(self.context,self.selection(('clipboard','shortcuts'),('codex','claude'),('ctrl-q',))))
        self.assertEqual([p['Bound Hosts'] for p in ps],[['&claude'],['&codex']])
        self.assertNotIn('0x63-0x40000-0x8-0x1',ps[0]['Keyboard Map'])
    def test_custom_codex_profile_override_is_reported(self):
        p=self.context.paths.codex_home; p.mkdir(); (p/'config.toml').write_text('[profiles.custom.tui]\ncopy_on_select="always"\n')
        c=build(self.context,self.selection()); self.assertTrue(any(f.code=='profile_copy_override' for f in c.findings))
    def test_shortcut_capability_mismatch_keeps_other_bindings(self):
        self.context.capabilities=frozenset()
        c=build(self.context,self.selection(('shortcuts',),shortcuts=('alt-enter','ctrl-q')))
        keys=self.profiles(c)[0]['Keyboard Map']
        self.assertNotIn('0xd-0x20000-0x24-0x1',keys)
        self.assertIn('0x71-0x40000-0xc-0x1',keys)
        self.assertTrue(any(f.code=='shortcut_capability' and f.state=='unavailable' for f in c.findings))
    def test_aps_conflicts(self):
        self.context.profiles['other']={'Bound Hosts':['&*']}
        self.assertEqual(build(self.context,self.selection()).edits,[])
        del self.context.profiles['other']
        self.context.profiles['Default']['Prevent Automatic Profile Switching']=True
        self.assertEqual(build(self.context,self.selection()).edits,[])
    def test_install_update_uninstall_profile_roundtrip(self):
        from iterm2_utils import engine
        from unittest.mock import patch
        prefs={'CopySelection':True}
        self.context.preferences={'com.googlecode.iterm2':dict(prefs)}
        def read(runner,domain,key): return {'exists':key in prefs,'value':prefs.get(key)}
        def write(runner,domain,key,value):
            if value['exists']: prefs[key]=value['value']
            else: prefs.pop(key,None)
        selection=self.selection(('clipboard','shortcuts'),shortcuts=('ctrl-q',))
        parent=dict(self.context.profiles['Default'])
        with patch('iterm2_utils.engine.preferences.read',side_effect=read), patch('iterm2_utils.engine.preferences.write',side_effect=write):
            first=engine.apply(Plan(selection,build(self.context,selection),'fixture'),self.context,None)
            self.assertFalse(first.findings)
            second=engine.apply(Plan(selection,build(self.context,selection),'fixture'),self.context,None)
            self.assertFalse(second.findings)
            self.assertEqual(first.receipt.resources,second.receipt.resources)
            partial=engine.revert(second.receipt,self.context,None,frozenset({'clipboard'}))
            self.assertFalse(partial.findings)
            path=self.context.paths.profiles/'iterm2-utils.json'
            self.assertTrue(path.exists()); self.assertTrue(prefs['CopySelection'])
            final=engine.revert(partial.receipt,self.context,None,frozenset({'shortcuts'}))
            self.assertFalse(final.findings)
            self.assertEqual(final.receipt.resources,[])
            self.assertEqual(self.context.profiles['Default'],parent)
            self.assertFalse(path.exists())
    def test_exact_selected_shortcuts_only(self):
        c=build(self.context,self.selection(('shortcuts',),('codex','claude'),('ctrl-v-ru','alt-enter')))
        for profile in self.profiles(c):
            self.assertEqual(profile['Keyboard Map']['0x43c-0x40000-0x9-0x1'],{'Action':11,'Text':'0x16'})
            self.assertEqual(profile['Keyboard Map']['0xd-0x20000-0x24-0x1'],{'Action':11,'Text':'0x1b 0x0d'})
            self.assertNotIn('0x71-0x40000-0xc-0x1',profile['Keyboard Map'])
            self.assertNotIn('0x52-0x120000-0xf-0x1',profile['Keyboard Map'])
    def test_planner_composes_profile_edits(self):
        from iterm2_utils.planner import plan
        self.context.executables={name:self.context.paths.home/name for name in ('codex','iterm2','zsh')}
        self.context.capabilities=frozenset({'macos'})
        result=plan(self.context,self.selection())
        self.assertTrue(result.changes.edits)
        self.assertEqual(result.changes.consumers,{'shared:agent-profiles':frozenset({'clipboard'})})
    def test_rebuild_remaining_shortcuts_removes_copy_bindings(self):
        original=self.selection(('clipboard','shortcuts'),shortcuts=('ctrl-q',))
        both=build(self.context,original)
        path=self.context.paths.profiles/'iterm2-utils.json'; path.parent.mkdir(); path.write_bytes(next(e.after for e in both.edits if isinstance(e,FileEdit) and e.path==path))
        remaining=build(self.context,self.selection(('shortcuts',),shortcuts=('ctrl-q',)))
        profile=self.profiles(remaining)[0]
        self.assertNotIn('0x63-0x40000-0x8-0x1',profile['Keyboard Map'])
        self.assertIn('0x71-0x40000-0xc-0x1',profile['Keyboard Map'])
        self.assertEqual(profile['Keyboard Map']['custom'],{'Action':12,'Text':'x'})
        self.assertEqual(remaining.consumers,{'shared:agent-profiles':frozenset({'shortcuts'})})
