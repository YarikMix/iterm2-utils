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

For native Codex status, inspect `status_backend` (cc-status, external native or
legacy reused) and `native_status_capability` separately. Missing/non-executable
cc-status or sibling it2, an old bundle or missing required flags needs a
compatible iTerm2 3.7.6+ bundle. Never execute cc-status as a live diagnostic
probe or copy app utilities into the package. A partial/duplicate/wrapped native
set or competing legacy writer needs explicit conflict resolution.

`status_migration_required`: run `python3 -m iterm2_utils update --dry-run --json`,
resolve the owned Codex status conflicts and complete update first. Another
consumer cannot switch the shared runtime while the owned status migration is
blocked. Preserve independently selected notifications/restore and foreign edits.

`codex_error_event: limited` is nonblocking. For 0.163.0 the verified schema lacks
StopFailure; for another/unknown version the error source is unverified. Do not
add guessed events or infer session failure from a failed tool or message text.
Ready files, child exit0 or `status_api: ready` do not establish hook delivery or
automatic API-error display.

`doctor --live` reads only get-status for a strict explicit UUID. TERM_SESSION_ID
alone is accepted; if ITERM_SESSION_ID is also present both must be valid and
agree. A malformed/conflicting source or nonempty TMUX leaves the probe pending,
without guessing the active tab. Use an ordinary local iTerm2 panel; tmux,
control mode and SSH need separate acceptance. Details/payload are not printed.
The accepted API states are empty, idle, working, waiting, done and error.


Appearance: `missing_dependency` can mean the selected runtime Python cannot
import `iterm2`, even if another interpreter can. Choose an existing Python 3.11+
with that SDK using absolute `ITERM2_UTILS_PYTHON` on setup/maintenance commands.
`appearance_config_required` needs a local rules JSON on the first plan/install;
`--appearance-config` is accepted only there with selected appearance. Later
install/update use installed rules and copied PNGs. Resolve invalid JSON/color,
unknown builtin, missing/corrupt PNG and edited owned files before retrying;
never overwrite the user's edits. New explicit JSON replaces the owned rules,
not arbitrary foreign config fields.

`appearance_api` pending is separate from SDK import and ready files. Offline
doctor cannot clear it; live doctor is read-only. Enable/authorize Python API as
in ui.md, then `reconcile --step appearance_api --json` in an ordinary iTerm2
session with valid matching UUID sources. No active-tab fallback, tmux bypass or
API/TCC automation workaround. A successful probe proves access only. If a
repository is unavailable, leave it unavailable; do not create a substitute root.
Visual APS/readability acceptance stays pending until actually checked.

Appearance follows ordinary cd in a fresh interactive iTerm2 zsh after install
or update: registered roots and subdirectories apply their pair; outside disables
base/light/dark Tab Color and hides the custom icon without a default RGB. A
missing external target does not match and must not be created. The once-only
native chpwd hook preserves foreign hooks; subprocesses, noninteractive shells
and tmux do not update the tab. Startup and each cd wait for the bounded helper
assignment/reset and cleanup, so a pending parent write cannot overwrite a fresh
interactive child's target. Usually brief, this can delay startup/each cd roughly
2.8 seconds with unavailable API/filesystem; API errors and deadlines still leave
a successful cd at exit 0. Launch readiness and asynchronous return observation
remain unchanged. Do not repeatedly
source startup or restart user sessions to clear a live-verification finding;
use an owned temporary tab for the checks in ui.md.

For appearance maintenance use `update --dry-run --json`, then `update --json`.
Selective removal: `uninstall --agent codex --features appearance --dry-run --json`,
then omit `--dry-run`. Existing tabs can retain their color/icon until closed;
shared runtime remains for other selected features. Do not reset open tabs or
remove unowned resources to make diagnostics look clean. Generated startup omits
appearance source after removal; already running shells are not changed remotely.

Appearance also requires the calling shell's terminal device to match the `tty`
of the explicit iTerm2 session. An inherited UUID, another PTY or a successful
read-only probe is insufficient. Missing/mismatched terminal, conflicting IDs,
closed session or API errors safely skip all color/icon and snapshot writes,
including delayed cleanup; there is no active-tab fallback. Device aliases are
compared by identity, and supervisor pipes remain supported. Nested interactive
shells on the same terminal continue to work.

Update delivers appearance.zsh and appearance.py together. Already running
shells keep their loaded hook and may still reference the old immutable runtime
without this protection. Old callers safely skip only when invoking the new
Python helper without tty. Open a fresh shell to activate the new hook; update
does not retrofit running shells. Do not restart user tabs remotely.
Launcher preflight additionally removes both parent terminal IDs only from its
private login-shell environment; parent state is preserved and newly created
tabs obtain their own binding. Commands, JSON rules and selection are unchanged.
