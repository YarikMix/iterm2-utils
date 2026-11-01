---
name: iterm2-launch
description: Use when a user requests a separate new Codex session in an iTerm2 tab on macOS with zsh, including handing work to a new terminal agent. Not for internal subagents or Claude Code.
---

# Launch a separate Codex

Create one new session; verify its identity and receipt of the task separately.
An internal-subagent or Claude Code request does not authorize a Codex tab.

1. Warn that a new iTerm2 tab will appear. Use a verified current checkout or
   unpacked release of https://github.com/YarikMix/iterm2-utils; read its README
   and run from that directory with Python **3.11+**. Check
   `python3 -m iterm2_utils launch-codex --help` before proceeding.
2. Obtain the **parent session ID** from explicit runtime metadata (for example,
   only the session UUID portion of `ITERM_SESSION_ID`). Using the selected
   iTerm2 bundle's verified `it2`, read `session list --json`, `tab list --json`
   and `window list --json`. Match the parent uniquely to its tab/window;
   record those IDs. Never choose the active/frontmost window. If the source is
   unavailable or ambiguous, ask for an explicit session/window before launch;
   preserve a window explicitly selected by the user.
3. Inspect `it2 profile list --json` and `it2 profile show NAME --json` for the
   selected profile; record its unique name/GUID. Name alone does not prove Cmd+C /
   Ctrl+C EN/RU bindings. The launch CLI also checks materialized bindings,
   CopySelection and effective Codex/login-shell compatibility. Preserve foreign
   profiles; unresolved compatibility blocks launch. Use `iterm2-setup` for
   prerequisites with the user's selected features; never silently install them.
4. Prepare the private, unique [handoff and receipt](references/handoff.md).
   Record the absolute cwd, handoff path, request UUID and launch timestamp;
   `ack.json` must not exist. Include only task-scoped context and restrictions.
5. Invoke exactly once, passing each value as one argument through an argv API
   or correct shell quoting:

   ```sh
   python3 -m iterm2_utils launch-codex --window WINDOW_ID --profile PROFILE_NAME --cwd ABS_DIR --handoff ABS_FILE --json
   ```

   The CLI preserves the normal shell function/settings/model/endpoint and sets
   process-local `CODEX_RESTORE_NO_AUTO=1`. Add no Codex flags, `--no-alt-screen`,
   resume, overrides or disabled protections. Never bypass denied automation.
6. Inspect JSON and exit code, then verify returned window/tab/session against
   read-only inventory, scoped to those exact IDs. A known tab must have exactly
   one session in the requested window. Recheck `profile show` name/GUID;
   confirm the profile/Codex via `session get-var session.profileName --session SESSION_ID` and
   `session get-var session.jobName --session SESSION_ID` (JSON-encoded strings).
   Job name alone is insufficient: `codex --version`/`--help` are helpers. For
   launch evidence also read `session.processTitle` and `session.commandLine`
   with the same scoped `get-var`. Require commandLine to equal processTitle,
   zero to two `--no-daemon` flags from supported wrappers, `-C`, the exact cwd,
   and `Read the handoff file at ABS_FILE and carry out the task described there.`
   joined by spaces without shell quoting (iTerm's representation). Do not echo
   the raw command line. Missing/malformed/mismatching evidence is unverified;
   do not upgrade status based on job name or elapsed time.
   For unknown identity, inspect known IDs/inventory; never guess by recency.
   Apply the receipt checks and bounded wait in the reference.

| CLI result | Report / next action |
|---|---|
| `launched` / 0 | Launch verified; receipt still required. |
| `created_unverified` / 3 | Retain known IDs; inspect that target. |
| `unknown` / 3 | Creation uncertain; report unresolved identity. |
| `blocked` / 2 | Explain the specific prerequisite from findings. |

Report actual launch and receipt status, IDs and artifact paths. Receipt is not
design approval, task completion or clipboard acceptance. Never resend the
prompt, create again automatically, close the tab or kill user processes after
failure. Keep artifacts for diagnosis.
