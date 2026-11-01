# Changelog

## Unreleased

Added explicit Codex-only `appearance`: repository JSON rules choose a session
color and one of seven bundled composite PNGs or an owned copy of a custom PNG.
Applies at interactive shell/Codex start (including resume/fork/restore), not cd;
no match or unavailable target leaves appearance unchanged. Uses the shared
installer/dispatcher and selected Python 3.11+ with the official iterm2 SDK.
Update works without original JSON/PNG; selective uninstall preserves foreign
changes and other runtime consumers. API authorization stays pending until the
explicit-session read-only reconcile succeeds. Offline assets, original SVGs and
MIT attribution are included in runtime/export. Fixture delivery and lifecycle
checks do not establish live APS transitions, icon readability or API permission.

Added `launch-codex` and the separately installed Codex-only `iterm2-launch`
skill: one new tab in an explicit window/profile, preserved login-zsh wrapper,
unique handoff/receipt instructions and bounded observations without automatic
retry. Launch requires source-verified Codex 0.166.0 and compatible existing
clipboard settings; effective config initialization may write normal Codex
state/log databases. Default bootstrap still installs only `iterm2-setup`.
Release fixtures cover launch through the bundled transport without restore
installation and installed restore after source/archive removal. Both skills
are structurally checked; model behavior and live clipboard remain unverified.

Codex status uses the native cc-status backend from a compatible iTerm2 3.7.6+
bundle, including native done and background-task handling. Owned beta.1 status
migrates through update; external legacy remains reused until explicit
`--adopt-legacy`. External complete native hooks are reused without ownership.
Notifications and restore remain independent; notification transition code stays
as a dependency, without writing visible status.

Read-only doctor separates backend, native capability, API connectivity and the
error-event source. Codex 0.163.0 has no StopFailure event, so automatic API-error
display is unsupported; unknown versions remain unverified. Fixture and source
checks do not establish live Codex delivery, renderer behavior or new CI results.

## v0.1.0-beta.1 — 2026-10-23

First public beta for macOS + zsh, Python 3.11+. Explicit selection of clipboard,
status, notifications, Codex restore, read-only MCP, shell integration and hotkeys.
Includes ownership-aware install/update/uninstall, dry-run, UI checkpoints and a
portable setup skill. Runtime and pinned sources are bundled; archive export uses
an explicit file allowlist and includes all source/license notices.

Automated checks use isolated fixtures. Live macOS/iTerm2/agent acceptance and
fresh-model skill behavior remain unverified; see [compatibility](docs/compatibility.md).

Final beta integration corrections: independent per-agent feature/shortcut
receipts and selective removal; owned hook replacement after interpreter changes;
read-only resource/dependency doctor and selected live probes; Python 3.11+ runtime
and complete notification prerequisites; explicit foreign-notification coexistence;
standalone daemon-command classification; materialized evaluation fixtures and
strict provenance metadata. Live/model acceptance remains unverified.
