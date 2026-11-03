# Beta compatibility and verification

Release: **v0.1.0-beta.1**, 2026-10-23. Supported target: macOS + zsh with Python
3.11+ (stdlib installer). Linux CI is configured for pure/fixture behavior and export only;
it does not establish Linux product support. This beta has no stable-production
acceptance claim.

## Codex API launch and exact resume — 2026-11-01

Current `launch-codex` supports mutually exclusive `--handoff ABS_FILE` and
`--resume SESSION_UUID`; both require `--window WINDOW_ID --profile PROFILE_NAME
--cwd ABS_DIR`. Existing handoff calls remain compatible. Resume validates one
exact interactive transcript under effective `CODEX_HOME/sessions`; it never
selects last/picker/fork or sends a new task. The skill matches relevant history,
uses its confirmed cwd unless the user requests another, and reports an already
open dialog instead of creating a duplicate without an explicit request.

Official `iterm2` SDK must be importable by the Python 3.11+ running the CLI.
It is loaded lazily for launch and explicitly selected API features; bootstrap
and unrelated features do not require it. No automatic installation, environment search or permission
changes occur. **Live-tested SDK version: 2.23**, with Python 3.13.7 and Codex 0.166.0
and iTerm2 3.7.6 on 2026-11-02. Existing profile/config compatibility checks remain in effect.

The SDK addresses an explicit window and creates once via
`Window.async_create_tab(profile=..., command=...)`. The custom command is
supplied at creation, overriding a profile's startup command. No terminal input
or `it2 tab new --command` fallback is used. Connection/preflight operations have
a 10-second bound; creation plus observations share 30 seconds. Timeout after
submission is `unknown` or `created_unverified` with any known IDs preserved;
there is no retry, tab close or process kill.

JSON retains `mode=launch_codex`, IDs, profile, findings and exits 0/2/3; it adds
`launch_mode=handoff|resume` and `resume_session_id` (dialog UUID for resume,
otherwise null). `session_id` identifies an iTerm2 terminal, a different namespace.
`launched`/0 requires exact identity/profile and complete command evidence;
`blocked`/2 means no creation; `unknown`/3 and `created_unverified`/3 are uncertain.
`processTitle` is argv0, while `commandLine` is argv0 plus exact mode arguments
and zero to two supported wrapper `--no-daemon` flags before those arguments.
The verifier accepts the exact space-joined representation or safely tokenized
quoted text equal to the same complete argv; it never evaluates that text.
Malformed quoting, extra arguments, a bare `codex`, help/version, wrong cwd/UUID
or partial observation fail.

Handoff launch and fresh receipt are separate results, with safe bounded reads
and a separate 120-second ack wait. Resume has no ack or new prompt. A restored
history claim requires additional read-only recovered history/identifier in the
exact target tab. Otherwise report: “команда resume запущена, восстановление
истории не подтверждено”. No prompt or `/status` is injected for verification.

Fixture/structural checks, offline behavioral simulations and live acceptance
are distinct. Current behavioral evidence is recorded in
[skill results](https://github.com/YarikMix/iterm2-utils/blob/main/docs/superpowers/validation/2026-11-01-launch-api-resume/skill-results.md).
The [final acceptance matrix](https://github.com/YarikMix/iterm2-utils/blob/main/docs/superpowers/validation/2026-11-01-launch-api-resume/acceptance.md)
records the 2026-11-02 checks, controller live observations and selected
installed-skill bootstrap separately. Final tested code/skill snapshot:
`0ac1a75642010b33b6a3365ecb015ecbf163a5cf`, Darwin 25.6.0 arm64,
Python 3.13.7 and zsh 5.9. This acceptance update changes documentation only.
Independent branch review's previous-restore compatibility finding was fixed and
passed scoped re-review; the later live argv fix also passed scoped review.

| Command / evidence | Actual result |
| --- | --- |
| `python3 -m unittest discover -v` at the final code snapshot | 611 tests in 134.552s, OK (skipped=1); 610 passed, one case-insensitive-filesystem skip; baseline 577 → 611 (+34) |
| `/bin/zsh tests/test_codex_shell.zsh` at the earlier hermetic checkpoint | PASS: dispatcher contracts; no separate count emitted |
| `/bin/zsh tests/test_appearance_shell.zsh` at that checkpoint | 22 tests, OK |
| `/bin/zsh tests/restore/test_codex.zsh` at that checkpoint | 37 tests, OK; pass=37 fail=0 |
| `python3 tools/check_sources.py` at that checkpoint | 27 pinned sources verified |
| `python3 tools/check_skill.py` after the final documentation update | 2 structurally valid skills; no behavioral evaluation |
| `python3 tools/check_export.py` after the final documentation update | 134 allowlisted files; provenance/licenses/private-reference checks passed |
| `git diff --check` after the final documentation update | PASS, no whitespace errors |

The one live handoff invocation returned **created_unverified/3** in 32.25s:
the observed command line quoted the prompt, exposing the now-fixed verifier
mismatch. A Codex folder-trust prompt appeared and later disappeared; the
controller did not confirm it or change trust, and no explicit human action is
attributed. The first tab was retained without retry. Subsequent continuation,
ack fields/actual thread/canonical cwd and unique marker were verified safely,
and exact inventory/profile GUID/job/parsed argv were observed read-only. The ack
was written **244.62s after launch**, outside the original 120-second receipt
window. This is later receipt/target evidence, not a timely handoff PASS, a changed
historical CLI result or a fresh successful handoff run of the final fix.

After clean exit of that own Codex, one exact resume returned **launched/0** in
**6.4s**; the exact own dialog/cwd and recovered marker/history were verified
read-only without a new prompt. Both own tabs were then closed by exact IDs;
final inventory confirmed them absent and the parent session present. Selected
Codex launch-skill bootstrap dry-run was ready, apply succeeded through CAS, and
all three installed files plus receipt bytes matched. No user settings, profiles
or permissions were edited. **Clipboard EN/RU was not checked.**

The recorded 30/30 offline behavioral decisions apply to the sampled `29f5073`
instruction, not to fresh samples of the later quoted-argv paragraph amendment.
Its exact code regression coverage and current skill fingerprint are recorded in
the linked results. Final release build/checksum are in the acceptance matrix;
no new CI or publication is claimed. The earlier matrix below is a historical
snapshot of the superseded transport, not current API launch acceptance.

## Earlier Codex launch snapshot — 2026-11-01 (superseded transport)

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

## Repository appearance — historical verification before cd support, 2026-11-01

The following results describe the earlier startup/Codex-only behavior. They are
retained as historical evidence; in particular, “cd preserved style” below is
superseded by the current cd/reset contract and is not its acceptance evidence.

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

## Repository appearance cd/reset — fixture verification, 2026-11-01

Current behavior extends the existing selected appearance feature: startup and
ordinary cd apply the most specific available physical root; outside all rules
disables base/light/dark Tab Color and hides the custom icon without writing a
default RGB. The native zsh chpwd hook belongs to its interactive shell, registers
once and preserves foreign hooks. No new flag/schema, daemon or polling is added.
The historical native results above do not verify this new behavior.

| Fixture command / scope | Actual evidence |
| --- | --- |
| `python3 -m unittest tests.test_appearance_runtime tests.test_appearance_rules -v` | 75 tests, PASS, one case-sensitive-filesystem skip; fake API reset/assignment, light/dark, launch/return and stale native-record ownership |
| `/bin/zsh tests/test_appearance_shell.zsh` | 22 tests, PASS (15.169s); physical cwd, single registration, foreign hooks, owner PID, ALLEXPORT/nested/noninteractive isolation, parent completion before child target, quiet API deadlines/cd0, worker cleanup and rapid ordering |
| `/bin/zsh tests/test_codex_shell.zsh` | PASS: `Codex dispatcher tests passed`; no separate count emitted |
| `/bin/zsh tests/restore/test_codex.zsh` | 37 tests, PASS: `pass=37 fail=0`; real fixture cd still reaches native dispatcher/restore |
| `python3 -m unittest tests.test_payload tests.test_appearance_feature tests.test_shell tests.test_export -v` | 48 tests, PASS; installed builtin/custom icon selection and outside reset after source JSON/PNG/checkout deletion; installed zsh source still emits shell-phase physical startup → project → outside events through a fake executable boundary |
| Strengthened existing partial-uninstall regression | 1 test, PASS after adding foreign shell text/function preservation; appearance source removed from generated startup, other runtime consumers retained |
| Delivery regressions against the copied pre-change snapshot | 2 tests, 2 expected failures: no outside reset and no cd hook event. Current focused run above passes both; the working tree was not reverted |

All development runs use temporary HOME and fake API/executable adapters, with no
real settings, SDK authorization, GUI or model invocation. After the final source
freeze, `python3 -m unittest discover -v` passed 577 tests (576 OK, one
case-sensitive-filesystem skip) in 116.194s. The same gate passed shell22,
restore37, dispatcher, 27 pinned sources, two structural skills, export131,
131 unique regular archive entries with 131 byte comparisons, checksum and
whitespace checks. Structural skill validation does not evaluate agent behavior;
no new CI run is claimed. Startup and each cd now wait for helper completion,
usually one short API roundtrip; unavailable API/filesystem can delay each event
roughly the existing 2.8s budget while successful cd remains exit0.

| New live acceptance case | Status |
| --- | --- |
| Fresh outside startup and ordinary cd through five selected roots, subdirectory and outside | PASS on iTerm2 3.7.6/Python 3.13.7: exact color/icon for all five; outside has base/light/dark use-color=false, Icon=0 and empty path |
| Subprocess cd and own neighboring control session | PASS: subprocess kept parent appearance; neighboring control unchanged |
| Rapid A → B → outside with no late recoloring | PASS, including a delayed final-state check |
| Auto-exiting native Codex under real APS in a project and after outside cd | PASS with a local native executable named codex; no model/network prompt. Project return followed immediately by cd retained the new project after 3.2s; outside return retained default |
| Normal-size tabbar readability | PASS: exact owned-window crop, five distinct colors and built-in Android/iOS + Mail/Cloud composite icons plus Kotlett visible |
| Actual light/dark theme switching | Not newly performed; native reset flags for both variants verified, fixture properties covered |
| Resume/fork/restore picker and disconnected external target | Fixture coverage only; no new live run, do not disconnect a disk in use |
| Selected appearance-only install, API access and temporary-tab cleanup | PASS: matching dry-run/install preserved selection and reused owned rules; installed runtime bytes matched; no pending steps. All six captured own sessions closed and own window absence verified; working user sessions were not restarted |

Late APS changes beyond the existing bounded observer, tmux and other shells or
agents remain outside this change. Already running user shells are not updated
remotely; use a fresh tab or explicitly restart zsh to load the updated hook.
Uninstall does not reset or restart existing tabs. Raw native evidence, screenshots
and personal paths remain private and are excluded from the release.

## Branded repository icons — 2026-11-01, historical acceptance

At that checkpoint, delivery had nine builtin names: `ios`, `android`, `kotlett`, `ios-mail`,
`ios-cloud`, `android-mail`, `android-cloud`, `chrome-mail`, `chrome-cloud`.
The four mobile names are preserved with updated branded artwork; base ios,
android and kotlett images are unchanged. Six composites use variant B: larger
platform and a square service badge at bottom right. Mail uses white @ on blue,
Cloud its branded white contour on blue, and Chrome its official full-color mark.
Each ships offline as matching SVG and transparent 128×128 PNG. Public-source
provenance, transformations and brand ownership are in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md); third-party artwork is separate
from MIT code/original illustrations. Earlier seven-asset verification and
five-rule native observations above remain historical evidence.

| New verification scope | Status |
| --- | --- |
| Final full automated gate, shell regressions, sources/skills and archive byte/checksum verification | PASS: 578 tests (577 OK, one case-sensitive-filesystem skip), 120.633s; appearance22/restore37/dispatcher PASS; sources27/structural skills2/export135; archive135 unique regular entries,135 source-byte comparisons and basename-only checksum PASS |
| Selected preview/install with seven local rules; previous five triples and other consumers preserved | PASS: appearance-only dry-run/install, exact seven rules with previous five triples/order and selection preserved,18 installed asset byte comparisons. General plan still reports the pre-existing unrelated notifications policy limitation; notifications were not changed |
| Selected-interpreter SDK, authorized API and pending-step verification | PASS: existing Python3.13.7 SDK import and explicit-session native API access; previous authorization reused, install pending0. No new permissions or reconcile step required; offline diagnostic findings unchanged |
| Native six branded composites, unchanged Kotlett, seven colors, subdirectories and outside reset | PASS:27 checks, seven roots and one existing subdirectory per root, startup/outside default (all three use-color flags false, Icon0/path empty), rapid final state/no late writer and unchanged neighboring control. Native icon paths and bytes match the reviewed pairs |
| Normal-size tabbar readability in an exact owned-window crop | PASS on iTerm2 3.7.6:1200px owned window, eight tabs including outside control; all six brand pairs and Kotlett visible. All eight captured own sessions closed and own window absence verified; working user tabs preserved |
| New CI run | Not yet observed at this local evidence checkpoint; final PR checks report their own outcome |

Fixture/structural checks cannot establish native rendering or agent behavior.
Personal roots, source JSON and screenshots stay private and outside the archive.
Actual theme switching, a fresh Codex/APS run and a new restore-picker run were
not repeated for this artwork-only change; directory/observer behavior is unchanged.
Running shells require a fresh tab or an explicit `exec zsh` to load updated hooks;
working user tabs are not restarted automatically.


## Apple iOS artwork — 2026-11-02, scoped acceptance verified

Current delivery keeps all nine builtin names and18 asset files. Only `ios`,
`ios-mail` and `ios-cloud` replace the former phone with light Apple `#E6F4FF`,
with preserved aspect ratio, leaf and bite. Variant B and both existing74×74
service badges remain unchanged, as do the other six pairs, seven selected rules
and cd/APS/reset behavior. Apple artwork belongs to Apple Inc.; public source,
extracted SVG hash and crop/recolor are recorded in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Earlier rows are historical
evidence for the previous artwork and do not establish Apple acceptance.

| Apple verification scope | Status |
| --- | --- |
| Full automated gate, source/skill/export and archive verification | PASS:578 tests (577 passed,1 filesystem skip), appearance shell22, restore37, dispatcher PASS; sources27, skills2, export135; archive135 unique regular entries,135 byte comparisons and basename-only checksum verified |
| Selected appearance-only install, seven rules/order/colors and asset bytes | PASS after clean task and whole-branch reviews: dry-run/install exit0 without a new JSON; config hash/order/colors and selection preserved,18 installed assets byte-identical, pending0 |
| Native normal-size Apple and both badges, subdirectories/outside reset and neighboring control | PASS on iTerm2 3.7.6: both iOS service pairs visible in the existing dark theme;10 profile checkpoints cover initial outside, ordinary cd into both roots/subdirectories and reset; neighboring owned outside control unchanged; exact-window screenshots inspected; all3 owned sessions closed, pre-existing sessions preserved |

Standalone `ios` was verified through asset tests and the dark-background
contact sheet at128/24/18px, without adding a personal rule. The other12 asset
files and both service subtrees remain identical to the previous artwork base.
Actual theme switching and fresh Codex/APS/restore execution were not repeated
for this asset-only change; earlier rows retain their historical scope. Existing
notification-policy/hook diagnostics were identical before and after the selected
install and were not changed. Working user tabs were not restarted; a fresh tab
loads the updated runtime. Private paths and screenshots are excluded from export.


## Project launcher — fixture verification, 2026-11-03

Explicit `project-launcher` supports iTerm2 exactly3.7.6, macOS/zsh and selected
Python3.11+ with official iterm2 SDK and manually enabled/authorized Python API.
[Local config/commands](project-launcher.md); [fictional HTML](examples/project-launcher.html).
Native format was manually checked separately on3.7.6; this does not verify the
new CLI installer.

| Scope | Evidence boundary |
| --- | --- |
| Config/builder/CLI | TemporaryDirectory, strict schema, no-source update, stable ids/order, explicit targeting, login shell override, no-write plan/dry-run |
| Ownership/lifecycle | Shared agent consumers, whole-file CAS, late single-bar-field conflict, fresh external/session references, actual engine set/inverse/recovery guards, durable uncertain intent |
| Native adapter | Fake SDK and bounded child using a temporary fake module; typed materialized bar/position and exact replacement proof; hidden references and sessions remain scanned |
| Live new CLI install/update/uninstall, visual panel and click behavior | **Not performed**; fixtures/readback do not establish acceptance |

The remaining inventory-to-write race is not eliminated. No automatic session
close, app launch or SDK install is performed. Missing folders after installation
use native warning/home fallback; narrow windows use Profiles fallback. Real
project names, inventory, configuration, paths and screenshots are not exported.
