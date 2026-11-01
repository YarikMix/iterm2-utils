---
name: iterm2-launch
description: Use when a user requests a separate Codex session or an exact existing Codex conversation in an iTerm2 tab on macOS with zsh. Not for internal subagents or Claude Code.
---

# Launch or resume Codex

Create at most one tab. Verify launch separately from task receipt or restored
history. An internal-subagent or Claude Code request does not authorize a Codex tab.

1. Use a verified checkout or unpacked release of
   https://github.com/YarikMix/iterm2-utils; read README and run
   `python3 -m iterm2_utils launch-codex --help` there. Python **3.11+** must have
   the official `iterm2` SDK importable in that same interpreter; the iTerm2 API
   must be accessible. Live-tested SDK version: **pending**. Missing SDK/API or
   denied access blocks launch; no automatic installation or environment search.
2. Map the explicit parent session UUID from runtime metadata (e.g. UUID portion
   of `ITERM_SESSION_ID`) using the selected bundle's verified `it2`
   `session list --json`, `tab list --json`, `window list --json`. Record its
   unique tab/window IDs. Preserve an explicitly selected window; never choose
   active/frontmost or guess by recency. Ambiguous/missing identity requires an
   explicit target before launch.
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
5. Warn that a new tab will appear. Invoke **once**, with values passed as
   individual argv elements or correctly shell-quoted:

   ```sh
   python3 -m iterm2_utils launch-codex --window WINDOW_ID --profile PROFILE_NAME --cwd ABS_DIR --handoff ABS_FILE --json
   python3 -m iterm2_utils launch-codex --window WINDOW_ID --profile PROFILE_NAME --cwd ABS_DIR --resume SESSION_UUID --json
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
