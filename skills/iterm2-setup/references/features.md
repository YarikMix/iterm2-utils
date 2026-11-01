# Feature choices and dependencies

| Feature | Result and boundary | Additional dependency |
| --- | --- | --- |
| `clipboard` | Codex manual Cmd+C/Ctrl+C in EN/RU, selection auto-copy off | Codex |
| `status` | Native working/waiting/done/idle for an explicit tab UUID; error depends on a verified event source | Python 3.11+; Codex requires compatible iTerm2 3.7.6+ cc-status/it2 pair |
| `notifications` | Completion/attention notifications, independently of visible status | Python 3.11+, terminal-notifier |
| `restore` | Codex conversation chooser, explicit selection before launch | Python 3.11+, fzf, compatible Codex --no-daemon |
| `mcp` | Separately selected terminal-reading MCP for selected agents | uvx; server Python 3.12+, Python API and human authorization |
| `shell` | Official zsh command marks/navigation in iTerm2 | zsh and iTerm2 |
| `shortcuts` | Explicit subset: ctrl-v-ru, alt-enter, ctrl-q, resume | Detected compatible agent version for alt-enter |
| `appearance` | Repository color/composite icon at interactive shell/Codex start; ordinary cd has no effect | Selected Python 3.11+ with `iterm2` SDK; enabled/authorized Python API |

First release: macOS + zsh. Most agent integrations require the selected agent
already installed. Never install a missing second agent implicitly. CLI plan
findings determine exact supported capabilities; a dependency preview is not
proof of a live connection.

Clipboard, restore and appearance are Codex-only. Codex automatic profile matching is
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

Selected Codex status uses this package's existing plan/install workflow to
register the adapter and 12 verified lifecycle hooks. There is no ready native
Codex installer in the iTerm2 menu. Claude keeps its official integration menu;
select only API, hooks and Session Status, leaving Workgroup and Auto-Enter off.
Do not ask for another feature choice or confirmation when the caller already
selected it. Explain new-session/human hook-trust requirements from findings.

Codex 0.163.0 has no StopFailure, Notification or PostToolUseFailure hook. Its
Stop payload cannot establish an API failure: native error rendering is not a
promise of automatic Codex API-error display. Doctor reports this as nonblocking
`codex_error_event: limited`; unknown versions have an unverified error source.

A complete external native hook set is reused without ownership or a second
status writer; adapter-only input/compact behavior is unavailable for that set.
An active recognized external legacy plugin is reused as a legacy backend, not
silently migrated. Include existing `--adopt-legacy` in plan/install only when
explicit migration was chosen. Owned beta.1 hooks migrate through update.
Notifications remain separately selected and keep their legacy transition model
only for notification decisions; it no longer writes visible Codex status.

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

## Repository appearance (eighth opt-in feature)

Only select `appearance` when requested; bootstrap selects none. First plan/install
requires `--appearance-config /path/to/rules.json`, with this strict schema:

```json
{"projects": [{"root": "/path/to/repo", "color": "#65A85A", "icon": "android-mail"}]}
```

Only `projects` at the top level; a nonempty list of objects containing exactly
`root`, `color`, `icon`. Root is absolute, color is `#RRGGBB`, icon is one of
`ios`, `android`, `kotlett`, `ios-mail`, `ios-cloud`, `android-mail`, `android-cloud`
or an absolute custom `.png` path. PNG limits: 16 MiB source, 4096 pixels per side,
128 MiB decoded data. No URLs or evaluated shell text. Most specific physical
root wins; duplicate physical roots are rejected. Unavailable external targets
are not created/scanned and do not apply. Never publish personal roots/rules.

Plan/dry-run validate files and the selected interpreter's `iterm2` import without
calling the API. Maintain an absolute `ITERM2_UTILS_PYTHON` override on subsequent
setup commands when choosing a nondefault existing Python. No startup pip or
image download. Install copies normalized rules and content-addressed custom PNGs
outside immutable runtime; seven builtins and SVG sources ship offline with MIT
attribution. Runtime survives removal of checkout/original JSON/PNG. Install
without a new JSON reuses owned rules; explicit new JSON replaces the owned set.
Update needs no original source. Changed/foreign values remain conflicts.

Use the ordinary plan/install/doctor/update/uninstall CLI workflow. Read pending
`appearance_api` and follow ui.md; successful read-only API access does not prove
color/icon rendering. Reconcile alone clears its API checkpoint. No status,
notifications, MCP, command marks or Claude appearance are enabled implicitly.

The physical calling shell cwd determines shell startup and interactive Codex
(including resume/fork/restore) appearance; `--cd` and conversation text do not.
No match, service command or API failure preserves current appearance. Only
session tab color/use-color and custom icon/mode change; Default/profile/title
stay intact. A bounded transition observer addresses APS for launch/return;
there is no daemon/chpwd hook. Actual APS/theme transitions and readability of
the paired symbols remain live pending. tmux/SSH need separate acceptance.
Uninstall removes only unchanged owned appearance resources, keeps shared
consumers, and does not reset/restart open tabs. Old custom hash copies remain
owned until uninstall; an empty config object may remain after removal.
