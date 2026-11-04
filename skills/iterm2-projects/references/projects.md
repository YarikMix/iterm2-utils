# Project launcher reference

## Candidate and schema

Preflight Python 3.11+, zsh, iTerm2 SDK/API 3.7.6, and importable `iterm2`.
Keep the absolute interpreter path in `ITERM2_UTILS_PYTHON`; do not auto-install
or request permissions. Start from a fresh `resolve_paths()` result and
`state.load(path)`. The source document is normalized as:

```json
{"profiles":["Profile A"],"projects":[{"id":"project-a","name":"Project A","path":"/tmp/project-a"}]}
```

The path above is a fictional example. With no receipt, first install is allowed
only when no manual/foreign panel exists and inventory is complete. A missing
receipt with such a panel, or incomplete inventory, is blocked: do not import or
adopt it. If an owned receipt exists but its source is absent, copy the fresh
installed config as the starting point. Write a new candidate in a temporary
private location with mode `0600`; do not include its contents in output. Keep
`profiles`, ids, ordering, and `parent_profile` unless explicitly changed.
Resolve by exact id, then unique name, then normalized absolute path. Duplicate
ids/names/paths require a question; removing a missing record is a no-op. New
paths must be absolute and exist.

## Commands

Use the selected agents and parent profile from the request/receipt. Replace
`AGENT`, `NAME`, `CSV`, and `CONFIG` with separately quoted argv values.

```sh
"$ITERM2_UTILS_PYTHON" -m iterm2_utils plan --agent AGENT --features project-launcher --parent-profile NAME --project-launcher-config CONFIG --json
"$ITERM2_UTILS_PYTHON" -m iterm2_utils install --agent AGENT --features project-launcher --parent-profile NAME --project-launcher-config CONFIG --dry-run --json
"$ITERM2_UTILS_PYTHON" -m iterm2_utils install --agent AGENT --features project-launcher --parent-profile NAME --project-launcher-config CONFIG --json
"$ITERM2_UTILS_PYTHON" -m iterm2_utils doctor --json
```

For removal, preview and then apply:

```sh
"$ITERM2_UTILS_PYTHON" -m iterm2_utils uninstall --features project-launcher --agent AGENT --dry-run --json
"$ITERM2_UTILS_PYTHON" -m iterm2_utils uninstall --features project-launcher --agent AGENT --json
```

Omit `--agent` only when the receipt's current consumers are intentionally
removed together. `update` has no project config flag. A failed dry-run or
doctor is a blocker; do not silently continue. Native readback/API success is
not visual or click acceptance.

## Transitions and safety

| Situation | Action |
| --- | --- |
| owned copy, add | reread, merge the new entry, preserve ids/order, plan → dry-run → install |
| repeat add | no-op; do not rewrite |
| rename or move | retain id and position; validate the new path |
| remove one | write a candidate containing the other entries |
| remove last | uninstall the feature for current consumers; no empty JSON or folder/session mutation |
| one consumer only | pass `--agent` and explain that the other panel remains |
| source/receipt changed after preview | reread and rebuild before apply |
| no receipt, no panel, complete inventory | allow first install; ask only missing choices |
| no receipt with manual/foreign panel or incomplete inventory | stop; never import/adopt |
| unmanaged or invalid config | stop and report the exact CLI error; no legacy/force |
| preview CAS mismatch | do not run stale argv; preserve concurrent bytes and rebuild |
| timeout or unknown native write | recover the existing CLI journal before planning again; never invent or repeat native writes |
| successful apply | delete temporary candidate |
| unknown first native write | do not retry; keep 0600 candidate and report only its path |

Check the fake runner separately from agent intent: argv must contain the config
only for plan/install, uninstall must be scoped as selected, and no direct file,
folder, GUI, or process-closing effect may be attributed to a model request.
