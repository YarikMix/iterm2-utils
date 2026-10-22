# Changelog

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
