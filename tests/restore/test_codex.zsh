#!/bin/zsh
# External programs are replaced at the process boundary; zsh integration is real.
exec python3 - "$0" "${@}" <<'PY'
import json, os, pathlib, shutil, subprocess, sys, tempfile, unittest
SOURCE = pathlib.Path(sys.argv[1]).resolve().parents[2] / 'runtime/codex_restore/codex-resume.zsh'
FOCUS = sys.argv[2] if len(sys.argv) > 2 else ''
STUB = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path(__file__).parent
name = pathlib.Path(__file__).name
args = sys.argv[1:]
def log(kind, **more):
    with (root/'log').open('a') as out:
        out.write(json.dumps(dict(kind=kind,args=args,**more))+'\n')
if name == 'codex':
    if args == ['--help']:
        log('help')
        print('usage '+('--no-daemon' if not (root/'unsupported').exists() else ''))
    else:
        log('codex', token=os.getenv('CODEX_RESTORE_TOKEN'), request=os.getenv('CODEX_RESTORE_REQUEST'), home=os.getenv('CODEX_HOME'), cache=os.getenv('CODEX_RESTORE_CACHE_DIR'), cwd=os.getcwd(), shell_parent=os.getppid())
        if (root/'crash-shell').exists():
            import signal
            os.kill(os.getppid(),signal.SIGKILL)
        if (root/'signal').exists():
            import signal
            os.kill(os.getpid(),signal.SIGINT)
        sys.exit(int((root/'exit').read_text()) if (root/'exit').exists() else 0)
elif name == 'fzf':
    log('fzf', data=sys.stdin.read())
    print((root/'selected').read_text(),end='')
    sys.exit(int((root/'fzf-exit').read_text()) if (root/'fzf-exit').exists() else 0)
else:
    log('cli', data=sys.stdin.read() if args and args[0]=='restore-open' else '')
    command = args[0]
    if (root/(command+'-fail')).exists():
        print('controlled '+command+' error',file=sys.stderr)
        sys.exit(7)
    if command=='register':
        counter=root/'counter'
        n=int(counter.read_text())+1 if counter.exists() else 1
        counter.write_text(str(n)); print('token-'+str(n))
    elif command=='restore-list':
        print((root/'rows').read_text(),end='')
    elif command=='restore-open':
        sys.stdout.buffer.write((root/'first').read_bytes())
'''

class Shell(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='codex-shell-')
        self.root=pathlib.Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        for name in ('codex','codex-sessions','fzf'):
            p=self.root/name; p.write_text(STUB); p.chmod(0o755)
        self.assertTrue(SOURCE.exists(), 'missing codex-resume.zsh integration')
        shutil.copy(SOURCE,self.root/'codex-resume.zsh')
        self.env=dict(os.environ,PATH=str(self.root)+':/usr/bin:/bin',TERM_PROGRAM='iTerm.app',ITERM_SESSION_ID='w1t1p0:11111111-1111-4111-8111-111111111111',CODEX_RESTORE_NO_AUTO='0',CODEX_RESTORE_CACHE_DIR=str(self.root/'cache'),CODEX_HOME=str(self.root/'original-home'))
        self.env.pop('CODEX_RESTORE_TOKEN',None); self.env.pop('CODEX_RESTORE_REQUEST',None)
        (self.root/'rows').write_text('')
        (self.root/'selected').write_text('')
        (self.root/'first').write_bytes(b'')
    def run_shell(self,body,interactive=False,pre=''):
        script=pre+'\nsource "$TEST_ROOT/codex-resume.zsh"\n'+body
        env=dict(self.env,TEST_ROOT=str(self.root))
        p=subprocess.run(['zsh','-f']+(['-i'] if interactive else [])+['-c',script],env=env,text=True,capture_output=True,cwd=self.root)
        self.result=p
        return p
    def logs(self,kind=None):
        path=self.root/'log'
        rows=[json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [r for r in rows if kind is None or r['kind']==kind]
    def commands(self): return [r['args'][0] for r in self.logs('cli')]
    def test_routing(self):
        cases=[('exec task',['exec','task']),('review',['review']),('agents',['agents']),('remote-control',['remote-control']),('app-server',['app-server']),('--help',['--help']),('--version',['--version']),('-m resume exec task',['-m','resume','exec','task']),('--config x=y review',['--config','x=y','review']),('--future x',['--future','x'])]
        for shell,want in cases:
            with self.subTest(shell=shell):
                (self.root/'log').unlink(missing_ok=True)
                p=self.run_shell('codex '+shell)
                self.assertEqual(p.returncode,0,p.stderr)
                self.assertEqual([r['args'] for r in self.logs('help' if shell=='--help' else 'codex')],[want])
                self.assertEqual(self.commands(),[])
    def test_unknown_positional_is_native_prompt(self):
        (self.root/'exit').write_text('42')
        p=self.run_shell('codex unknown-command')
        self.assertEqual(p.returncode,42,p.stderr)
        self.assertEqual(self.logs('codex')[0]['args'],['--no-daemon','unknown-command'])
        self.assertEqual(self.commands(),['register','finish'])
    def test_interactive_argv_and_cleanup(self):
        p=self.run_shell('codex -C "project space" -m resume "hello world"; codex resume --all; codex resume -- --restore; codex --no-daemon fork; print -r -- "after:${CODEX_RESTORE_TOKEN-unset}"')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual([r['args'] for r in self.logs('codex')],[['--no-daemon','-C','project space','-m','resume','hello world'],['--no-daemon','resume','--all'],['--no-daemon','resume','--','--restore'],['--no-daemon','fork']])
        self.assertEqual(self.commands(),['register','finish']*4)
        self.assertEqual([r['token'] for r in self.logs('codex')],['token-1','token-2','token-3','token-4'])
        self.assertEqual(len(self.logs('help')),1)
        self.assertEqual(p.stdout,'after:unset\n')
        for row in self.logs('cli')[::2]:
            self.assertEqual(row['args'][:2],['register','--terminal'])
            self.assertIn('--shell-pid',row['args'])
    def test_all_global_option_values_are_skipped(self):
        options=['-c','--config','-m','--model','-C','--cd','-i','--image','-p','--profile','-s','--sandbox','-a','--ask-for-approval','--enable','--disable','--add-dir','--local-provider']
        arguments=[]
        for option in options:
            arguments.extend([option,'exec'])
        import shlex
        p=self.run_shell('codex '+shlex.join(arguments+['resume','--all']))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.logs('codex')[0]['args'],['--no-daemon']+arguments+['resume','--all'])
        self.assertEqual(self.commands(),['register','finish'])
    def test_previous_and_repeated_source(self):
        p=self.run_shell('source "$TEST_ROOT/codex-resume.zsh"; codex one; codex two',pre='function codex { print previous >> "$TEST_ROOT/previous"; command codex "$@"; }')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual((self.root/'previous').read_text(),'previous\nprevious\n')
        self.assertEqual(len(self.logs('codex')),2)
    def test_full_configuration_source(self):
        p=self.run_shell('function codex { print current >> "$TEST_ROOT/previous"; command codex "$@"; }; source "$TEST_ROOT/codex-resume.zsh"; codex hello; codex resume --restore',pre='function codex { print stale >> "$TEST_ROOT/previous"; command codex "$@"; }')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual((self.root/'previous').read_text(),'current\n')
        self.assertEqual(self.commands(),['register','finish','restore-list'])
    def test_status_function_single_flag(self):
        # Literal fixture keeps tests portable and mirrors the installed function's behavior.
        pre='function codex { case "${1-}" in agents|remote-control|app-server) command codex "$@" ;; *) if (( ! ${@[(Ie)--no-daemon]} )) && command codex --help 2>/dev/null | /usr/bin/grep -q -- --no-daemon; then command codex --no-daemon "$@"; else command codex "$@"; fi ;; esac; }'
        p=self.run_shell('codex; codex --no-daemon resume --all; codex exec task; codex agents',pre=pre)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual([r['args'] for r in self.logs('codex')],[['--no-daemon'],['--no-daemon','resume','--all'],['--no-daemon','exec','task'],['agents']])
        self.assertEqual(self.commands(),['register','finish']*2)
    def test_exit_and_dynamic_environment(self):
        (self.root/'exit').write_text('42')
        p=self.run_shell('export CODEX_RESTORE_TOKEN=old CODEX_RESTORE_REQUEST=oldrequest; codex; code=$?; print -r -- "$code:$CODEX_RESTORE_TOKEN:$CODEX_RESTORE_REQUEST"; exit $code')
        self.assertEqual(p.returncode,42,p.stderr)
        self.assertEqual(p.stdout,'42:old:oldrequest\n')
        self.assertEqual(self.commands(),['register','finish'])
        self.assertEqual(self.logs('codex')[0]['token'],'token-1')
    def test_register_failure(self):
        (self.root/'register-fail').touch()
        p=self.run_shell('codex hello')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(len(self.logs('codex')),1)
        self.assertIn(self.logs('codex')[0]['token'],(None,''))
        self.assertEqual(self.commands(),['register'])
    def test_unsupported_no_tracking(self):
        (self.root/'unsupported').touch()
        p=self.run_shell('codex; codex resume --all')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.commands(),[])
        self.assertEqual([r['args'] for r in self.logs('codex')],[[],['resume','--all']])
        self.assertEqual(len(self.logs('help')),1)
    def test_remote_and_temporary(self):
        p=self.run_shell('codex --remote ws://example; codex --ephemeral hi; codex resume --remote ws://example')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.commands(),[])
        self.assertEqual([r['args'] for r in self.logs('codex')],[['--remote','ws://example'],['--ephemeral','hi'],['resume','--remote','ws://example']])

    def picker(self,selected=None,cwd=None):
        sid1='11111111-1111-4111-8111-111111111111'
        sid2='22222222-2222-4222-8222-222222222222'
        request='33333333-3333-4333-8333-333333333333'
        self.project=cwd or self.root/'project space'
        self.project.mkdir(exist_ok=True)
        self.restore_home=self.root/'restored home'
        (self.root/'rows').write_text('1\t'+sid1+'\t1.1\tOne\tproject\t1h\n2\t'+sid2+'\t1.2\tTwo\tproject\t2h\n')
        (self.root/'selected').write_text(selected if selected is not None else sid1+'\n'+sid2+'\n')
        (self.root/'first').write_bytes(('\0'.join([request,sid1,str(self.project),str(self.restore_home),str(self.root/'cache')])+'\0').encode())
        return sid1,sid2,request
    def test_picker_open_before_first_resume(self):
        sid1,sid2,request=self.picker()
        (self.root/'exit').write_text('42')
        p=self.run_shell('codex resume --restore; code=$?; print -r -- "$code:$CODEX_HOME:${CODEX_RESTORE_REQUEST-unset}"; exit $code')
        self.assertEqual(p.returncode,42,p.stderr)
        self.assertEqual(p.stdout,'42:'+str(self.root/'original-home')+':unset\n')
        self.assertEqual(self.commands(),['restore-list','restore-open','register','finish'])
        self.assertEqual(self.logs('cli')[1]['data'],sid1+'\n'+sid2+'\n')
        self.assertEqual(self.logs('cli')[2]['args'][-2:],['--request',request])
        row=self.logs('codex')[0]
        self.assertEqual(row['args'],['--no-daemon','resume',sid1])
        self.assertEqual((row['cwd'],row['home'],row['request']),(str(self.project),str(self.restore_home),request))
        self.assertLess([r['kind'] for r in self.logs()].index('fzf'),[r['kind'] for r in self.logs()].index('codex'))
        flags=self.logs('fzf')[0]['args']
        for flag in ('--multi','--bind=load:select-all','--no-sort','--accept-nth=2'):
            self.assertIn(flag,flags)
        self.assertIn('--delimiter=\t',flags)
        self.assertIn('--with-nth=3..',flags)
    def test_picker_selection_sent_as_uuids(self):
        for selection in ('22222222-2222-4222-8222-222222222222\n','22222222-2222-4222-8222-222222222222\n11111111-1111-4111-8111-111111111111\n'):
            with self.subTest(selection=selection):
                self.picker(selection)
                (self.root/'log').unlink(missing_ok=True)
                p=self.run_shell('codex resume --restore')
                self.assertEqual(p.returncode,0,p.stderr)
                self.assertEqual(len(self.logs('cli')),4)
                self.assertEqual(self.logs('cli')[1]['data'],selection)
    def test_picker_cache_environment_is_scoped(self):
        for cache in (None, 'relative caller cache'):
            with self.subTest(cache=cache):
                self.picker()
                if cache is None:
                    self.env.pop('CODEX_RESTORE_CACHE_DIR',None)
                else:
                    self.env['CODEX_RESTORE_CACHE_DIR']=cache
                (self.root/'log').unlink(missing_ok=True)
                p=self.run_shell('codex resume --restore; print -r -- "${CODEX_RESTORE_CACHE_DIR-unset}"')
                self.assertEqual(p.returncode,0,p.stderr)
                self.assertEqual(p.stdout,(cache if cache is not None else 'unset')+'\n')
                self.assertEqual(self.logs('codex')[0]['cache'],str(self.root/'cache'))
    def test_picker_esc(self):
        self.picker(); (self.root/'fzf-exit').write_text('130')
        p=self.run_shell('codex resume --restore')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.commands(),['restore-list'])
        self.assertEqual(self.logs('codex'),[])
        self.assertEqual(len(self.logs('fzf')),1)
    def test_picker_error(self):
        self.picker(); (self.root/'fzf-exit').write_text('2')
        p=self.run_shell('codex resume --restore')
        self.assertEqual(p.returncode,2,p.stderr)
        self.assertEqual(self.commands(),['restore-list'])
        self.assertIn('fzf',p.stderr)
    def test_picker_missing_fzf(self):
        self.picker(); (self.root/'fzf').unlink()
        # Restrict lookup to the fixture and standard OS tools.
        p=self.run_shell('codex resume --restore')
        self.assertEqual(p.returncode,127,p.stderr)
        self.assertIn('fzf',p.stderr)
        self.assertEqual(self.commands(),['restore-list'])
    def test_picker_empty(self):
        p=self.run_shell('codex resume --restore')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(p.stdout,'Codex: восстанавливать нечего\n')
        self.assertEqual(self.logs('fzf'),[])
    def test_picker_cli_errors_not_cancellation(self):
        for command in ('restore-list','restore-open'):
            with self.subTest(command=command):
                self.picker(); (self.root/(command+'-fail')).touch()
                p=self.run_shell('codex resume --restore')
                self.assertEqual(p.returncode,7,p.stderr)
                self.assertEqual(self.logs('codex'),[])
                (self.root/(command+'-fail')).unlink()
                (self.root/'log').unlink(missing_ok=True)
    def test_picker_bad_nul_protocol(self):
        self.picker()
        valid=(self.root/'first').read_bytes().split(b'\0')
        for payload in (b'bad\0id\0/tmp\0', b'\0'.join(valid[:4])+b'\0',
                        b'\0'.join(valid[:4]+[b'relative',b'']),
                        b'\0'.join(valid[:4]+[b'',b''])):
            with self.subTest(payload=payload):
                (self.root/'first').write_bytes(payload)
                p=self.run_shell('codex resume --restore')
                self.assertNotEqual(p.returncode,0)
                self.assertEqual(self.logs('codex'),[])
                self.assertIn('ответ',p.stderr)
    def test_picker_cd_failure_cancels(self):
        sid1,sid2,request=self.picker()
        self.project.rmdir()
        p=self.run_shell('codex resume --restore')
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.commands(),['restore-list','restore-open','restore-cancel'])
        self.assertEqual(self.logs('cli')[-1]['args'],['restore-cancel',request])
        self.assertEqual(self.logs('codex'),[])
    def test_extra_restore_arguments_rejected(self):
        for arguments in ('resume --restore extra','resume --restore --all','-m x resume --restore','resume --all --restore','resume --help --restore','--help resume --restore'):
            with self.subTest(arguments=arguments):
                p=self.run_shell('codex '+arguments)
                self.assertEqual(p.returncode,2,p.stderr)
                self.assertIn('codex resume --restore',p.stderr)
                self.assertEqual(self.logs(),[])
    def test_signal_cleanup(self):
        (self.root/'signal').touch()
        p=self.run_shell('codex')
        self.assertEqual(p.returncode,130,p.stderr)
        self.assertEqual(self.commands(),['register','finish'])
    def test_alias_diagnostic(self):
        p=self.run_shell('print -r -- "$aliases[codex]"; (( ${+functions[codex]} )) && exit 9; exit 0',pre="alias codex='echo aliased'")
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('alias codex',p.stderr)
        self.assertEqual(p.stdout,'echo aliased\n')
    def test_startup_once(self):
        self.picker(); (self.root/'fzf-exit').write_text('130')
        p=self.run_shell('source "$TEST_ROOT/codex-resume.zsh"; print -r -- "before:${(j:,:)precmd_functions}"; _codex_restore_precmd; print -r -- "after:${(j:,:)precmd_functions}"; _codex_restore_precmd; source "$TEST_ROOT/codex-resume.zsh"; print -r -- "again:${(j:,:)precmd_functions}"',interactive=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.commands(),['restore-list'])
        self.assertEqual(self.logs('cli')[0]['args'],['restore-list','--auto'])
        self.assertEqual(p.stdout,'before:_codex_restore_precmd\nafter:\nagain:\n')
        self.assertEqual(len(self.logs('fzf')),1)
    def test_startup_error_does_not_stop_other_precmd_hooks(self):
        (self.root/'restore-list-fail').touch()
        p=self.run_shell('_codex_restore_precmd; code=$?; print -r -- "$code:${(j:,:)precmd_functions}"',interactive=True,pre='precmd_functions=(other_precmd)')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(p.stdout,'0:other_precmd\n')
        self.assertIn('controlled restore-list error',p.stderr)
    def test_startup_gates(self):
        for interactive,term,no_auto in ((False,'iTerm.app','0'),(True,'xterm','0'),(True,'iTerm.app','1')):
            with self.subTest(interactive=interactive,term=term,no_auto=no_auto):
                self.env.update(TERM_PROGRAM=term,CODEX_RESTORE_NO_AUTO=no_auto)
                p=self.run_shell('print -r -- "${(j:,:)precmd_functions}"; codex resume --restore',interactive=interactive)
                self.assertEqual(p.returncode,0,p.stderr)
                self.assertEqual(p.stdout,'\nCodex: восстанавливать нечего\n')
                self.assertEqual(self.logs('cli')[-1]['args'],['restore-list'])

    def test_foreground_subshell_is_tracked(self):
        p=self.run_shell('(codex hello); print done')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.commands(),['register','finish'])
        self.assertEqual(self.logs('codex')[0]['args'],['--no-daemon','hello'])
        registration=self.logs('cli')[0]['args']
        requested_pid=int(registration[registration.index('--shell-pid')+1])
        self.assertEqual(requested_pid,self.logs('codex')[0]['shell_parent'])
    def test_dead_subshell_does_not_borrow_live_parent(self):
        # SIGKILL only our test subshell, preventing always/finish; keep its parent alive.
        (self.root/'crash-shell').touch()
        script='source "$TEST_ROOT/codex-resume.zsh"; print -r -- "$$" > "$TEST_ROOT/parent"; (codex hello); print ready; read -r answer'
        process=subprocess.Popen(['zsh','-f','-c',script],env=dict(self.env,TEST_ROOT=str(self.root)),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=self.root)
        try:
            self.assertEqual(process.stdout.readline(),'ready\n')
            self.assertIsNone(process.poll())
            parent_pid=int((self.root/'parent').read_text())
            actual_pid=self.logs('codex')[0]['shell_parent']
            self.assertNotEqual(parent_pid,actual_pid)
            self.assertEqual(self.commands(),['register'])
            args=self.logs('cli')[0]['args']
            requested_pid=int(args[args.index('--shell-pid')+1])
            with self.subTest(boundary='actual-owner'):
                self.assertEqual(requested_pid,actual_pid)
            # Feed the observed registration boundary into the real registry API.
            sys.path.insert(0,str(SOURCE.parent))
            from codexlib import registry, store
            from codexlib.models import Pane
            from tests.restore.helpers import write_session
            paths=store.paths(pathlib.Path(self.env['CODEX_HOME']),pathlib.Path(self.env['CODEX_RESTORE_CACHE_DIR']))
            sid='11111111-1111-4111-8111-111111111111'
            transcript=write_session(paths.codex_home,sid,self.root)
            reg=registry.register(paths,self.env['ITERM_SESSION_ID'],requested_pid,'shell-start','current-launch',1)
            event={'hook_event_name':'Stop','session_id':sid,'cwd':str(self.root),'transcript_path':str(transcript)}
            self.assertTrue(registry.accept_event(paths,reg.token,self.env['ITERM_SESSION_ID'],event,lambda pid:'shell-start',2))
            identity=lambda pid: 'shell-start' if pid==parent_pid and process.poll() is None else None
            with self.subTest(boundary='late-hook'):
                self.assertFalse(registry.accept_event(paths,reg.token,self.env['ITERM_SESSION_ID'],event,identity,3))
            with self.subTest(boundary='live-filter'):
                self.assertEqual(registry.live(paths,[Pane(sid,'T1','W1',1,1)],identity),[])
            self.assertIsNone(process.poll())
        finally:
            process.communicate('\n',timeout=5)
    def test_unknown_options_after_positionals_passthrough(self):
        import shlex
        (self.root/'exit').write_text('42')
        for arguments in (['resume','--future','x'],['fork','--future','x'],['hello','--future','x'],['resume','--future=x']):
            with self.subTest(arguments=arguments):
                (self.root/'log').unlink(missing_ok=True)
                p=self.run_shell('codex '+shlex.join(arguments))
                self.assertEqual(p.returncode,42,p.stderr)
                self.assertEqual([row['args'] for row in self.logs('codex')],[arguments])
                self.assertEqual(self.commands(),[])
                self.assertEqual(self.logs('help'),[])
    def test_passthrough_still_rejects_extra_restore(self):
        for arguments in ('resume --remote ws://example --restore','--remote ws://example resume --restore','--future resume --restore','resume --future x --restore'):
            with self.subTest(arguments=arguments):
                (self.root/'log').unlink(missing_ok=True)
                p=self.run_shell('codex '+arguments)
                self.assertEqual(p.returncode,2,p.stderr)
                self.assertIn('codex resume --restore',p.stderr)
                self.assertEqual(self.logs(),[])
    def test_known_resume_options_and_literal_passthrough(self):
        import shlex
        cases=[(['resume','--last','--all'],True),(['fork','--last','--all'],True),(['resume','-m','exec','--all'],True),(['resume','--remote','ws://example','--','--restore'],False),(['--future','--model','resume','exec','--restore'],False),(['--future','x','resume','--restore'],False)]
        for arguments,tracked in cases:
            with self.subTest(arguments=arguments):
                (self.root/'log').unlink(missing_ok=True)
                p=self.run_shell('codex '+shlex.join(arguments))
                self.assertEqual(p.returncode,0,p.stderr)
                self.assertEqual(self.logs('codex')[0]['args'],(['--no-daemon'] if tracked else [])+arguments)
                self.assertEqual(self.commands(),['register','finish'] if tracked else [])
    def test_literal_no_daemon_is_not_a_flag(self):
        p=self.run_shell('codex resume -- --no-daemon; codex -m --no-daemon hello')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual([r['args'] for r in self.logs('codex')],[['--no-daemon','resume','--','--no-daemon'],['--no-daemon','-m','--no-daemon','hello']])
        self.assertEqual(self.commands(),['register','finish']*2)
    def test_register_failure_does_not_reuse_inherited_token(self):
        (self.root/'register-fail').touch()
        p=self.run_shell('export CODEX_RESTORE_TOKEN=old; codex; print -r -- "$CODEX_RESTORE_TOKEN"')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn(self.logs('codex')[0]['token'],(None,''))
        self.assertEqual(p.stdout,'old\n')
    def test_picker_paths_are_literal(self):
        project=self.root/"quote' $() `touch marker`\tline\nnext"
        self.picker(cwd=project)
        p=self.run_shell('codex resume --restore')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.logs('codex')[0]['cwd'],str(project))
        self.assertFalse((self.root/'marker').exists())
    def test_real_cli_finish_and_corrupt_cache(self):
        sys.path.insert(0,str(SOURCE.parent))
        from codexlib import snapshots, store
        from codexlib.models import Snapshot
        shutil.copy(SOURCE.parent/'codex-sessions',self.root/'codex-sessions')
        (self.root/'codexlib').symlink_to(SOURCE.parent/'codexlib',target_is_directory=True)
        ps=self.root/'ps'
        ps.write_text("#!/usr/bin/env python3\nimport os\nprint(os.environ['TEST_SHELL_PID']+' Thu Oct 15 10:00:00 2026 /bin/zsh')\n")
        ps.chmod(0o755)
        self.env.update(CODEX_RESTORE_PS=str(ps),CODEX_RESTORE_ITERM_LAUNCH='current-launch')
        paths=store.paths(pathlib.Path(self.env['CODEX_HOME']),pathlib.Path(self.env['CODEX_RESTORE_CACHE_DIR']))
        store.write(paths,'tabs.json',snapshots._encode(Snapshot('previous-launch',100,[])))
        original=(paths.state_dir/'tabs.json').read_bytes()
        (self.root/'exit').write_text('42')
        p=self.run_shell('codex hello',pre='export TEST_SHELL_PID=$$')
        self.assertEqual(p.returncode,42,p.stderr)
        self.assertIsNotNone(store.read(paths,'registry.json'),p.stderr)
        entries=store.read(paths,'registry.json')['registrations']
        self.assertEqual(len(entries),1)
        self.assertFalse(entries[0]['active'])
        self.assertEqual(self.logs('codex')[0]['token'],entries[0]['token'])
        (self.root/'signal').touch()
        p=self.run_shell('codex hello',pre='export TEST_SHELL_PID=$$')
        self.assertEqual(p.returncode,130,p.stderr)
        self.assertTrue(all(not entry['active'] for entry in store.read(paths,'registry.json')['registrations']))
        (self.root/'signal').unlink()
        (paths.state_dir/'registry.json').write_text('broken json')
        p=self.run_shell('codex hello',pre='export TEST_SHELL_PID=$$')
        self.assertEqual(p.returncode,42,p.stderr)
        self.assertIn('invalid state',p.stderr)
        self.assertEqual(len(self.logs('codex')),3)
        self.assertEqual(self.logs('codex')[-1]['token'],'')
        self.assertEqual((paths.state_dir/'tabs.json').read_bytes(),original)
    def test_two_startup_shells_real_cli(self):
        # Real snapshot/state locking/auto claim across two independent zsh processes.
        sys.path.insert(0,str(SOURCE.parent))
        from codexlib import snapshots, store
        from codexlib.models import SavedTab, Session, Snapshot
        from tests.restore.helpers import TerminalTools, write_session
        sid1,_,_=self.picker()
        shutil.copy(SOURCE.parent/'codex-sessions',self.root/'codex-sessions')
        (self.root/'codexlib').symlink_to(SOURCE.parent/'codexlib',target_is_directory=True)
        paths=store.paths(pathlib.Path(self.env['CODEX_HOME']),pathlib.Path(self.env['CODEX_RESTORE_CACHE_DIR']))
        transcript=write_session(paths.codex_home,sid1,self.project)
        store.write(paths,'tabs.json',snapshots._encode(Snapshot('previous-launch',100,[SavedTab((1,1),Session(sid1,self.project,transcript,paths.codex_home))])))
        original=(paths.state_dir/'tabs.json').read_bytes()
        tools=TerminalTools(self.root)
        tools.set_inventory([{'id':sid1,'tab_id':'T1','window_id':'W1'}],[{'id':'T1','window_id':'W1','index':0}],[{'id':'W1'}])
        self.env.update(CODEX_RESTORE_IT2=str(tools.it2),CODEX_RESTORE_PS=str(tools.ps),CODEX_RESTORE_ITERM_LAUNCH='current-launch')
        (self.root/'fzf-exit').write_text('130')
        script='source "$TEST_ROOT/codex-resume.zsh"; _codex_restore_precmd; _codex_restore_precmd'
        env=dict(self.env,TEST_ROOT=str(self.root))
        processes=[subprocess.Popen(['zsh','-f','-i','-c',script],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=self.root) for _ in range(2)]
        for process in processes:
            out,err=process.communicate(timeout=10)
            self.assertEqual(process.returncode,0,err)
            self.assertEqual(out,'')
        self.assertEqual(len(self.logs('fzf')),1)
        p=self.run_shell('codex resume --restore')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(len(self.logs('fzf')),2)
        (self.root/'fzf-exit').unlink()
        (self.root/'selected').write_text(sid1+'\n')
        tools.ps.write_text("#!/usr/bin/env python3\nimport os\nprint(os.environ['TEST_SHELL_PID']+' Thu Oct 15 10:00:00 2026 /bin/zsh')\n")
        p=self.run_shell('codex resume --restore',pre='export TEST_SHELL_PID=$$')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(len(self.logs('codex')),1)
        self.assertEqual(self.logs('codex')[0]['args'],['--no-daemon','resume',sid1])
        registrations=store.read(paths,'registry.json')['registrations']
        self.assertEqual(len(registrations),1)
        self.assertEqual(registrations[0]['session']['session_id'],sid1)
        self.assertFalse(registrations[0]['active'])
        self.assertEqual(registrations[0]['request'],self.logs('codex')[0]['request'])
        self.assertEqual(store.pending(paths),[])
        self.assertEqual((paths.state_dir/'tabs.json').read_bytes(),original)

if __name__=='__main__':
    names=[name for name in unittest.defaultTestLoader.getTestCaseNames(Shell) if not FOCUS or FOCUS in name]
    suite=unittest.TestSuite(Shell(name) for name in names)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    failed={getattr(test,'test_case',test).id() for test,_ in result.failures+result.errors}
    print('pass=%d fail=%d' % (result.testsRun-len(failed), len(failed)))
    sys.exit(not result.wasSuccessful())
PY
