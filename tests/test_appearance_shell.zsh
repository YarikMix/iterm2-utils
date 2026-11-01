#!/bin/zsh
# Fake executables at the boundary; the dispatcher and zsh jobs are real.
exec python3 - "$0" <<'PY'
import errno, json, os, pathlib, pty, shutil, subprocess, sys, tempfile, time, unittest
REPO = pathlib.Path(sys.argv[1]).resolve().parents[1]
HELPER = r'''import json, os, pathlib, signal, sys, time
root = pathlib.Path(__file__).parent
args = sys.argv[1:]
phase = args[args.index('--phase')+1]
def log(event):
    with (root/'events').open('a') as out:
        out.write(json.dumps(dict(event=event,phase=phase,args=args,pid=os.getpid()))+'\n')
def finish(*unused):
    log('term'); time.sleep(.04); log('end'); sys.exit(0)
signal.signal(signal.SIGTERM,finish)
log('start')
if (root/'fail').exists():
    print('helper failure',file=sys.stderr); sys.exit(7)
if phase == 'launch':
    if (root/'delay-ready').exists(): time.sleep(1)
    log('ready')
    if '--ready-fd' in args:
        os.write(int(args[args.index('--ready-fd')+1]), b'ready\n')
if (root/'hold').exists() and phase != 'return' or (root/'hold-return').exists() and phase == 'return':
    while True: time.sleep(.01)
time.sleep(.06)
log('end')
'''
CODEX = r'''#!/usr/bin/env python3
import json, os, pathlib, sys, time
root=pathlib.Path(__file__).parent
if (root/'await-launch').exists():
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        rows=[json.loads(line) for line in (root/'events').read_text().splitlines()] if (root/'events').exists() else []
        if any(r['event']=='start' and r['phase']=='launch' for r in rows): break
        time.sleep(.01)
if (root/'finish-launch').exists(): time.sleep(.15)
with (root/'calls').open('a') as out:
    try: os.fstat(int(os.environ.get('TEST_LIFETIME_FD','-1'))); inherited=True
    except OSError: inherited=False
    rows=[json.loads(line) for line in (root/'events').read_text().splitlines()] if (root/'events').exists() else []
    ready=any(r['event']=='ready' and r['phase']=='launch' for r in rows)
    out.write(json.dumps(dict(args=sys.argv[1:],cwd=os.getcwd(),inherited_fd=inherited,appearance_ready=ready))+'\n')
print('native stderr',file=sys.stderr)
sys.exit(42)
'''
class AppearanceShell(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='appearance shell ')
        self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name).resolve()
        for name in ('appearance.zsh','codex.zsh'):
            source=REPO/'runtime'/name
            if source.exists(): shutil.copy(source,self.root/name)
        (self.root/'appearance.py').write_text(HELPER)
        (self.root/'codex').write_text(CODEX); (self.root/'codex').chmod(0o755)
        self.project=self.root/"physical ' $()"; self.project.mkdir()
        self.link=self.root/'linked'; self.link.symlink_to(self.project,target_is_directory=True)
        self.env=dict(os.environ,HOME=str(self.root),PATH=str(self.root)+':/usr/bin:/bin',TERM_PROGRAM='iTerm.app',TEST_ROOT=str(self.root),ITERM2_UTILS_PYTHON=sys.executable,ITERM2_UTILS_APPEARANCE_CONFIG=str(self.root/'installed rules.json'),ITERM2_UTILS_CODEX_NO_DAEMON='1')
    def run_shell(self,body,interactive=True,terminal='iTerm.app',source=True):
        startup='source "$TEST_ROOT/appearance.zsh"; source "$TEST_ROOT/codex.zsh"; ' if source else ''
        p=subprocess.run(['/bin/zsh','-df']+(['-i'] if interactive else [])+['-c',startup+body],env=dict(self.env,TERM_PROGRAM=terminal),cwd=self.link,capture_output=True,text=True,timeout=7)
        self.assertNotIn('no such file',p.stderr)
        return p
    def rows(self,file='events'):
        path=self.root/file
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    def wait_helper(self): return "[[ -z ${_iterm2_utils_appearance_fd-} ]] || { local fixture_discard=''; sysread -i $_iterm2_utils_appearance_fd fixture_discard 2>/dev/null || true; }; "
    def test_startup_once_source_twice_and_cd_does_not_apply(self):
        p=self.run_shell(self.wait_helper()+'source "$TEST_ROOT/appearance.zsh"; cd /; '+self.wait_helper())
        self.assertEqual(p.returncode,0,p.stderr)
        starts=[r for r in self.rows() if r['event']=='start']
        self.assertEqual([r['phase'] for r in starts],['shell'])
        self.assertEqual(starts[0]['args'],['--config',str(self.root/'installed rules.json'),'--cwd',str(self.project),'--phase','shell'])
        self.assertEqual(p.stdout,''); self.assertEqual(p.stderr,'')
    def test_noninteractive_or_other_terminal_do_not_apply(self):
        for interactive,terminal in ((False,'iTerm.app'),(True,'other')):
            p=self.run_shell('codex hello; exit $?',interactive,terminal)
            self.assertEqual(p.returncode,42,p.stderr)
        self.assertEqual(self.rows(),[])
    def test_interactive_variants_keep_argv_exit_stderr_and_physical_cwd(self):
        (self.root/'await-launch').touch(); (self.root/'hold').touch()
        for args in ('hello --cd /elsewhere','resume --last','fork --no-daemon'):
            with self.subTest(args=args):
                (self.root/'events').unlink(missing_ok=True)
                p=self.run_shell('codex '+args+'; result=$?; '+self.wait_helper()+'exit $result')
                self.assertEqual(p.returncode,42,p.stderr)
                self.assertEqual(p.stderr,'native stderr\n'); self.assertEqual(p.stdout,'')
                starts=[r for r in self.rows() if r['event']=='start']
                self.assertEqual([r['phase'] for r in starts][-2:],['launch','return'])
                self.assertTrue(all(r['args'][3]==str(self.project) for r in starts))
                expected=args.split()
                if '--no-daemon' not in expected: expected.insert(0,'--no-daemon')
                self.assertEqual(self.rows('calls')[-1]['args'],expected)
                # A TERM cleanup must fully end before the next helper starts.
                events=self.rows(); launch=next(i for i,r in enumerate(events) if r['event']=='start' and r['phase']=='launch')
                returned=next(i for i,r in enumerate(events) if r['event']=='start' and r['phase']=='return')
                self.assertIn('end',[r['event'] for r in events[launch+1:returned]])
                # Return stays asynchronous; terminate it explicitly in this fixture.
    def test_services_and_help_do_not_apply(self):
        commands=['--help','exec task','review','login','agents','remote-control','app-server','resume --future x']
        p=self.run_shell(self.wait_helper()+'; '.join('codex '+s for s in commands)+'; true')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual([r['phase'] for r in self.rows() if r['event']=='start'],['shell'])
        self.assertEqual([r['args'] for r in self.rows('calls')],[s.split() for s in commands])
    def test_helper_failure_does_not_change_native_result(self):
        (self.root/'fail').touch(); (self.root/'await-launch').touch()
        p=self.run_shell('codex hello; result=$?; '+self.wait_helper()+'exit $result')
        self.assertEqual(p.returncode,42,p.stderr)
        self.assertEqual(p.stdout,''); self.assertEqual(p.stderr,'native stderr\n')
    def test_native_codex_starts_only_after_snapshot_and_observer_are_ready(self):
        (self.root/'delay-ready').touch()
        p=self.run_shell(self.wait_helper()+'codex hello; result=$?; '+self.wait_helper()+'exit $result')
        self.assertEqual(p.returncode,42,p.stderr)
        self.assertTrue(self.rows('calls')[-1]['appearance_ready'])
    def test_snapshot_launch_identity_changes_and_is_shared_with_its_return(self):
        p=self.run_shell(self.wait_helper()+'codex first; '+self.wait_helper()+'codex second; '+self.wait_helper())
        self.assertEqual(p.returncode,0,p.stderr)
        phases=[r for r in self.rows() if r['event']=='start' and r['phase']!='shell']
        identifiers=[r['args'][r['args'].index('--launch-id')+1] if '--launch-id' in r['args'] else None for r in phases]
        self.assertEqual(len(identifiers),4)
        self.assertIsNotNone(identifiers[0])
        self.assertEqual(identifiers[0],identifiers[1])
        self.assertEqual(identifiers[2],identifiers[3])
        self.assertNotEqual(identifiers[0],identifiers[2])
    def test_finished_helper_is_reaped_without_signaling_another_job(self):
        (self.root/'await-launch').touch(); (self.root/'finish-launch').touch()
        p=self.run_shell(self.wait_helper()+"function TRAPDEBUG { [[ $ZSH_DEBUG_CMD == 'builtin kill -TERM '* ]] && print -r -- $ZSH_DEBUG_CMD >> \"$TEST_ROOT/signals\"; return 0; }; sleep 1 & unrelated=$!; codex hello; result=$?; "+self.wait_helper()+'wait $unrelated; exit $result')
        self.assertEqual(p.returncode,42,p.stderr)
        self.assertFalse((self.root/'signals').exists(),(self.root/'signals').read_text() if (self.root/'signals').exists() else '')
        self.assertEqual([r['phase'] for r in self.rows() if r['event']=='term'],[])
    def test_nested_shell_does_not_inherit_helper_ownership_or_bootstrap_marker(self):
        p=self.run_shell(self.wait_helper()+"/bin/zsh -dfi -c 'source \"$TEST_ROOT/appearance.zsh\"; sysread -i $_iterm2_utils_appearance_fd fixture_discard 2>/dev/null || true'")
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual([r['phase'] for r in self.rows() if r['event']=='start'],['shell','shell'])
    def test_subshell_does_not_cancel_the_parent_helper(self):
        (self.root/'hold').touch()
        p=self.run_shell('sleep .08; (_iterm2_utils_appearance return "$PWD"; '+self.wait_helper()+'); _iterm2_utils_appearance return "$PWD"; '+self.wait_helper())
        self.assertEqual(p.returncode,0,p.stderr)
        events=self.rows()
        first_return_end=next(i for i,r in enumerate(events) if r['event']=='end' and r['phase']=='return')
        parent_term=next(i for i,r in enumerate(events) if r['event']=='term' and r['phase']=='shell')
        self.assertLess(first_return_end,parent_term)
    def test_caller_job_options_are_preserved(self):
        # MONITOR needs a controlling TTY; this PTY uses only fixture executables.
        for monitored in (True,False):
            script=('setopt ' if monitored else 'unsetopt ')+'monitor; setopt bgnice notify; source "$TEST_ROOT/appearance.zsh"; '+self.wait_helper()+'print -r -- "$options[bgnice]:$options[monitor]:$options[notify]"'
            pid,fd=pty.fork()
            if pid==0:
                os.chdir(self.project)
                os.execve('/bin/zsh',['/bin/zsh','-dfi','-c',script],self.env)
            output=b''
            try:
                while True:
                    try: chunk=os.read(fd,4096)
                    except OSError as error:
                        if error.errno==errno.EIO: break
                        raise
                    if not chunk: break
                    output+=chunk
            finally:
                os.close(fd)
                _,status=os.waitpid(pid,0)
            self.assertEqual(os.waitstatus_to_exitcode(status),0,output)
            self.assertEqual(output.decode().replace('\r\n','\n'),'on:'+('on' if monitored else 'off')+':on\n')
    def test_restore_picker_reaches_dispatcher_and_keeps_status(self):
        shutil.copy(REPO/'runtime/codex_restore/codex-resume.zsh',self.root/'codex-resume.zsh')
        (self.root/'await-launch').touch(); (self.root/'fail').touch()
        sid='11111111-1111-4111-8111-111111111111'
        sessions="""import json, pathlib, sys
root=pathlib.Path(__file__).parent
with (root/'restore-calls').open('a') as out: out.write(json.dumps(dict(args=sys.argv[1:]))+'\\n')
if sys.argv[1]=='register': print('restore-token')
elif sys.argv[1]=='restore-list': print('row')
elif sys.argv[1]=='restore-open':
    fields=['22222222-2222-4222-8222-222222222222','11111111-1111-4111-8111-111111111111',str(root/"physical ' $()"),str(root/'restore-home'),str(root/'restore-cache'),'']
    sys.stdout.buffer.write(bytes([0]).join(field.encode() for field in fields))
"""
        (self.root/'codex-sessions').write_text(sessions)
        (self.root/'fzf').write_text('#!/bin/sh\ncat >/dev/null\nprintf "%s\\n" '+sid+'\n'); (self.root/'fzf').chmod(0o755)
        self.env['ITERM_SESSION_ID']='w1t1p0:'+sid
        p=self.run_shell(self.wait_helper()+'typeset -g _codex_restore_no_daemon=1; source "$TEST_ROOT/codex-resume.zsh"; source "$TEST_ROOT/codex.zsh"; source "$TEST_ROOT/codex-resume.zsh"; codex resume --restore; result=$?; '+self.wait_helper()+'exit $result')
        self.assertEqual(p.returncode,42,p.stderr)
        self.assertEqual(p.stderr,'native stderr\n'); self.assertEqual(p.stdout,'')
        self.assertEqual(self.rows('calls')[-1]['args'],['--no-daemon','resume',sid])
        self.assertEqual([r['args'][0] for r in self.rows('restore-calls')],['restore-list','restore-open','register','finish'])
        self.assertEqual([r['phase'] for r in self.rows() if r['event']=='start'],['shell','launch','return'])
    def test_fd_setup_failure_does_not_signal_a_finished_helper(self):
        p=self.run_shell("function sysopen { sleep .15; return 1; }; function TRAPDEBUG { [[ $ZSH_DEBUG_CMD == 'builtin kill -TERM '* ]] && print signal >> \"$TEST_ROOT/signals\"; return 0; }; source \"$TEST_ROOT/appearance.zsh\"",source=False)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertFalse((self.root/'signals').exists())
    def test_lifetime_fd_is_not_inherited_by_native_codex(self):
        p=self.run_shell(self.wait_helper()+'export TEST_LIFETIME_FD=$_iterm2_utils_appearance_fd; command codex probe')
        self.assertEqual(p.returncode,42,p.stderr)
        self.assertFalse(self.rows('calls')[-1]['inherited_fd'])
    def test_finished_children_are_reaped(self):
        (self.root/'await-launch').touch(); (self.root/'hold').touch()
        # Keep this same interactive shell alive after EOF, so exit cannot reap zombies.
        script='source "$TEST_ROOT/appearance.zsh"; source "$TEST_ROOT/codex.zsh"; codex hello; '+self.wait_helper()+'print ready > "$TEST_ROOT/reap-ready"; read fixture_release'
        p=subprocess.Popen(['/bin/zsh','-dfi','-c',script],env=self.env,cwd=self.link,
                           stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+4
            while not (self.root/'reap-ready').exists() and time.monotonic()<deadline:
                self.assertIsNone(p.poll()); time.sleep(.01)
            self.assertTrue((self.root/'reap-ready').exists())
            pids={r['pid'] for r in self.rows()}
            self.assertGreaterEqual(len(pids),2)
            for pid in pids:
                while time.monotonic()<deadline:
                    try: os.kill(pid,0)
                    except ProcessLookupError: break
                    time.sleep(.01)
                with self.assertRaises(ProcessLookupError): os.kill(pid,0)
            self.assertIsNone(p.poll(), 'Parent zsh must still be alive during assertions')
            out,err=p.communicate('release\n',timeout=3)
            self.assertEqual(p.returncode,0,err)
        finally:
            if p.poll() is None: p.kill()
            p.communicate(timeout=3)
    def test_return_observer_is_in_background(self):
        (self.root/'await-launch').touch(); (self.root/'hold').touch(); (self.root/'hold-return').touch()
        # Mark the shell's return before draining a bounded fake return helper.
        p=self.run_shell('codex hello; result=$?; print returned; sleep .08; builtin kill -TERM $_iterm2_utils_appearance_pid; '+self.wait_helper()+'exit $result')
        self.assertEqual(p.returncode,42,p.stderr)
        self.assertEqual(p.stdout,'returned\n')
        self.assertIn('return',[r['phase'] for r in self.rows() if r['event']=='start'])

if __name__=='__main__': unittest.main(argv=[sys.argv[0]],verbosity=2)
PY
