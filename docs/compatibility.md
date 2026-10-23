# Beta compatibility and verification

Release: **v0.1.0-beta.1**, 2026-10-23. Supported target: macOS + zsh with Python
3.11+ (stdlib installer). Linux CI is configured for pure/fixture behavior and export only;
it does not establish Linux product support. This beta has no stable-production
acceptance claim.

| Component | Pinned or source-level contract | Actual acceptance |
| --- | --- | --- |
| iTerm2 | v3.7.6 native cc-status, minimum 3.7.6, executable sibling it2 with required flag checks; official zsh integration | Fixture app/preferences/runner only; live iTerm2 unverified |
| Codex | --no-daemon and strict explicit UUID; 0.163.0 hook enum has exactly 12 events and no StopFailure/Notification/PostToolUseFailure | Fake CLI/hooks/payloads; installed live agent and automatic API-error source unverified/unsupported respectively |
| Claude Code | Native cc-status integration checkpoint; Alt+Enter sourced for 2.1.308 | Fake CLI/hooks; native integration and live agent unverified |
| Python | Installer and selected hook/restore runtime 3.11+; MCP server requires 3.12+ | Local fixtures: 3.13.7. Remote macOS fixtures passed on 3.11 and 3.x (resolved to 3.14.8); see CI evidence below |
| MCP | mcp-server-iterm2==0.1.1, mcp<2, invoked through uvx | Fixture initialize/list_sessions/read-only allowlist; live server/TCC unverified |
| Notifications | terminal-notifier, it2, osascript; exact tab UUID targeting; explicit foreign-handler coexistence | Fixture delivery/focus only; macOS banners/click behavior unverified |
| Restore | Bundled Codex restore port, fzf dependency | Fixture lifecycle/transcript selection only; real dialogs unverified |

Local checks ran on Darwin 25.6.0 arm64, Python 3.13.7 and zsh 5.9.
The [CI matrix](https://github.com/YarikMix/iterm2-utils/actions/workflows/test.yml)
runs isolated fixtures and export checks on Linux and macOS with Python 3.11 and
current stable (3.x); macOS also runs explicit zsh contracts. Each run logs its
resolved Python version and, on macOS, zsh version. The verified macOS 3.x run
used Python 3.14.8. Consult the linked workflow for current job results. These
fixture checks do not establish Linux product support or live macOS acceptance.
These are historical beta CI results, not a CI run for the native status migration.

Native status evidence is separated by kind:

| Kind | Evidence / boundary |
| --- | --- |
| Source | iTerm2 v3.7.6 `7ce456b98db38d3f0bafd70ffec87752e69d5d58` supports Codex native working/waiting/idle/done/error, Interrupt and background tasks. Codex rust-v0.163.0 `83086188ae0614bd882818ff1aa23f3194962012` has no StopFailure; Stop does not reliably identify API failure. See the [design sources](superpowers/specs/2026-10-23-native-cc-status-design.md#9-первоисточники). |
| Fixture | Temporary HOME, fake bundle/runner and synthetic payloads cover native dependencies, registration, UUID/TMUX guard, delivery budgets, ownership and read-only doctor. Synthetic events establish adapter contracts, not a live renderer or real event source. |
| Live | Native migration remains unverified: no isolated Mac acceptance environment is available, and author settings/conversations are prohibited. No native migration CI run or live/model behavioral acceptance is claimed. |

`codex_error_event: limited` distinguishes known absence on 0.163.0 from an
unverified source on unknown versions. Backend/capability readiness, installed
files, child exit0 and `status_api: ready` do not verify loaded hook delivery.
External complete native sets are reused without ownership or adapter-only
input/compact guarantees; external legacy reuse is not a native migration.

Automated acceptance uses TemporaryDirectory HOME, fake app bundles, preference
adapters and CLI runners. All seven feature IDs can be selected explicitly;
unselected features stay disabled. Ownership/CAS, independent feature checkpoints,
partial/full uninstall, shared runtime, foreign settings preservation and source
checkout independence are covered by contracts. Export smoke extracts the archive,
moves its fixture source checkout away, runs CLI contracts, installs fixture
runtime and deletes the extracted source before testing installed entry points.

No isolated macOS account/VM or separately verified app-preferences environment
was available for this release preparation. The author's current installation
was not used for acceptance. These cases remain **live-unverified**:

| Live case | Beta status |
| --- | --- |
| Copy Cmd+C/Ctrl+C in EN/RU, no extra command, profile start/exit | Unverified |
| Selected hotkeys' emitted bytes; shell marks/navigation | Unverified |
| Actual startup, working, input/permission waiting, Stop/done/idle from Codex 0.163.0 + iTerm2 3.7.6 and a recorded Claude version | Unverified |
| Parallel subagents, compact, two explicit UUIDs, bundle update and API unavailable | Unverified |
| Synthetic StopFailure renderer; real Codex 0.163.0 API failure | Renderer unverified; real StopFailure source absent/unsupported |
| Completion/attention banners, foreground suppression and click to correct tab | Unverified |
| Interrupt without false completion | Unverified |
| fzf resumes only selected conversations with preserved CODEX_HOME/cwd | Unverified |
| MCP reads a test session, permission flow and no command-execution tools | Unverified |
| UI/TCC, hook trust, native Claude integration and existing-session profile switch | Unverified |
| Fresh agent discovers and follows the setup skill end to end | Unverified |

Task10's pre-authoring fresh Claude process used --bare, disabled built-in tools,
strict fixture MCP and no persistence. Both temporary-HOME and inherited-HOME
attempts returned authentication_failed before inference (0 tokens). No model
behavior baseline or behavioral GREEN was obtained. CLI contracts and structural
skill checks establish only their named contracts; scripted tool calls are not
proof of an agent refusing a bypass. No authentication was changed to run tests.

Source identity and exact bundled hashes are recorded in
[sources.lock.json](../sources.lock.json); [notices](../THIRD_PARTY_NOTICES.md)
separate package MIT, upstream status MIT and official shell integration GPL.
Mutable branch dependencies are not used. A newer local notification snapshot
has recorded source hashes but no public commit identity; the public base and
adaptation are disclosed in notices. No code or settings must be fetched from
that source installation at runtime.
