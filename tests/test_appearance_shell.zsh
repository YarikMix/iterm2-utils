#!/bin/zsh
# Fake executables at the boundary; the dispatcher and zsh jobs are real.
exec python3 - "$0" "$@" <<'PY'
import errno, json, os, pathlib, pty, select, shutil, subprocess, sys, tempfile, time, unittest
REPO = pathlib.Path(sys.argv[1]).resolve().parents[1]
HELPER = r'''import json, os, pathlib, select, signal, sys, time
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
(root/('started-'+str(os.getpid()))).touch()
if phase == 'shell' and (root/'hold-first-shell').exists():
    try: (root/'held-shell').mkdir()
    except FileExistsError: pass
    else:
        with (root/'release-shell').open('rb', buffering=0) as release:
            if not select.select([release], [], [], 3)[0]: sys.exit(8)
            release.read(1)
if (root/'fail').exists():
    print('helper failure',file=sys.stderr); sys.exit(7)
if phase == 'launch':
    if (root/'delay-ready').exists(): time.sleep(1)
    log('ready')
    if '--ready-fd' in args:
        os.write(int(args[args.index('--ready-fd')+1]), b'ready\n')
if (root/'hold-launch').exists() and phase == 'launch' or (root/'hold-return').exists() and phase == 'return':
    while True: time.sleep(.01)
time.sleep(.06)
if phase == 'shell': (root/'appearance-state').write_text(args[args.index('--cwd')+1])
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
        self.subdir=self.project/'subdir'; self.subdir.mkdir()
        self.other=self.root/'B'; self.other.mkdir()
        self.outside=self.root/'outside'; self.outside.mkdir()
        self.env=dict(os.environ,HOME=str(self.root),PATH=str(self.root)+':/usr/bin:/bin',TERM_PROGRAM='iTerm.app',TEST_ROOT=str(self.root),ITERM2_UTILS_PYTHON=sys.executable,ITERM2_UTILS_APPEARANCE_CONFIG=str(self.root/'installed rules.json'),ITERM2_UTILS_CODEX_NO_DAEMON='1',TMUX='')
    def run_shell(self,body,interactive=True,terminal='iTerm.app',source=True):
        startup='source "$TEST_ROOT/appearance.zsh"; source "$TEST_ROOT/codex.zsh"; ' if source else ''
        p=subprocess.run(['/bin/zsh','-df']+(['-i'] if interactive else [])+['-c',startup+body],env=dict(self.env,TERM_PROGRAM=terminal),cwd=self.link,capture_output=True,text=True,timeout=7)
        self.assertNotIn('no such file',p.stderr)
        return p
    def rows(self,file='events'):
        path=self.root/file
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    def wait_helper(self): return "[[ -z ${_iterm2_utils_appearance_fd-} ]] || { local fixture_discard=''; sysread -i $_iterm2_utils_appearance_fd fixture_discard 2>/dev/null || true; }; "
    def test_startup_once_source_twice_and_cd_applies_physical_cwd(self):
        self.env.pop('TMUX')
        body=self.wait_helper()+'source "$TEST_ROOT/appearance.zsh"; '
        for destination in ('outside','linked','linked/subdir','B','outside'):
            body+='builtin cd "$TEST_ROOT/'+destination+'"; '+self.wait_helper()
        body+='(( ${#chpwd_functions} == 1 )) && [[ $chpwd_functions[1] == _iterm2_utils_appearance_chpwd ]]'
        p=self.run_shell(body)
        self.assertEqual(p.returncode,0,p.stderr)
        starts=[r for r in self.rows() if r['event']=='start']
        expected=[self.project,self.outside,self.project,self.subdir,self.other,self.outside]
        self.assertEqual([r['phase'] for r in starts],['shell']*6)
        self.assertEqual([r['args'] for r in starts],[['--config',str(self.root/'installed rules.json'),'--cwd',str(cwd),'--phase','shell'] for cwd in expected])
        self.assertEqual(p.stdout,''); self.assertEqual(p.stderr,'')
    def test_chpwd_preserves_foreign_function_hooks_and_cd_status(self):
        (self.root/'fail').touch()
        p=self.run_shell('function chpwd { print foreign-function; }; function fixture_chpwd { print foreign-hook; }; autoload -Uz add-zsh-hook; add-zsh-hook chpwd fixture_chpwd; source "$TEST_ROOT/appearance.zsh"; '+self.wait_helper()+'source "$TEST_ROOT/appearance.zsh"; builtin cd "$TEST_ROOT/B"; result=$?; '+self.wait_helper()+'exit $result',source=False)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(p.stdout,'foreign-function\nforeign-hook\n'); self.assertEqual(p.stderr,'')
        starts=[r for r in self.rows() if r['event']=='start']
        self.assertEqual([r['phase'] for r in starts],['shell','shell'])
        self.assertEqual([r['args'][3] for r in starts],[str(self.project),str(self.other)])
    def test_inherited_chpwd_does_not_recolor_parent_from_subprocess(self):
        p=self.run_shell(self.wait_helper()+'(builtin cd "$TEST_ROOT/B"; source "$TEST_ROOT/appearance.zsh"); captured=$(builtin cd "$TEST_ROOT/B"); [[ -z $captured ]] || exit 91; /bin/zsh -df -c \'source "$TEST_ROOT/appearance.zsh"; builtin cd "$TEST_ROOT/B"\'; '+self.wait_helper())
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual([r['phase'] for r in self.rows() if r['event']=='start'],['shell'])
        self.assertEqual(p.stdout,''); self.assertEqual(p.stderr,'')
    def test_noninteractive_or_other_terminal_or_tmux_do_not_apply(self):
        for interactive,terminal,tmux in ((False,'iTerm.app',''),(True,'other',''),(True,'iTerm.app','fixture-tmux')):
            self.env['TMUX']=tmux
            p=self.run_shell('builtin cd "$TEST_ROOT/B"; codex hello; exit $?',interactive,terminal)
            self.assertEqual(p.returncode,42,p.stderr)
        self.assertEqual(self.rows(),[])
    def test_empty_tmux_does_not_disable_chpwd(self):
        self.env['TMUX']=''
        p=self.run_shell(self.wait_helper()+'builtin cd "$TEST_ROOT/B"; '+self.wait_helper())
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual([r['args'][3] for r in self.rows() if r['event']=='start'],[str(self.project),str(self.other)])
    def test_interactive_variants_keep_argv_exit_stderr_and_physical_cwd(self):
        (self.root/'await-launch').touch(); (self.root/'hold-launch').touch()
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
    def test_allexport_keeps_private_state_and_fresh_child_owner_independent(self):
        child=self.root/'child.zsh'
        child.write_text('''[[ -z ${(k)parameters[(I)_iterm2_utils_appearance_*]} ]] || exit 91
setopt allexport
source "$TEST_ROOT/appearance.zsh"
source "$TEST_ROOT/appearance.zsh"
builtin cd "$TEST_ROOT/B"
[[ $options[allexport] == on && $_iterm2_utils_appearance_hook_owner == $sysparams[pid] ]] || exit 92
(( ${#chpwd_functions} == 1 )) || exit 93
print child:$sysparams[pid]
''')
        p=self.run_shell('''setopt allexport
source "$TEST_ROOT/appearance.zsh"
source "$TEST_ROOT/appearance.zsh"
/bin/zsh -dfi "$TEST_ROOT/child.zsh" || exit $?
[[ $options[allexport] == on && $_iterm2_utils_appearance_hook_owner == $sysparams[pid] ]] || exit 94
(( ${#chpwd_functions} == 1 )) || exit 95
for name in ${(k)parameters[(I)_iterm2_utils_appearance_*]}; do
  [[ $parameters[$name] != *export* ]] || exit 96
done
print parent:$sysparams[pid]
''',source=False)
        self.assertEqual(p.returncode,0,p.stderr)
        owners=p.stdout.splitlines()
        self.assertEqual(len(owners),2)
        self.assertNotEqual(owners[0].split(':')[1],owners[1].split(':')[1])
        starts=[r for r in self.rows() if r['event']=='start']
        self.assertEqual([r['args'][3] for r in starts],[str(self.project),str(self.project),str(self.other)])
        self.assertEqual(p.stderr,'')
    def test_parent_shell_completion_precedes_fresh_child_target(self):
        for trigger in ('startup','cd'):
            for target in ('B','outside'):
                with self.subTest(trigger=trigger,target=target):
                    for name in ('events','appearance-state','hold-first-shell'):
                        (self.root/name).unlink(missing_ok=True)
                    if (self.root/'held-shell').exists(): (self.root/'held-shell').rmdir()
                    fifo=self.root/'release-shell'
                    if not fifo.exists(): os.mkfifo(fifo)
                    release=os.open(fifo,os.O_RDWR|os.O_NONBLOCK)
                    if trigger=='startup': (self.root/'hold-first-shell').touch()
                    child=self.root/'child.zsh'
                    child.write_text('source "$TEST_ROOT/appearance.zsh"; builtin cd "$TEST_ROOT/'+target+'"; print child-target; read fixture_release')
                    script='source "$TEST_ROOT/appearance.zsh"; '
                    if trigger=='cd': script+='touch "$TEST_ROOT/hold-first-shell"; builtin cd "$TEST_ROOT/B"; '
                    script+='print parent-released; /bin/zsh -dfi "$TEST_ROOT/child.zsh"'
                    p=subprocess.Popen(['/bin/zsh','-dfi','-c',script],env=self.env,cwd=self.link,
                                       stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                    try:
                        deadline=time.monotonic()+3
                        while not (self.root/'held-shell').exists() and time.monotonic()<deadline:
                            self.assertIsNone(p.poll()); time.sleep(.01)
                        self.assertTrue((self.root/'held-shell').exists())
                        # The writer is explicitly held: neither source nor cd may release its caller.
                        premature=bool(select.select([p.stdout],[],[],.15)[0])
                        os.write(release,b'x')
                        self.assertTrue(select.select([p.stdout],[],[],4)[0])
                        first=p.stdout.readline()
                        second=p.stdout.readline()
                        self.assertIsNone(p.poll(),'Fresh child must remain alive at final-target check')
                        self.assertEqual((self.root/'appearance-state').read_text(),str(self.root/target))
                        out,err=p.communicate('release\n',timeout=4)
                        self.assertEqual(p.returncode,0,err)
                        self.assertFalse(premature,'Parent released caller while its shell writer was held')
                        self.assertEqual(first+second+out,'parent-released\nchild-target\n'); self.assertEqual(err,'')
                        self.assertEqual((self.root/'appearance-state').read_text(),str(self.root/target))
                        events=self.rows()
                        starts=[(i,r) for i,r in enumerate(events) if r['event']=='start']
                        self.assertEqual(len(starts),3 if trigger=='startup' else 4)
                        for n,(index,row) in enumerate(starts):
                            following=starts[n+1][0] if n+1<len(starts) else len(events)
                            self.assertEqual([r['event'] for r in events[index+1:following] if r['pid']==row['pid']],['end'])
                    finally:
                        os.close(release)
                        if p.poll() is None: p.kill()
                        p.communicate(timeout=4)
    def test_subshell_does_not_cancel_the_parent_helper(self):
        (self.root/'hold-launch').touch()
        p=self.run_shell('_iterm2_utils_appearance launch "$PWD"; (_iterm2_utils_appearance return "$PWD"; '+self.wait_helper()+'); _iterm2_utils_appearance return "$PWD"; '+self.wait_helper())
        self.assertEqual(p.returncode,0,p.stderr)
        events=self.rows()
        first_return_end=next(i for i,r in enumerate(events) if r['event']=='end' and r['phase']=='return')
        parent_term=next(i for i,r in enumerate(events) if r['event']=='term' and r['phase']=='launch')
        self.assertLess(first_return_end,parent_term)
    def test_caller_job_options_are_preserved(self):
        # MONITOR needs a controlling TTY; this PTY uses only fixture executables.
        for monitored in (True,False):
            script=('setopt ' if monitored else 'unsetopt ')+'monitor; setopt bgnice notify; source "$TEST_ROOT/appearance.zsh"; '+self.wait_helper()+'builtin cd "$TEST_ROOT/B"; '+self.wait_helper()+'print -r -- "$options[bgnice]:$options[monitor]:$options[notify]"'
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
        self.assertEqual([r['phase'] for r in self.rows() if r['event']=='start'],['shell','shell','launch','return'])
    def test_fd_setup_failure_does_not_signal_a_finished_helper(self):
        p=self.run_shell("function sysopen { sleep .15; return 1; }; function TRAPDEBUG { [[ $ZSH_DEBUG_CMD == 'builtin kill -TERM '* ]] && print signal >> \"$TEST_ROOT/signals\"; return 0; }; source \"$TEST_ROOT/appearance.zsh\"",source=False)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertFalse((self.root/'signals').exists())
    def test_lifetime_fd_is_not_inherited_by_native_codex(self):
        p=self.run_shell(self.wait_helper()+'export TEST_LIFETIME_FD=$_iterm2_utils_appearance_fd; command codex probe')
        self.assertEqual(p.returncode,42,p.stderr)
        self.assertFalse(self.rows('calls')[-1]['inherited_fd'])
    def test_finished_children_are_reaped(self):
        (self.root/'await-launch').touch(); (self.root/'hold-launch').touch()
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
    def test_rapid_cd_and_return_observer_leave_only_latest_writer(self):
        (self.root/'hold-launch').touch(); (self.root/'hold-return').touch()
        started='until [[ -e "$TEST_ROOT/started-$_iterm2_utils_appearance_pid" ]]; do sleep .01; done; '
        script='source "$TEST_ROOT/appearance.zsh"; source "$TEST_ROOT/codex.zsh"; '
        script+='builtin cd "$TEST_ROOT/B"; builtin cd "$TEST_ROOT/outside"; '
        script+='codex hello; '+started+'builtin cd "$TEST_ROOT/linked"; builtin cd "$TEST_ROOT/outside"; '
        script+='print ready > "$TEST_ROOT/order-ready"; read fixture_release'
        p=subprocess.Popen(['/bin/zsh','-dfi','-c',script],env=self.env,cwd=self.link,
                           stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+5
            while not (self.root/'order-ready').exists() and time.monotonic()<deadline:
                self.assertIsNone(p.poll()); time.sleep(.01)
            self.assertTrue((self.root/'order-ready').exists())
            events=self.rows(); starts=[(i,r) for i,r in enumerate(events) if r['event']=='start']
            self.assertEqual([r['phase'] for _,r in starts],['shell','shell','shell','launch','return','shell','shell'])
            self.assertEqual([r['args'][3] for _,r in starts],[str(self.project),str(self.other),str(self.outside),str(self.outside),str(self.outside),str(self.project),str(self.outside)])
            for n,(index,row) in enumerate(starts):
                next_start=starts[n+1][0] if n+1<len(starts) else len(events)
                self.assertEqual([r['event'] for r in events[index+1:next_start] if r['pid']==row['pid'] and r['event'] in ('term','end')],['end'] if row['phase']=='shell' else ['term','end'])
                while time.monotonic()<deadline:
                    try: os.kill(row['pid'],0)
                    except ProcessLookupError: break
                    time.sleep(.01)
                with self.assertRaises(ProcessLookupError): os.kill(row['pid'],0)
            self.assertIsNone(p.poll(),'Parent zsh must remain alive')
            time.sleep(.1)
            self.assertEqual(self.rows(),events,'No writer may append after final cleanup')
            out,err=p.communicate('release\n',timeout=3)
            self.assertEqual(p.returncode,0,err)
            self.assertEqual(out,''); self.assertEqual(err,'native stderr\n')
        finally:
            if p.poll() is None: p.kill()
            p.communicate(timeout=3)
    def test_shell_deadline_reaps_worker_and_preserves_successful_cd(self):
        helper='''import json, os, pathlib, signal, sys
root=pathlib.Path(__file__).parent
if '--worker' in sys.argv:
    json.load(sys.stdin)
    (root/'deadline-worker').write_text(str(os.getpid()))
    signal.pause()
else:
    sys.path.insert(0, REPO_PATH)
    from runtime import appearance
    appearance.__file__=__file__
    result=appearance._supervise({'phase':'shell'},dict(os.environ))
    (root/'deadline-result').write_text(result)
'''.replace('REPO_PATH',repr(str(REPO)))
        (self.root/'appearance.py').write_text(helper)
        started=time.monotonic()
        p=self.run_shell('''config=$ITERM2_UTILS_APPEARANCE_CONFIG
ITERM2_UTILS_APPEARANCE_CONFIG=''
source "$TEST_ROOT/appearance.zsh"
ITERM2_UTILS_APPEARANCE_CONFIG=$config
builtin cd "$TEST_ROOT/B"
result=$?
[[ -f "$TEST_ROOT/deadline-result" ]] || exit 91
exit $result
''',source=False)
        elapsed=time.monotonic()-started
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(p.stdout,''); self.assertEqual(p.stderr,'')
        self.assertEqual((self.root/'deadline-result').read_text(),'timeout')
        self.assertGreaterEqual(elapsed,2.7); self.assertLess(elapsed,4.5)
        with self.assertRaises(ProcessLookupError): os.kill(int((self.root/'deadline-worker').read_text()),0)
    def test_return_observer_is_in_background(self):
        (self.root/'await-launch').touch(); (self.root/'hold-launch').touch(); (self.root/'hold-return').touch()
        # Mark the shell's return before draining a bounded fake return helper.
        p=self.run_shell('codex hello; result=$?; print returned; sleep .08; builtin kill -TERM $_iterm2_utils_appearance_pid; '+self.wait_helper()+'exit $result')
        self.assertEqual(p.returncode,42,p.stderr)
        self.assertEqual(p.stdout,'returned\n')
        self.assertIn('return',[r['phase'] for r in self.rows() if r['event']=='start'])

if __name__=='__main__': unittest.main(argv=[sys.argv[0]]+sys.argv[2:],verbosity=2)
PY
