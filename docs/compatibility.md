# Beta compatibility and verification

Release: **v0.1.0-beta.1**, 2026-10-23. Supported target: macOS + zsh with Python
3.11+ (stdlib installer). Linux CI is configured for pure/fixture behavior and export only;
it does not establish Linux product support. This beta has no stable-production
acceptance claim.

| Component | Pinned or source-level contract | Actual acceptance |
| --- | --- | --- |
| iTerm2 | Official zsh integration v3.7.6; session-status / Python API capability checks | Fixture app/preferences only; live iTerm2 unverified |
| Codex | --no-daemon required for reliable tab identity; Alt+Enter mapping sourced for 0.163.0 | Fake CLI/hooks; installed live agent unverified |
| Claude Code | Native cc-status integration checkpoint; Alt+Enter sourced for 2.1.308 | Fake CLI/hooks; native integration and live agent unverified |
| Python | Installer and selected hook/restore runtime 3.11+; MCP server requires 3.12+ | Local fixtures: 3.13.7. Remote macOS fixtures passed on 3.11 and 3.x (resolved to 3.14.8); see CI evidence below |
| MCP | mcp-server-iterm2==0.1.1, mcp<2, invoked through uvx | Fixture initialize/list_sessions/read-only allowlist; live server/TCC unverified |
| Notifications | terminal-notifier, it2, osascript; exact tab UUID targeting; explicit foreign-handler coexistence | Fixture delivery/focus only; macOS banners/click behavior unverified |
| Restore | Bundled Codex restore port, fzf dependency | Fixture lifecycle/transcript selection only; real dialogs unverified |

Local checks ran on Darwin 25.6.0 arm64, Python 3.13.7 and zsh 5.9.
[CI run 39866832243](https://github.com/YarikMix/iterm2-utils/actions/runs/39866832243)
passed both macOS jobs; the 3.x job used Python 3.14.8 and passed 321 Python tests,
37 restore zsh cases, and source/skill/export/build checks. Both Linux jobs failed
because the synthetic macOS fixture inherited the runner's platform. The fixture
now selects its platform explicitly; a subsequent remote run must confirm the
correction. This evidence does not establish Linux product support or live macOS
acceptance.

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
| Actual working/waiting/idle events from each installed agent | Unverified |
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
