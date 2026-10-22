# Feature choices and dependencies

| Feature | Result and boundary | Additional dependency |
| --- | --- | --- |
| `clipboard` | Codex manual Cmd+C/Ctrl+C in EN/RU, selection auto-copy off | Codex |
| `status` | Working/waiting/idle for an explicit tab UUID; Claude native cc-status | Python 3.11+, supported iTerm2 capability |
| `notifications` | Completion/attention notifications, independently of visible status | Python 3.11+, terminal-notifier |
| `restore` | Codex conversation chooser, explicit selection before launch | Python 3.11+, fzf, compatible Codex --no-daemon |
| `mcp` | Separately selected terminal-reading MCP for selected agents | uvx; server Python 3.12+, Python API and human authorization |
| `shell` | Official zsh command marks/navigation in iTerm2 | zsh and iTerm2 |
| `shortcuts` | Explicit subset: ctrl-v-ru, alt-enter, ctrl-q, resume | Detected compatible agent version for alt-enter |

First release: macOS + zsh. Most agent integrations require the selected agent
already installed. Never install a missing second agent implicitly. CLI plan
findings determine exact supported capabilities; a dependency preview is not
proof of a live connection.

Clipboard and restore are Codex-only. Codex automatic profile matching is
`&codex`, never `claude`; a Claude shortcut profile has no Codex copy bindings.
Only clipboard selects `tui.copy_on_select = "never"` and shared iTerm2
`CopySelection = false`; shortcuts alone leave copy-on-select unchanged.
Cmd+V stays native paste. Large clipboard text can race copy completion; no fixed
paste delay or focus automation guarantees completion.

`ctrl-q` may interrupt or exit. `resume` sends /resume plus LF. Only selected
shortcut IDs are installed; profile inheritance preserves the chosen parent.
Alt+Enter depends on the exact compatibility reported by doctor/plan.

MCP pins `mcp-server-iterm2==0.1.1` with `mcp<2`, registered as `iterm2-observe`
using `uvx --with 'mcp<2' mcp-server-iterm2==0.1.1`. Setup itself needs Python
3.11+; this server needs **3.12+**. uvx may download the pinned server and an
appropriate Python on first use; explain this before running the selected setup.
Do not replace another server with the same name or expose its secrets.

Hooks target an explicit tab UUID; never substitute the active tab. Trust is
confirmed by the human. Existing status installations and migration conflicts
are reported; adopting legacy resources requires an explicit migration choice.

## Independent agent choices and runtime requirements

Make separate plan/install calls for different choices, for example Codex
clipboard/status and Claude notifications/MCP. A later agent choice never expands
previous features to it. Read `selection.agent_features` and `agent_shortcuts` for
exact intent; aggregate features is only their union. Additional shortcuts are
also recorded per agent. `uninstall --agent AGENT --features CSV` removes only
those pairs; omitting `--agent` removes those features across the recorded agents.

Hooks and restore require a detected runtime Python >=3.11. An absolute
`ITERM2_UTILS_PYTHON` override selects that interpreter for discovery and generated
hooks/restore; preserve it on subsequent setup commands. Old/unknown versions
block runtime features only. Notifications additionally require all three
transports: terminal-notifier, it2 and osascript. A written checkpoint does not
confirm notification permission or a live API connection.

A known existing notifier/status plugin needs a separate choice. Leave package
notifications unselected to retain the external system alone. Only after the
caller chooses coexistence, include `--coexist-notifications` in both plan and
install. It persists for updates for the chosen agents, preserves every foreign handler and can produce
duplicate banners. Never infer coexistence from ordinary notification opt-in or
remove foreign hooks by command-name heuristics.
