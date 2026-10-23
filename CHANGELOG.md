# Changelog

## Unreleased

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
