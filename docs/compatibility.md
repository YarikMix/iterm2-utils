# Beta compatibility and verification

Release: **v0.1.0-beta.1**, 2026-10-23. Supported target: macOS + zsh with Python
3.11+ (stdlib installer). Linux CI is configured for pure/fixture behavior and export only;
it does not establish Linux product support. This beta has no stable-production
acceptance claim.

## Codex launch verification — 2026-11-01

`launch-codex` supports a new Codex session on macOS + zsh with Python 3.11+.
It requires an explicit window ID, unique profile name/GUID, absolute cwd and
regular readable handoff file. No restore installation/receipt is required.
`bootstrap-skill --skill iterm2-launch --agent codex` is separate from the default
setup-only bootstrap. These launch contracts do not extend the existing status,
notification or hotkey version allowlists below.

Local final checks on Darwin 25.6.0 arm64, Python 3.13.7 and zsh 5.9:

| Exact command | Actual result |
| --- | --- |
| `python3 -m unittest discover -v` | 467 tests, PASS (90.028 s), including 8 export regressions and 75 restore Python tests |
| `/bin/zsh tests/test_codex_shell.zsh` | PASS: `Codex dispatcher tests passed` |
| `/bin/zsh tests/restore/test_codex.zsh` | PASS: `pass=37 fail=0` |
| `python3 tools/check_sources.py` | 27 pinned sources verified |
| `python3 tools/check_skill.py` | Both skills structurally valid; no behavioral evaluation |
| `python3 tools/check_export.py` | 109 explicit unique files; provenance/licenses/private-reference checks PASS |
| `python3 tools/build_release.py --destination dist` | Beta.1 archive and basename-only SHA-256 file built; no publication |
| `git diff --check` | PASS, no whitespace errors |

| Evidence | Scope / actual boundary |
| --- | --- |
| Codex source | Exactly rust-v0.166.0, `6ff1e1ca3b30fc8b914720681fcf5fe62e95f856`: canonical app-server `config/read`, effective `tui.alternate_screen` auto/always, `fullscreen_transcript` true and explicit `copy_on_select` never. Other Codex versions remain blocked/unverified. |
| iTerm2 source | v3.7.6, `7ce456b98db38d3f0bafd70ffec87752e69d5d58`: explicit `it2 tab new --window --profile --command`, curated profile name/GUID and session profile/job variables. Runtime checks require the bundled CLI flags; later versions have no new live acceptance claim. |
| Fixture transport | Extracted release imports the `runtime` namespace and launches through the actual bundled `ITerm._run` using fake executable `it2`, with one tab and no restore receipt. Both default setup and explicit launch bootstrap run from the archive. |
| Standalone restore | Fixture install survives deletion of its source checkout, compressed archive and extracted runtime source; installed help and NUL-protocol restore list/open/cancel remain usable. |
| Structural skills | Default validator checks setup and launch; an explicit directory still checks only that skill. No agent behavior is established. |
| Behavioral skills | Launch held-out baseline RED and GREEN are **BLOCKED**, not run: no authorized isolated inference endpoint/auth was supplied. No model invocation or behavioral PASS is claimed. |
| Live launch/clipboard | **Live-unverified**: no isolated Mac account/VM was supplied. No real settings, GUI, auth or developer sessions were inspected/launched. |

The configuration probe runs the preserved interactive login zsh from the selected
cwd with process-local `CODEX_RESTORE_NO_AUTO=1`. It starts its own bounded
app-server process group, performs initialize → initialized → config/read and
never starts a thread/turn. Ordinary app-server initialization, shell startup,
state/log creation and recovery SQLite are part of an authorized launch; this
is **not filesystem-read-only**. A temporary CODEX_SQLITE_HOME alone is not a
complete DB isolation guarantee. Development exercises only fake config
transport and synthetic processes in temporary homes.

Supported shell identities are direct binary, exact bundled dispatcher/restore
bodies and their chains, simple passthrough and a wrapper adding only
`--no-daemon`. Unknown/profile-changing wrappers and aliases block launch. The
identity guard rechecks executable/version, HOME/CODEX_HOME/ZDOTDIR, relevant
functions, restore root identity and selected Python before the actual `codex -C` call;
restore helper content provenance is checked during preflight only. The guard
does not add model/API/config overrides or `--no-alt-screen`.

The profile reader requires one live name/GUID and a matching materialized
`New Bookmarks` entry with explicit Keyboard Map and global `CopySelection=false`.
Its preference snapshot is not a direct runtime-binding read: a stale external
plist with the same name/GUID may be indistinguishable; concurrent profile
changes after preflight are not atomic. Config contents can likewise change
between inspection and launch; the identity guard is not a lock over settings.
`session.jobName=codex` alone can describe a helper. Launch success additionally
requires `session.processTitle` (argv0) and `session.commandLine` to match the
complete expected invocation: argv0, up to two `--no-daemon` flags contributed
by supported wrappers, `-C`, cwd and the exact handoff prompt. iTerm joins argv
with spaces without escaping; comparison uses that representation, not shell
parsing. Missing/malformed/mismatching evidence remains `created_unverified`.
These are cached process observations, not proof that the process still lives
at response time or has accepted the task. A fresh matching ack is separately
required for receipt; neither observation proves Cmd+C → Cmd+V.

Still required in an isolated Mac account/VM: launch from another agent, inspect
the profile before interaction, exactly one Codex, fresh request/cwd/thread ack,
manual copy/paste in ABC and Russian without auto-copy or manual restart, and an
unchanged neighboring session. Fixture, source and structural checks do not
replace these observations. This task makes no new CI or live acceptance claim.

## Earlier integration verification

Native migration local verification, 2026-10-23: the exact tested **pre-documentation
code snapshot** is commit `00232d7bf7f240ab085bac89c17ad7002e659b94`.
The verification matrix update follows that commit and changes documentation only;
this SHA identifies the code/tests that passed, rather than a self-referencing final
documentation commit. No native migration CI, model-behavior or live run is claimed.

| Local command / scope | Actual result |
| --- | --- |
| `python3 -m unittest discover -s tests -t . -v` | 413 tests, PASS; includes the 6 export tests and extracted-archive installed hook smoke |
| `/bin/zsh tests/test_codex_shell.zsh` | PASS (`Codex dispatcher tests passed`) |
| `/bin/zsh tests/restore/test_codex.zsh` | 37 tests, PASS (`pass=37 fail=0`) |
| `python3 tools/check_sources.py` | 27 pinned sources verified; unchanged vendor hashes/licenses |
| `python3 tools/check_skill.py` | Structure valid; no behavioral evaluation |
| `python3 tools/check_export.py` | 102 explicit, unique files; provenance/licenses/private-reference checks PASS |
| `python3 tools/build_release.py --destination dist` | Deterministic beta.1 archive and basename-only SHA-256 file built; archive extraction/install independence covered by the export tests |

| Component | Pinned or source-level contract | Actual acceptance |
| --- | --- | --- |
| iTerm2 | v3.7.6 native cc-status, minimum 3.7.6, executable sibling it2 with required flag checks; official zsh integration | Fixture app/preferences/runner only; live iTerm2 unverified |
| Codex | --no-daemon and strict explicit UUID; 0.163.0 hook enum has exactly 12 events and no StopFailure/Notification/PostToolUseFailure | Fake CLI/hooks/payloads; installed live agent and automatic API-error source unverified/unsupported respectively |
| Claude Code | Native cc-status integration checkpoint; Alt+Enter sourced for 2.1.308 | Fake CLI/hooks; native integration and live agent unverified |
| Python | Installer and selected hook/restore runtime 3.11+; MCP server requires 3.12+ | Native migration local fixtures: 3.13.7. Historical beta macOS fixtures passed on 3.11 and 3.x (resolved to 3.14.8); no new CI run |
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

Migration prerequisite source evidence, 2026-10-24: approval-only TUI policy is
allowlisted for exactly Codex 0.163.0 and 0.164.0. For rust-v0.164.0, release commit
`6aaac694803004a63c6f393d153c96d22521a6b9`,
[`notifications.rs`](https://github.com/openai/codex/blob/6aaac694803004a63c6f393d153c96d22521a6b9/codex-rs/tui/src/chatwidget/notifications.rs#L72)
maps exec/edit/elicitation approvals to `approval-requested` (lines 75–77) and
filters custom notification lists by exact type name (lines 94–98).
The [Notifications schema](https://github.com/openai/codex/blob/6aaac694803004a63c6f393d153c96d22521a6b9/codex-rs/core/config.schema.json#L3501)
accepts boolean or string-array values; [`tui.notifications`](https://github.com/openai/codex/blob/6aaac694803004a63c6f393d153c96d22521a6b9/codex-rs/core/config.schema.json#L5107)
uses that definition. Unknown/future versions (including 0.165.0) remain blocked.
This evidence does not extend the Alt+Enter allowlist, registered hook events or
native error guarantees; the 0.164.0 error source remains limited/unverified.
Discovery uses only the read-only `terminal-notifier -version` probe, with no
notification sent. Source inspection and fixture checks do not establish live
delivery, loaded hooks or a new CI result.

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
If a known legacy plugin is enabled after the package already owns an active
status writer (including beta.1), update and doctor report a conflict. They do
not silently retire or adopt either writer. Explicit `--adopt-legacy` can disable
the recognized plugin transactionally; removing package status preserves the
external plugin and remaining independently selected consumers.

Final-review regressions also run synthetic native processes and grandchildren,
then send real SIGTERM to the hook during delivery and before `Popen.pid` is
registered. Both cases verify group cleanup, bounded exit0/`{}` output and restored
signal handlers. Real `/bin/sh` fixture execution confirms that `nice -n 5` and
leading output redirection invoke native; discovery treats those shell forms as
conflicts, and install leaves the fixture unchanged. Ordinary status names in
arguments, comments and redirection targets remain negative classifier cases.
These subprocess tests do not use iTerm2 or real agent settings.

Automated acceptance uses TemporaryDirectory HOME, fake app bundles, preference
adapters and CLI runners. All seven feature IDs can be selected explicitly;
unselected features stay disabled. Ownership/CAS, independent feature checkpoints,
partial/full uninstall, shared runtime, foreign settings preservation and source
checkout independence are covered by contracts. Export smoke extracts the archive,
moves its fixture source checkout away, runs CLI contracts, installs fixture
runtime and deletes the extracted source before testing installed entry points.
The installed `hook.py` reaches only its selected fake bundle with an explicit,
matching terminal UUID and no inherited TMUX session. Replacing both native
utilities in that bundle is observed on the next event without changing installed
runtime bytes. Missing native/sibling utilities and `status: false` produce no
native call; PATH traps remain unused. Synthetic raw prompt content stays out of
the forwarded payload, caches, receipts and runtime. Application binaries are
neither exported nor owned, and the retained vendor helpers keep their pinned
source/license metadata.

No isolated macOS account/VM or separately verified app-preferences environment
was available for this release preparation. The author's current installation
was not used for acceptance. These cases remain **live-unverified**:

| Live case | Beta status |
| --- | --- |
| Copy Cmd+C/Ctrl+C in EN/RU, no extra command, profile start/exit | Unverified |
| Selected hotkeys' emitted bytes; shell marks/navigation | Unverified |
| Native synthetic start/prompt/stop/interrupt/StopFailure renderer, including working/done/idle/error | Live-unverified; fixture adapter checks do not prove renderer behavior |
| Actual Codex 0.163.0 prompt/tool/permission/input/Esc/compact and the three adapter transformations with iTerm2 3.7.6 | Live-unverified |
| Two panels/two sessions, switching the active tab while a response runs; exact UUID targeting | Live-unverified |
| Parallel/detached subagents and main Stop; waiting/background completion after errors | Live-unverified; no local status fallback |
| Native Claude at a recorded version with notifications separately; absence of duplicate writers/banners | Live-unverified; no live Claude version recorded for this migration |
| API off / native unavailable / bundle updated; doctor setup/API/event-delivery distinction | Live-unverified; only fake bundle/dependency/doctor contracts passed |
| Real Codex 0.163.0 API failure | StopFailure source absent/unsupported, even if a synthetic renderer later passes |
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

## Repository appearance — local verification, 2026-11-01

Fixture checks and separately authorized native checks are recorded below;
this is not a new CI execution claim.
The eighth opt-in feature `appearance` is Codex-only, macOS/zsh, selected Python
3.11+ with the official `iterm2` SDK. Source and installed runtime include seven
original transparent PNGs and their SVGs under the package MIT license.
[Setup, strict JSON and lifecycle](repo-appearance.md).

| Scope | Actual evidence |
| --- | --- |
| Rules and selection | Isolated rules fixtures: physical roots/symlinks, nested roots/path boundaries, missing external targets, invalid schema/colors/icons |
| API/helper | Fake API/clock/process fixtures: explicit matching UUID only, bounded failures/timeouts, session properties only; no real SDK/API authorization or rendering claim |
| Shell/Codex/restore | Fake Codex and helper; argv/status/stderr, once-only source, service exclusions, physical cwd, no cd assignment, restore dispatch and child absence while the same interactive shell remains alive |
| Lifecycle | TemporaryDirectory HOME, fake Runner: opt-in, selected SDK import prerequisite, no-write plan/dry-run, CAS/update/reinstall/uninstall, partial consumers and API pending/reconcile |
| Delivery | Focused payload/export regression suite; seven PNG+SVG pairs, helper/licenses, byte-sensitive release/fingerprint, missing/symlink rejection, no arbitrary image/state export; installed builtin/custom selection after checkout/original JSON/PNG deletion |
| `python3 -m unittest discover -v` | 518 tests, PASS (97.416s), one case-sensitive-filesystem skip, Python 3.13.7; final controller run after ownership fixes, including extracted-archive payload/CLI tests |
| `/bin/zsh tests/test_codex_shell.zsh` | PASS, Codex dispatcher tests passed |
| `/bin/zsh tests/test_appearance_shell.zsh` | 16 tests, PASS (7.859s), zsh 5.9 |
| `/bin/zsh tests/restore/test_codex.zsh` | 37 tests, PASS (31.707s), pass=37 fail=0 |
| `python3 tools/check_sources.py` | 27 pinned sources verified; upstream provenance retained |
| `python3 tools/check_skill.py` | Structure valid; no behavioral evaluation |
| `python3 tools/check_export.py` | 124 explicit unique files; licenses/provenance/private-reference checks PASS |
| `python3 tools/build_release.py --destination dist`; `git diff --check` | PASS; allowlisted beta.1 archive/checksum built, final whitespace output empty |

| Appearance live case | Status |
| --- | --- |
| Enabled/authorized Python API in the selected interpreter/session | PASS: authorized local appearance-only install and explicit-session API access, iTerm2 3.7.6, Python 3.13.7 |
| Five selected color/icon combinations and normal-size symbol readability | PASS: 5/5 fresh native sessions matched exact color/icon properties; captured native tab bar inspected at normal size |
| Existing APS on Codex entry and exit | PASS: native auto-exiting executable named Codex, installed dispatcher/restore wrapper and real APS; matched, no-match, manual color/icon and reassignment cases all passed |
| Real Codex baseline | One controlled real executable run, without a model prompt: late running and returned style preserved. An earlier isolated matched-style loss was not reproduced; its cause is not claimed fixed |
| Ordinary cd and launch without a matching root | PASS: cd preserved style; no-match launch/return preserved both assigned and manually changed pairs. Separate native checks preserved exact base/light/dark color values |
| Resume/fork/restore picker, actual theme switching and disconnected SSD | Fixture coverage; not exercised live. A working SSD was not disconnected during other work |
| Failure paths and own temporary-tab cleanup | Failure/cancellation paths covered by fixtures; no real permission revocation. All five final own sessions and the separate debug session closed by exact IDs; foreign sessions preserved |

The fixture table uses isolated settings and fake adapters. The separate live
table records authorized local installation and native observations; private
rules, paths, receipts and screenshots are excluded from the public package.
The final post-install check passed five startup and four APS scenarios. Native
API failures and profile changes later than the bounded observer remain limits;
connectivity alone does not establish rendering or APS behavior.
