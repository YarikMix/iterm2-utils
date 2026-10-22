# iterm2-utils

Read-only discovery and feature selection for iTerm2 with Codex CLI and Claude Code.
This repository is under development: **installation, update, uninstall and runtime
integrations are not implemented yet**. A ready finding means the preview found
its dependencies, not that anything has been installed or tested live.

Requires Python 3.11+; the first release targets macOS and zsh. No third-party
Python dependencies are needed for the current commands.

```sh
python3 -m iterm2_utils doctor --json
python3 -m iterm2_utils plan --agent codex --features clipboard,shell --json
python3 -m iterm2_utils plan --agent claude --features shortcuts --shortcuts ctrl-q,resume
```

`doctor` inspects installed binaries and lists available features. `plan` accepts
`--agent codex|claude|both`, an explicit comma-separated `--features` selection,
optional `--shortcuts` and `--parent-profile` (default `Default`). Empty selections
fail without inspection. Only these two subcommands are currently available.
Neither command writes settings, installs dependencies, sources `.zshrc`, opens
iTerm2 or changes permissions. Each executable probe has a five-second timeout.

Features: `clipboard`, `status`, `notifications`, `restore`, `mcp`, `shell`,
`shortcuts`. Clipboard and restore apply only to Codex; a Claude-only selection
reports them as unavailable and excludes them from the supported plan selection.
For `both`, an unavailable Claude finding does not remove the Codex choice.
Shortcut choices are `ctrl-v-ru`, `alt-enter`, `ctrl-q` and `resume`; select each
explicitly. Ctrl+Q can interrupt or exit. Missing dependencies are attached to
individual features. Missing agents are never installed automatically.

Clipboard preview declares `tui.copy_on_select = "never"` and the shared iTerm2
`CopySelection = false` change. Codex profile matching uses `&codex`, never
`claude`. MCP is a separate choice with planned pinned dependencies
`mcp-server-iterm2==0.1.1` and `mcp<2`; it exposes terminal text to the agent.
Python API authorization and live runtime connections remain unverified and
require later setup. Peekaboo is detected only, never installed or launched.

Exit codes: `0` dependency preview ready; `2` invalid selection, conflict,
missing dependency or unavailable feature; `3` pending UI or a new session.
Blocking findings take precedence over pending UI. JSON includes an explicit
`installation_implemented: false` marker. Public output lists only dependency
names, parsed versions, capabilities and bounded findings, never raw command
output, environment variables or foreign MCP configuration.

Paths respect absolute `ZDOTDIR`, `CODEX_HOME`, `XDG_CONFIG_HOME`,
`XDG_DATA_HOME`, `XDG_CACHE_HOME`; relative overrides are ignored. Claude settings
are located at `~/.claude/settings.json`. `ITERM2_APP` selects an explicit app
bundle (invalid overrides fail closed); otherwise discovery tries
`/Applications/iTerm.app`, then `~/Applications/iTerm.app`. Info.plist identity
and bundle executable are validated. iTerm2 itself is never launched. Its
bundled `it2 --help`, when available, is inspected for supported capabilities.
Agent configuration files and their unrelated MCP env/auth blocks are not read.

Validation so far: standard-library unittest fixtures with TemporaryDirectory
HOME, fake executable files and a fake Runner. No live iTerm2 or agent behavior
has been verified by these tests. Parent profile existence, key compatibility,
hook trust, live MCP authorization, existing installation ownership and config
conflicts require subsequent implementation; preview readiness is not acceptance.

```sh
python3 -m unittest discover -v
```
