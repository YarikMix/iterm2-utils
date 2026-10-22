# Maintenance and unresolved setup

Run from the repository with Python 3.11+. Start with `doctor --json`; it is
read-only. `doctor --live --json` additionally probes bounded runtime/MCP reads;
it does not send commands into a terminal. Keep the distinction between
installed files, loaded hooks, Python API authorization and a verified connection.

- Missing Python: obtain Python 3.11+ using the colleague's existing package
  manager, after explaining the dependency. Do not install another agent. For
  MCP, account separately for the server's Python 3.12+ and uvx download.
- Missing dependencies: use the selected feature's `missing_dependency` findings,
  list the packages first, then use the existing manager within the authorized
  setup. Never install all optional packages merely because they are listed.
- `conflict`: preserve foreign or user-edited settings; explain which selected
  feature is blocked. Do not replace an existing skill directory/MCP, broad agent
  config, profile or shell file. Adoption of a recognized legacy integration is
  an explicit choice (`--adopt-legacy`), not a generic overwrite escape hatch.
- `pending_ui`: give the exact menu step from ui.md, then run the CLI reconcile
  for its pending code. Failed verification remains pending.
- `new_session`: explain why hooks/registration need a fresh session. The user
  starts it; do not restart the running agent automatically.

Update the checkout, then preview `python3 -m iterm2_utils update --dry-run --json`
and run `python3 -m iterm2_utils update --json`. Only receipt-owned selected
features are updated. Repeating install/update is idempotent. To add a feature,
use plan/install with explicit choices, retaining the recorded agents and parent;
changing those requires resolving the CLI selection conflict.

Remove only the chosen feature IDs:
`python3 -m iterm2_utils uninstall --features CSV --dry-run --json`, then the same
without `--dry-run`. Shared dependencies remain for retained consumers. Removal
restores only unchanged owned values, never a whole config backup over user edits.
Changed values remain with a conflict for manual resolution. Missing/corrupt
ownership state does not authorize deletion.

Refresh the public skill with `python3 -m iterm2_utils bootstrap-skill --agent
codex|claude|both` after updating the checkout. It uses a separate receipt, copies
only the selected agents' skill files and does not enable terminal features.
User-edited or foreign skill files are preserved as conflicts. Read SKILL.md
directly if the current session has not refreshed skill discovery.

Doctor checks receipt resources and selected dependencies/registrations without
writing. `owned_resource_missing`, `owned_resource_changed`, `selected_hook_missing`
and `registration_changed` require inspection of the named integration; do not
restore whole backups over foreign settings. A missing/old runtime interpreter
needs Python >=3.11 and, for a custom path, the absolute `ITERM2_UTILS_PYTHON`
override on setup commands. Updating then replaces unchanged owned hooks.

`foreign_notifications` requires a separate decision: keep the existing system
alone, or explicitly plan/install `--coexist-notifications`. Explain duplicate
banners and preserve the external hooks. Selective uninstall accepts `--agent`.
Live status checks run only for selected status consumers; MCP checks are
independent. With no receipt, discovery does not require enabling every feature.
