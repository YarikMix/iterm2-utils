# Short-lived helpers use a lifetime pipe, without visible shell jobs.
function _iterm2_utils_appearance {
  emulate -L zsh
  unsetopt bgnice
  [[ -o interactive && ${TERM_PROGRAM-} == iTerm.app && -z ${TMUX-} ]] || return 0
  [[ -n ${ITERM2_UTILS_PYTHON-} && ${ITERM2_UTILS_APPEARANCE_CONFIG-} == /* ]] || return 0
  zmodload zsh/system 2>/dev/null || return 0
  local phase=$1 cwd=$2 tty=$TTY fd clean_fd child result discard
  [[ -n $tty ]] || return 0
  local -a ready_arguments=()
  if [[ $phase == launch ]]; then
    ready_arguments=(--ready-fd 3)
    typeset -gi +x _iterm2_utils_appearance_sequence=$(( ${_iterm2_utils_appearance_sequence:-0} + 1 ))
    typeset -g +x _iterm2_utils_appearance_launch_id="$sysparams[pid]-$_iterm2_utils_appearance_sequence"
  fi
  if [[ $phase != shell && ${_iterm2_utils_appearance_launch_id-} == "$sysparams[pid]-"* ]]; then
    ready_arguments+=(--launch-id "$_iterm2_utils_appearance_launch_id")
  fi
  if [[ -n ${_iterm2_utils_appearance_fd-} ]]; then
    fd=$_iterm2_utils_appearance_fd
    # A forked shell closes its copy, never its parent's helper.
    if [[ ${_iterm2_utils_appearance_owner-} == $sysparams[pid] ]]; then
      sysread -i "$fd" -t 0 discard 2>/dev/null && result=0 || result=$?
      if (( result == 4 )); then
        builtin kill -TERM "$_iterm2_utils_appearance_pid" 2>/dev/null || true
        sysread -i "$fd" discard 2>/dev/null && result=0 || result=$?
      fi
      # EOF follows supervisor cleanup; errors cannot authorize a new writer.
      (( result == 5 )) || return 0
    fi
    exec {fd}<&-
    unset _iterm2_utils_appearance_fd _iterm2_utils_appearance_pid
  fi
  local ready=0
  {
    # shortcut: macOS/zsh reaps process substitutions; revalidate if shell support expands.
    exec {fd}< <(
      print -r -- "$sysparams[pid]"
      exec "$ITERM2_UTILS_PYTHON" "$_iterm2_utils_appearance_root/appearance.py" \
        --config "$ITERM2_UTILS_APPEARANCE_CONFIG" --cwd "$cwd" --phase "$phase" --tty "$tty" "${ready_arguments[@]}" 3>&1 >/dev/null 2>&1
    )
    read -r child <&$fd || return 0
    [[ $child == <-> ]] || return 0
    # EOF on error/timeout also releases launch within the supervisor's deadline.
    [[ $phase != launch ]] || read -r discard <&$fd || true
    # The read end must not be inherited by Codex or nested external shells.
    sysopen -r -o cloexec -u clean_fd "/dev/fd/$fd" 2>/dev/null || return 0
    typeset -g +x _iterm2_utils_appearance_owner=$sysparams[pid]
    typeset -g +x _iterm2_utils_appearance_pid=$child
    typeset -g +x _iterm2_utils_appearance_fd=$clean_fd
    if [[ $phase == shell ]]; then
      # A fresh child shell must not race this shell's pending assignment/reset.
      sysread -i "$fd" discard 2>/dev/null && result=0 || result=$?
      (( result == 5 )) || return 0
    fi
    ready=1
  } always {
    if (( ! ready )); then
      # An interrupted handshake still owns a bounded supervisor to cancel.
      [[ -n $child ]] || read -r child <&$fd
      while true; do
        sysread -i "$fd" -t 0 discard 2>/dev/null && result=0 || result=$?
        (( result == 0 )) || break
      done
      if (( result == 4 )) && [[ $child == <-> ]]; then
        builtin kill -TERM "$child" 2>/dev/null || true
        sysread -i "$fd" discard 2>/dev/null || true
      fi
      [[ -z $clean_fd ]] || exec {clean_fd}<&-
      unset _iterm2_utils_appearance_fd _iterm2_utils_appearance_pid
    fi
    exec {fd}<&-
  }
  return 0
}

function _iterm2_utils_appearance_chpwd {
  emulate -L zsh
  [[ -o interactive && ${TERM_PROGRAM-} == iTerm.app && -z ${TMUX-} &&
     ${_iterm2_utils_appearance_hook_owner-} == $sysparams[pid] ]] || return 0
  _iterm2_utils_appearance shell "$(builtin pwd -P)"
  return 0
}

() {
  emulate -L zsh
  typeset -g +x _iterm2_utils_appearance_root=${${(%):-%x}:A:h}
  if [[ -o interactive && ${TERM_PROGRAM-} == iTerm.app && -z ${TMUX-} && ${_iterm2_utils_appearance_bootstrapped-0} != 1 ]] && zmodload zsh/system 2>/dev/null; then
    typeset -g +x _iterm2_utils_appearance_bootstrapped=1
    typeset -g +x _iterm2_utils_appearance_hook_owner=$sysparams[pid]
    autoload -Uz add-zsh-hook
    add-zsh-hook chpwd _iterm2_utils_appearance_chpwd
    _iterm2_utils_appearance_chpwd
  fi
}
