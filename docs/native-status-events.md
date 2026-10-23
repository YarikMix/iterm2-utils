# Native Codex status contracts

The native backend requires iTerm2 **3.7.6 or newer**, bundle identifier
`com.googlecode.iterm2`, and executable sibling utilities
`Contents/Resources/utilities/cc-status` and `it2` in that bundle. Discovery runs
only read-only `it2 --help` and `it2 set-status --help`; it never invokes
`cc-status`, including with `--help`, because that program consumes hook stdin.
The status help must include all six flags: `--background-tasks`,
`--background-tasks-delta`, `--turn-open`, `--if-turn-open`,
`--if-background-tasks`, `--json`. Passing this gate establishes capability,
not live delivery or renderer acceptance. Utilities remain in the app bundle;
the package neither vendors them nor owns the standard iTerm2 symlink.

The released source contracts used for this migration are:

- iTerm2 v3.7.6, commit `7ce456b98db38d3f0bafd70ffec87752e69d5d58`:
  [HookEvent.swift](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/cc-status/Sources/cc-status/HookEvent.swift),
  [Addressing.swift](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/cc-status/Sources/cc-status/Addressing.swift),
  [main.swift](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/cc-status/Sources/cc-status/main.swift),
  [It2Runner.swift](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/cc-status/Sources/cc-status/It2Runner.swift).
- Codex rust-v0.163.0, commit `83086188ae0614bd882818ff1aa23f3194962012`:
  [HookEventName](https://github.com/openai/codex/blob/83086188ae0614bd882818ff1aa23f3194962012/codex-rs/protocol/src/protocol.rs#L1688)
  and [Stop payload](https://github.com/openai/codex/blob/83086188ae0614bd882818ff1aa23f3194962012/codex-rs/hooks/src/events/stop.rs).

Codex registers exactly these **12** events: `SessionStart`, `SessionEnd`,
`UserPromptSubmit`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`,
`PostCompact`, `SubagentStart`, `SubagentStop`, `Stop`, `Interrupt`.
`runtime.events.CODEX_EVENTS` owns this list; `EVENTS` is its compatibility alias.
Normalization also accepts Claude's `Notification`, `StopFailure` and
`PostToolUseFailure`, without registering them in Codex.

The [iTerm2 example hooks](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/tests/codex-hooks.json)
include `StopFailure`, which the released Codex enum lacks. Copying that example
verbatim would register an unsupported event. Codex `Stop` does not reliably
identify a failed API response, so native support for rendering `error` does not
establish a real error event source in Codex 0.163.0. A synthetic `StopFailure`
can test the renderer only. Future schemas require separate confirmation.

Addressing accepts an explicit UUID, bare or in `w0t0p0:UUID` panel form, from
`ITERM_SESSION_ID` or `TERM_SESSION_ID`; lowercase UUIDs normalize to uppercase.
Every present source must be valid and both must agree. A present empty source,
conflict, malformed value or mismatching payload `terminal_uuid` gives a no-op.
No active-panel fallback is allowed. The native adapter supplies normalized
`TERM_SESSION_ID` for local-panel delivery; tmux support requires separate work.

External native reuse requires one direct command-hook per event for all **10**
events above excluding `PreCompact` and `PostCompact`, with exact arguments
`--agent codex`. Commands are parsed as shell tokens; matchers must be absent,
empty or `*`, and executable paths must resolve to the selected bundle's
`cc-status`. A standard symlink is accepted only when it resolves there.
Partial sets, duplicates, another app copy, shell wrappers, extra native events,
restricted matchers or simultaneous known legacy writers are conflicts.
Unrelated foreign hooks are preserved without guessing their executable behavior.
This external integration does not promise the adapter's input/compact extensions.
Inventory contains only `codex-native-status: {enabled: true}` or
`codex-native-status: {conflict: true}`; hook/config bodies and private strings
are not retained. Inspection never runs hooks or reads foreign executable bodies.

These contracts are checked offline with temporary homes, fake bundles and runners.
Runtime and tests make no network requests to the linked sources. Live sessions,
hook trust, API authorization and displayed status remain separate acceptance work.
