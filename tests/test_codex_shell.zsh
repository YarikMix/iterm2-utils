#!/bin/zsh
set -eu
root=${0:A:h:h}
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/bin"
cat > "$tmp/bin/codex" <<'SH'
#!/bin/sh
printf '%s\n' "$@" > "$CAPTURE"
SH
chmod +x "$tmp/bin/codex"
export PATH="$tmp/bin:$PATH" CAPTURE="$tmp/argv"
export ITERM2_UTILS_CODEX_NO_DAEMON=1
source "$root/runtime/codex.zsh"
source "$root/runtime/codex.zsh"
for service in agents remote-control app-server; do
  codex "$service"
  [[ "$(cat "$CAPTURE")" == "$service" ]]
done
codex hello --no-daemon
[[ "$(grep -c -- --no-daemon "$CAPTURE")" == 1 ]]
codex hello
[[ "$(grep -c -- --no-daemon "$CAPTURE")" == 1 ]]
ITERM2_UTILS_CODEX_NO_DAEMON=0
codex hello
[[ "$(cat "$CAPTURE")" == hello ]]
print 'Codex dispatcher tests passed'
