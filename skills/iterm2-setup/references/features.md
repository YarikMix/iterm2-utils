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
