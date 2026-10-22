# Repository guidance

This public package supports macOS + zsh and Python 3.11+ (stdlib, unittest).
Read README.md and skills/iterm2-setup/SKILL.md for the end-user setup workflow.
No private framework, author workspace or corporate service is required.

## Development and tests

Use TemporaryDirectory HOME/Paths and fake Runner/adapters for all tests. Never
read or change the developer's real agent/iTerm2 settings, auth, .env files or
old source checkouts. Do not launch GUI or change permissions during development.
Run `python3 -m unittest discover -v` and `python3 tools/check_skill.py`.
Fixture tests and structural checks do not establish live acceptance or agent
behavior; document the actual verification matrix and unresolved UI checks.

## Product invariants

End users explicitly authorize changes to their actual selected settings through
the CLI. Ask for detected agents/features unless already chosen; bootstrap selects
no features. Pure builders return ChangeSet, never write or launch GUI. Use the
transaction engine, receipts and CAS for owned values; preserve foreign changes.
Keep stdout diagnostics bounded and free of settings bodies/secrets. Codex copy
and restore are Codex-only; never assign &codex matching to Claude. MCP remains
optional and pinned. Hooks require an explicit tab UUID, no active-tab fallback.
UI denials are not bypassed. Human permission/trust dialogs remain human actions.
