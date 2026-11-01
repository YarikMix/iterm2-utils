# Handoff and acknowledgement

## Prepare before launch

Generate one UUID with the platform UUID library per launch. Use a securely
created private local directory (for example `tempfile.mkdtemp`, mode 0700),
containing `handoff.md` (mode 0600) and an initially **absent** `ack.json`.
Resolve cwd and both paths to absolute paths; retain the directory after use.
Do not reuse paths or delete an old receipt to make it appear fresh.

The handoff has these explicit fields/sections:

- `request_id`: the generated UUID; `ack_path`: the absolute adjacent ack path.
- `cwd`: the existing absolute working directory used in `--cwd`.
- Original task and expected first step; state whether the step is a suggestion.
- Relevant constraints, scope/ownership, available authorization and prohibitions.
- Material paths and useful context, limited to this task; no unrelated secrets.
- Receipt instructions below, including the schema and the actual request/cwd.

Passing a handoff does not approve a design, broaden authorization or waive the
new session's applicable workflow. Preserve unresolved questions as questions.
Write task text as data, never interpolate it into shell code.

## Instructions for the receiving Codex

Read the handoff and its relevant materials. Before acting on the task, write a
new UTF-8 JSON object to the exact `ack_path`, using these five required fields:

```json
{
  "request_id": "UUID copied from this handoff",
  "thread_id": "actual identifier of this Codex conversation",
  "cwd": "absolute working directory from this handoff",
  "accepted_task": "concise description of the task actually read",
  "first_step": "concrete next action within the applicable workflow"
}
```

All values must be nonempty strings, with no whitespace-only values. Verify the
actual working directory equals the handoff's canonical cwd before acknowledging;
do not merely echo that field. Use the actual conversation ID from runtime
metadata; do not invent one. If identity,
cwd or writing the receipt is unavailable, explain that limitation rather than
fabricating acknowledgement. The task may require clarification before work;
`first_step` may say so. The receipt acknowledges reading, not agreement with a
design or completion. Write a temporary ordinary file in the same private
directory with mode 0600, then atomically rename it to `ack.json`; do not create
a symlink. The CLI neither creates nor validates this receipt.

## Sender's receipt check

Record wall-clock nanoseconds immediately before the one CLI invocation for
freshness checks. After it returns, start a monotonic deadline of **120 seconds**
for read-only target/receipt observation. Every external read has a timeout
within the remaining budget and at most **10 seconds**; polling intervals are
also at most 10 seconds. Send a progress message by 60 seconds if still waiting.

First establish the returned target's unique window/tab/session identity and
selected profile/Codex as described in the skill. If identity cannot be
established, report uncertainty; an ack alone cannot select an unknown tab.
Do not create again or send the prompt again to resolve uncertainty.

For the exact expected ack path, use `lstat` to reject a symlink or non-regular
file. Open without following symlinks and check the opened file's identity/type
with `fstat`; reject a replacement during reading. Bound the read (64 KiB is
sufficient for a receipt), decode UTF-8 and parse JSON as an object. Require:

- A fresh file modification timestamp at or after the recorded launch time,
  and not in the future at observation time.
- All five required fields above are strings with nonempty `.strip()` values.
- `request_id` exactly equals this launch's UUID; `cwd` exactly equals the
  canonical absolute cwd written in the handoff and passed to the CLI.
- `thread_id` identifies the receiving conversation; accepted task/first step
  describe this handoff rather than another task.

Missing, partial, stale or mismatched files remain unconfirmed; bounded read-only
polling may continue for an atomic write. Do not infer receipt from startup
text, process presence or an old valid receipt. At the deadline report observed
launch status and “task receipt unconfirmed”, the known IDs and retained paths.
If a valid receipt is observed for the verified target, report “task received”
separately from the launch status. Never expose the full handoff or terminal
screen in diagnostics, and never clean up user sessions on an error.
