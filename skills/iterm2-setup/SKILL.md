---
name: iterm2-setup
description: Use when setting up, checking, updating or removing selective iTerm2 integrations for Codex CLI or Claude Code on macOS with zsh, including clipboard, status, notifications, restore, MCP, shell integration and shortcuts.
---

# iTerm2 setup

Use the public repository https://github.com/YarikMix/iterm2-utils. Obtain it in a
new directory if needed, read its README and run commands from that checkout.
This file can be read directly before the current agent refreshes skill discovery.
No private skills, corporate services or workspace framework are required.

1. Choose an available Python **3.11+** interpreter; check its version. If absent,
   report that prerequisite before executing setup. Do not install another agent
   as a workaround. Run `python3 -m iterm2_utils doctor --json` read-only.
2. Ask which **detected agents and features** the colleague wants. Preserve choices
   already explicit in the request. Explain only the relevant choices from
   [features](references/features.md); never infer all features from “setup”.
   Bootstrap copies the skill only; it authorizes none of the seven features.
3. List missing dependencies for the chosen features before installing them with
   an existing package manager. Keep the chosen agents and features; dependencies
   do not justify a second agent, a different feature or installing Peekaboo.
4. Run `python3 -m iterm2_utils plan --agent AGENT --features CSV --json` with only
   the selected values (`AGENT`: `codex`, `claude`, `both`). For shortcuts add
   `--shortcuts CSV`; choose the existing parent with `--parent-profile NAME` if
   needed. Resolve conflicts explicitly; preserve foreign settings and MCP.
5. Run the matching `install` command, then `doctor --json` (and `doctor --live
   --json` for a chosen live connection). Existing selection authorizes necessary
   writes; do not repeatedly ask for the same approval. Installation commits each
   available feature separately: report actual completed, blocked and pending
   results, without adding replacements for failed choices.
6. Follow [UI verification](references/ui.md) for pending steps. Discover Peekaboo
   from the session's actual tool schemas and connection/permission result; a
   detected CLI executable is insufficient. No tool means exact localized manual
   instructions. A UI policy denial stays denied: never try osascript, another
   automation tool or TCC changes to bypass it. System permission and hook trust
   dialogs remain human actions. Do not restart the colleague's session.
7. After “done”, run `reconcile --step CODE --json` for the actual pending code,
   then verify again; the user's confirmation alone cannot mark ready. New hooks
   or MCP may require the colleague to start a new agent session. Keep pending
   findings when verification fails and explain the remaining step.

For maintenance and dependency failures read
[troubleshooting](references/troubleshooting.md). Summarize what actually changed,
what remains pending and which live checks were not performed.
