---
name: iterm2-projects
description: Use when adding, removing, renaming, moving, or listing iTerm2 project-launcher button projects, including choosing Codex/Claude consumers and a parent profile.
---

# Project launcher projects

Use the repository's CLI and its normalized project-launcher config. Keep names,
paths, ids, profiles, and receipt details private; public examples use only
Project A and Project B.

## Read first

Preflight an available Python 3.11+ interpreter, zsh, iTerm2 SDK/API 3.7.6,
and an importable `iterm2`; preserve its absolute `sys.executable` in
`ITERM2_UTILS_PYTHON`. Do not install packages, request permissions, or search
real settings automatically. Call `resolve_paths()` and read state with
`state.load(path)`. If a receipt exists, use
`selection.agents_for("project-launcher")` and `selection.parent_profile` as
ownership and consumers. If no receipt exists, allow first install only when
there is no manual/foreign panel and the inventory is complete; otherwise stop
without import/adoption. An absent source with an owned install starts from the
fresh installed 0600 copy. Read the normalized config
`{profiles, projects:[{id,name,path}]}` without changing it.
Detailed transitions and a fake-runner checklist are in
[projects reference](references/projects.md).

## Choose the transition

- Listing is read-only: show project names and paths only; do not recover or
  print the receipt.
- For add, repeat is a no-op. A rename or path change keeps the existing `id`
  and list position. Resolve an entry by exact id, then unique name, then
  normalized absolute path; duplicate ids/names/paths require a question.
  Missing-record removal is a no-op. A new path must be absolute and exist;
  report a missing old path.
- Removing one entry keeps the remaining entries. Removing the last entry
  uninstalls `project-launcher` for the receipt's consumers; never publish an
  empty config, delete a folder, or close a session. `--agent` limits uninstall
  to that consumer and leaves the other consumer's panel intact.
- On first install ask only for values not already supplied: consumers,
  parent profile, and project data. Do not select unrelated features.

Prepare a new candidate outside the checkout with mode `0600`; preserve unknown
fields and existing entries. Never edit an installed file directly. Save bytes
or fingerprints of the receipt and installed config used for preview. Immediately
before apply, reread both and compare those fingerprints; if either changed,
discard the stale command, preserve the concurrent edit, and rebuild. On
success, delete the temporary candidate. Keep it only for an unknown first
native write or an interrupted/failed recovery.

## Apply

Use the exact CLI sequence from the reference: plan and install both receive
`--project-launcher-config`; install has a dry-run before the real install; then
run `doctor --json`. `update` has no config flag. Quote every path as one argv
element and keep execution foreground. If the CLI reports a validation or
ownership error, stop, preserve the candidate, and report the exact CLI error.
For a timeout or unknown native write, recover the existing CLI journal before
planning again; never repeat an unknown native write. Do not invent a journal or
use direct
SDK calls, legacy adoption, null/force overrides, GUI automation, or session
termination. Native readback/API success does not prove visual button state or
click acceptance; report that separately.
