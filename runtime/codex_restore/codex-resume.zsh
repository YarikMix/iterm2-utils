# Source after any existing codex function (for example codex-iterm2-status).
# Keep a copy of the installed body: a full .zshrc source may redefine codex first.
if (( ${+aliases[codex]} )); then
  print -u2 -- 'Codex: alias codex мешает функции восстановления; уберите alias и подключите файл снова'
  return 1
fi
if (( ${+functions[codex]} )) && [[ ${functions[codex]} != ${_codex_restore_installed_body-} ]]; then
  functions -c codex _codex_restore_previous
fi
typeset -g _codex_restore_root=${${(%):-%x}:A:h}

function _codex_restore_previous_call {
  if (( ${+functions[_codex_restore_previous]} )); then
    _codex_restore_previous "$@"
  else
    command codex "$@"
  fi
}

# REPLY is local to the caller. Unknown options are deliberately passed through.
function _codex_restore_classify {
  emulate -L zsh
  local arg command_name='' literal=0 need_value=0
  REPLY=interactive
  for arg in "$@"; do
    if (( need_value )); then
      need_value=0
      continue
    fi
    (( literal )) && continue
    case $arg in
      --) literal=1; continue ;;
      --help|-h|--version|-V)
        REPLY=passthrough; continue ;;
      --remote)
        REPLY=passthrough; need_value=1; continue ;;
      --remote=*|--remote-control|--ephemeral)
        REPLY=passthrough; continue ;;
      -c|--config|-m|--model|-C|--cd|-i|--image|-p|--profile|-s|--sandbox|-a|--ask-for-approval|--enable|--disable|--add-dir|--local-provider)
        need_value=1; continue ;;
      --no-daemon) _codex_restore_seen_no_daemon=1; continue ;;
      --config=*|--model=*|--cd=*|--image=*|--profile=*|--sandbox=*|--ask-for-approval=*|--enable=*|--disable=*|--add-dir=*|--local-provider=*|--oss|--full-auto|--dangerously-bypass-approvals-and-sandbox|--no-alt-screen|--search)
        continue ;;
      --all|--last)
        [[ $command_name == resume || $command_name == fork ]] || REPLY=passthrough
        continue ;;
      --restore)
        if [[ $command_name == resume ]]; then
          REPLY=invalid-restore
          return
        fi
        REPLY=passthrough; continue ;;
      -*) REPLY=passthrough; continue ;;
    esac
    if [[ -z $command_name ]]; then
      case $arg in
        exec|e|review|agents|remote-control|app-server|login|logout|mcp|mcp-server|app|completion|sandbox|debug|apply|a|cloud|features|help)
          REPLY=passthrough; command_name=service ;;
        resume|fork) command_name=$arg ;;
        *) command_name=prompt ;;
      esac
    fi
  done
  (( need_value )) && REPLY=passthrough
  return 0
}

function _codex_restore_call {
  emulate -L zsh
  local REPLY token='' result=0 _codex_restore_seen_no_daemon=0
  _codex_restore_classify "$@"
  if [[ $REPLY == invalid-restore ]]; then
    print -u2 -- 'Codex: используйте ровно codex resume --restore (без дополнительных аргументов)'
    return 2
  fi
  if [[ $REPLY != interactive ]]; then
    _codex_restore_previous_call "$@"
    return $?
  fi
  # A failed new registration must not lend the child a previous owner's token.
  local -x CODEX_RESTORE_TOKEN=''
  if [[ -z ${_codex_restore_no_daemon+x} ]]; then
    typeset -g _codex_restore_no_daemon=0
    [[ $(command codex --help 2>/dev/null) == *--no-daemon* ]] && _codex_restore_no_daemon=1
  fi
  if (( ! _codex_restore_no_daemon )); then
    _codex_restore_previous_call "$@"
    return $?
  fi
  local -a arguments=("$@") register_args
  (( _codex_restore_seen_no_daemon )) || arguments=(--no-daemon "${arguments[@]}")
  if [[ -n ${ITERM_SESSION_ID-} && ${TERM_PROGRAM-} == iTerm.app ]] && zmodload zsh/system 2>/dev/null; then
    # $$ remains the parent's PID inside ( ... ). Read the actual owner before
    # command substitution creates its own process; never fall back to $$.
    local shell_pid=$sysparams[pid]
    register_args=(register --terminal "$ITERM_SESSION_ID" --shell-pid "$shell_pid")
    [[ -n ${CODEX_RESTORE_REQUEST-} ]] && register_args+=(--request "$CODEX_RESTORE_REQUEST")
    token=$("$_codex_restore_root/codex-sessions" "${register_args[@]}") || token=''
  fi
  if [[ -z $token ]]; then
    _codex_restore_previous_call "${arguments[@]}"
    return $?
  fi
  CODEX_RESTORE_TOKEN=$token
  {
    _codex_restore_previous_call "${arguments[@]}"
    result=$?
  } always {
    "$_codex_restore_root/codex-sessions" finish "$token" || true
  }
  return $result
}

function _codex_restore_select {
  emulate -L zsh
  local rows selected output result
  local -a fields
  rows=$("$_codex_restore_root/codex-sessions" restore-list "$@") || return $?
  if [[ -z $rows ]]; then
    [[ ${1-} == --auto ]] || print -- 'Codex: восстанавливать нечего'
    return 0
  fi
  if (( ! ${+commands[fzf]} )); then
    print -u2 -- 'Codex: для выбора вкладок нужен fzf 0.60+'
    return 127
  fi
  selected=$(print -r -- "$rows" | command fzf --multi --bind=load:select-all --no-sort \
    --delimiter=$'\t' --with-nth=3.. --accept-nth=2 --prompt='Codex: ')
  result=$?
  if (( result == 130 || result == 1 )); then
    return 0
  elif (( result )); then
    print -u2 -- 'Codex: ошибка выбора fzf'
    return $result
  fi
  [[ -n $selected ]] || return 0
  # zsh preserves NUL bytes in command substitution. Capture the producer's
  # status before splitting; a read loop/process substitution would hide it.
  output=$(print -r -- "$selected" | "$_codex_restore_root/codex-sessions" restore-open) || return $?
  [[ -n $output ]] || return 0
  fields=("${(@0)output}")
  local uuid_pattern='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
  if (( ${#fields} != 6 )) || [[ -n $fields[6] || ! $fields[1] =~ $uuid_pattern || ! $fields[2] =~ $uuid_pattern || $fields[3] != /* || $fields[4] != /* || $fields[5] != /* ]]; then
    print -u2 -- 'Codex: некорректный ответ restore-open'
    return 1
  fi
  if ! builtin cd -- "$fields[3]"; then
    "$_codex_restore_root/codex-sessions" restore-cancel "$fields[1]" || true
    return 1
  fi
  local -x CODEX_HOME=$fields[4] CODEX_RESTORE_REQUEST=$fields[1] CODEX_RESTORE_CACHE_DIR=$fields[5]
  codex resume "$fields[2]"
}

function _codex_restore_precmd {
  emulate -L zsh
  precmd_functions=(${precmd_functions:#_codex_restore_precmd})
  [[ ${_codex_restore_auto_ran-0} == 1 ]] && return 0
  typeset -g _codex_restore_auto_ran=1
  _codex_restore_select --auto
  # A failed picker must not stop the remaining precmd hooks (including cr).
  return 0
}

if [[ -o interactive && ${TERM_PROGRAM-} == iTerm.app && ${CODEX_RESTORE_NO_AUTO-0} != 1 && ${_codex_restore_auto_ran-0} != 1 ]]; then
  typeset -ga precmd_functions
  (( ${precmd_functions[(Ie)_codex_restore_precmd]} )) || precmd_functions+=(_codex_restore_precmd)
fi

function codex {
  if (( $# == 2 )) && [[ $1 == resume && $2 == --restore ]]; then
    _codex_restore_select
  else
    _codex_restore_call "$@"
  fi
}
typeset -g _codex_restore_installed_body=$functions[codex]
