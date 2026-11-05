---
name: iterm2-launch
description: Use when a user requests a separate Codex session or an exact existing Codex conversation in an iTerm2 tab on macOS with zsh. Not for internal subagents or Claude Code.
---

# Launch or resume Codex

Create at most one tab. Verify launch separately from task receipt or restored
history. An internal-subagent or Claude Code request does not authorize a Codex tab.

**Codex sandbox:** When this skill runs inside Codex, pass
`sandbox_permissions: "require_escalated"` on the tool call before the first
iTerm2 socket/API operation. Apply it to the selected `it2` session/tab/window/
profile inventory, scoped observations such as `session get-var` and profile
reads, and the single `launch-codex` mutation. Do not probe from the default
sandbox first. This is tool-call metadata, not a CLI flag. Keep the approval
prefix narrow: use only the selected bundled `it2` executable or the exact
saved Python executable for `iterm2_utils`; do not request broad filesystem
access. If the host cannot provide escalation, report launch as blocked and do
not retry or create another tab automatically. Other hosts use their native
permission mechanism.

1. Use a verified checkout or unpacked release of
   https://github.com/YarikMix/iterm2-utils; read README there. Select available
   `python3` or the user's explicitly chosen Python and save its absolute
   `sys.executable`. Preserve that path, including virtualenv symlinks; do not
   resolve it to a base interpreter or keep a PATH shim instead. For `python3`:

   ```sh
   launch_python="$(python3 -c 'import os, sys; p = sys.executable; assert os.path.isabs(p); print(p)')" &&
   "$launch_python" -c 'import sys; assert sys.version_info >= (3, 11); import iterm2; print(sys.executable)' &&
   "$launch_python" -m iterm2_utils launch-codex --help
   ```

   Require successful version/import/help checks before continuing; bound each
   external operation to 10 seconds using the calling tool. Use this exact path
   for checks and launch. Separate tool calls must pass the saved path explicitly
   again; shell variables do not persist. If cwd/PATH changes, recheck import/help
   with the saved Python in the invocation context, without selecting another.
   Python **3.11+** and accessible iTerm2 API are required. Live-tested SDK: **2.23**.
   Missing SDK/API or denied access blocks launch; report the selected Python and
   missing prerequisite. No automatic installation or environment search. An
   explicitly authorized installation is separate; recheck afterward.
2. Select the window from successful, complete, valid inventories using the
   selected bundle's verified `it2`: `session list --json`, `tab list --json`,
   `window list --json`, in this priority order:
   - Preserve the user's explicit target; verify its unique window ID. If missing
     or ambiguous, ask for a target instead of substituting another window.
   - Otherwise map the parent UUID from runtime metadata (e.g. UUID portion of
     `ITERM_SESSION_ID`) to consistent unique session/tab/window IDs.
   - If the runtime ID is absent or not found, and the complete window inventory
     contains exactly one window with a nonempty ID, use it **without asking**.
     Record that selection basis; do not invent a parent mapping.
   - Multiple windows without a mapped parent, or contradictory parent mappings,
     require an explicit target. Zero windows or failed/invalid inventories block
     selection. Never infer uniqueness from a screenshot, focus, title or recency.
3. Read `it2 profile list --json` and `profile show NAME --json`; record unique
   name/GUID. CLI also checks materialized Cmd+C/Ctrl+C EN/RU, CopySelection and
   effective Codex/login-shell compatibility. Preserve foreign profiles. For
   prerequisites use `iterm2-setup` with explicitly selected features.
4. Choose the requested mode:
   - **New task:** prepare private unique [handoff/ack](references/handoff.md),
     canonical cwd, absent ack and launch timestamp.
   - **Existing conversation:** follow [resume](references/resume.md) to match
     relevant history, exact UUID and confirmed transcript cwd. If already open,
     report its tab; create a duplicate only on explicit request. No new prompt
     or ack is part of resume.
5. Recheck the selected window ID before invoking CLI. If selected only because
   it was the sole window, the complete inventory must still contain exactly that
   window. A second window requires clarification; a vanished target blocks this
   attempt without automatic substitution. Rechecking is not an atomic guarantee
   against concurrent changes; CLI also validates the exact target before create.
   Warn that a new tab will appear. Invoke **once**, with values passed as
   individual argv elements or correctly shell-quoted:

   ```sh
   "$launch_python" -m iterm2_utils launch-codex --window WINDOW_ID --profile PROFILE_NAME --cwd ABS_DIR --handoff ABS_FILE --json
   "$launch_python" -m iterm2_utils launch-codex --window WINDOW_ID --profile PROFILE_NAME --cwd ABS_DIR --resume SESSION_UUID --json
   ```

   Choose exactly one line. The SDK supplies custom command **at tab creation**;
   no terminal send/run/send_text or `it2 tab new --command` fallback. Preserve
   shell function/settings/model/endpoint and protections; add no Codex flags
   or `--no-alt-screen`. CLI sets `CODEX_RESTORE_NO_AUTO=1` before login shell.
6. Inspect exit/JSON; observe only returned IDs read-only. Require one session in
   the exact tab/window, matching profile name/GUID and `session.profileName`,
   `session.jobName=codex`, `session.processTitle` and `session.commandLine`
   through scoped `session get-var ... --session SESSION_ID` (JSON strings).
   `processTitle` is argv0; `commandLine` is that title **plus** zero to two
   supported wrapper `--no-daemon` flags before exact mode argv: `-C cwd prompt`
   or `resume UUID -C cwd`. Accept either the exact space-joined representation
   or safely shell-tokenized quoted text matching that complete argv; never
   evaluate the text. Malformed quoted text or extra arguments remain unverified.
   Bare `codex`, help/version, wrong cwd/UUID/handoff or missing evidence is
   unverified. Do not expose raw command lines or screens.
7. Report launch and the mode's separate evidence: fresh validated handoff ack,
   or read-only recovered history/identifier in the exact resume target. Without
   resume history: **«команда resume запущена, восстановление истории не подтверждено»**.
   Use bounded observations: preflight/connect ≤10 seconds each; creation and
   launch verification share 30 seconds; handoff ack has its own 120-second wait.

| JSON status / exit | Meaning |
|---|---|
| `launched` / 0 | Command verified; ack/history remains separate. |
| `created_unverified` / 3 | Retain known IDs; inspect that target only. |
| `unknown` / 3 | Creation uncertain; retain uncertainty and any IDs. |
| `blocked` / 2 | Prerequisite failed before creation. |

JSON `mode=launch_codex` includes `launch_mode=handoff|resume` and
`resume_session_id` (dialog UUID or null). `session_id` is the iTerm2 terminal ID.
Report actual statuses, IDs and artifact paths. Never automatically retry,
resend a prompt, close a tab or kill processes after uncertainty. If a shell
command is visible in Codex's input field, leave it unsent: bare Codex is not a
successful launch. Use this procedure for an authorized replacement; retain the
old tab and diagnostic artifacts. Receipt/history is not task completion,
design approval or clipboard acceptance.

The effective-config preflight still uses the selected cwd and login shell, but
its private environment omits both inherited `ITERM_SESSION_ID` and
`TERM_SESSION_ID`. Parent environment, appearance and saved snapshot stay intact
before creation; the new tab gets its own iTerm2 binding and normal shell startup.
Appearance separately requires the shell tty device to match the explicit
session's tty before any profile/snapshot write. Missing/mismatched tty safely
skips; read-only API access alone does not authorize mutation. After updating
runtime, use a fresh shell to load the new hook. Existing shells may still call
an older immutable runtime without this protection. An old caller invoking the
new Python helper without tty safely skips; update does not retrofit running
shells. Do not restart existing user sessions.
