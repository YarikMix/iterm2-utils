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
function codex() {
  : 'iterm2-utils dispatcher'
  local arg REPLY
  if (( ${+functions[_codex_restore_classify]} )); then
    _codex_restore_classify "$@"
    if [[ $REPLY != interactive ]]; then
      command codex "$@"
      return $?
    fi
  fi
  case "${1-}" in
    exec|e|review|agents|remote-control|app-server|login|logout|mcp|mcp-server|app|completion|sandbox|debug|apply|a|cloud|features|help|--help|-h|--version|-V) command codex "$@"; return $? ;;
  esac
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
