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
Discovery reads native and dynamic iTerm2 profiles and retains only allowlisted
copy preference values. When clipboard is selected, the planner parses Codex
TOML to prepare a targeted tui.copy_on_select edit; unrelated configuration values
are never included in public output.

Validation so far: standard-library unittest fixtures with TemporaryDirectory
HOME, fake executable files and a fake Runner. No live iTerm2 or agent behavior
has been verified by these tests. Profile planning checks parent existence,
conflicting bindings and competing automatic switching rules. Hook trust, live
MCP authorization and end-to-end behavior still require later validation; preview
readiness is not acceptance.

```sh
python3 -m unittest discover -v
```

Profile changes are built in `DynamicProfiles/iterm2-utils.json`. They inherit the
chosen parent and merge its keyboard map; colors, fonts, the default profile and
normal shell startup are inherited. Codex matches `&codex`; a Claude hotkeys
profile matches `&claude` and has no Codex C bindings. Clipboard selects bilingual
physical C mappings, `tui.copy_on_select = "never"` and the shared iTerm2
`CopySelection = false` setting. Named `[profiles.<name>.tui]` overrides are
reported because different Codex invocations can use different profiles.

Cmd+V remains native paste. Manual copy does not guarantee completion timing for
large clipboard payloads; no paste delay or focus action is installed. The
optional resume shortcut sends `/resume` followed by an actual LF byte. Hotkeys
alone do not alter copy-on-select. Alt+Enter is omitted with an unavailable
finding when compatibility for the detected agent version is unverified.

Current Claude documentation describes Option+Enter after enabling Option as
Meta on macOS: https://code.claude.com/docs/en/interactive-mode. The profile sends
the equivalent ESC+CR bytes directly. The current documented release is exactly Claude Code 2.1.308
([release](https://github.com/anthropics/claude-code/releases/tag/v2.1.308),
published 2026-10-22). Only that exact version is treated as documentation-supported;
older, future and unknown versions fail closed. Live behavior remains unverified.

The profile-level `Prevent Automatic Profile Switching` flag is checked using
iTerm2 v3.7.6 source naming. A per-session override is not a global defaults key;
verify automatic switching in the target live session before accepting setup.

Codex Alt+Enter is source-verified for exactly 0.163.0 (`insert_newline` default
binding in `codex-rs/tui/src/keymap.rs`, tag `rust-v0.163.0`); other versions remain
unverified. A custom Codex TUI keymap can override `insert_newline`, so check the
selected configuration and target session before relying on this shortcut.

MCP — отдельная опция `mcp`, включаемая только для выбранных агентов.
Регистрация `iterm2-observe` использует строго
`uvx --with 'mcp<2' mcp-server-iterm2==0.1.1`. Установите `uvx` самостоятельно:
сервер требует Python **3.12+**, хотя установщику достаточно Python 3.11+.
Первый запуск uvx может загрузить пакет и подходящий Python; установщик не
устанавливает uvx скрытно. Нужны включённый Python API iTerm2 и разрешение пользователя.
Codex сохраняет регистрацию в `$CODEX_HOME/config.toml` (обычно `~/.codex/config.toml`);
Claude — в user scope (`~/.claude.json`), через штатный `claude mcp add --scope user`.
После регистрации перезапустите агент. Совпадающий чужой сервер не становится
собственностью установщика; несовпадение, отключённый сервер, другой scope или
неизвестный формат вывода CLI блокируют изменение. Claude `get` может проверять
доступность сервера; вызов ограничен таймаутом, его вывод не попадает в диагностику.
Live probe проверяет MCP initialize, список разрешённых инструментов и `list_sessions`;
он не посылает команды в терминал. Разрешены только чтение и метаданные из
проверенной версии; неожиданное имя инструмента блокирует готовность.
