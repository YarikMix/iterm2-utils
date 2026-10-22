# Shared dispatcher. Never capture or wrap an unknown user function.
if (( ${+aliases[codex]} )); then
  print -u2 'iterm2-utils: codex alias conflict'
  return 1
fi
if (( ${+functions[codex]} )) && [[ ${functions[codex]} == ${_codex_restore_installed_body-} ]]; then
  return 0
fi
if (( ${+functions[codex]} )) && [[ ${functions[codex]} != *'iterm2-utils dispatcher'* ]]; then
  print -u2 'iterm2-utils: codex function conflict'
  return 1
fi
# REPLY is local to the caller. Unknown options are deliberately passed through.
function _iterm2_utils_classify {
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
      --no-daemon) continue ;;
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


function codex() {
  : 'iterm2-utils dispatcher'
  local arg REPLY
  _iterm2_utils_classify "$@"
  if [[ $REPLY != interactive ]]; then
    command codex "$@"
    return $?
  fi
  if [[ ${ITERM2_UTILS_CODEX_NO_DAEMON:-0} == 1 ]]; then
    for arg in "$@"; do
      if [[ $arg == --no-daemon ]]; then
        command codex "$@"
        return $?
      fi
    done
    command codex --no-daemon "$@"
  else
    command codex "$@"
  fi
}
