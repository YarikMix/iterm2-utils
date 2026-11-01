# Resume an exact conversation

Find the requested dialog by relevant history, reading only task-related
transcripts. Confirm the exact UUID and original cwd from its validated header
under effective `CODEX_HOME/sessions`; a filename, title or recent timestamp
alone is insufficient. If multiple dialogs fit, resolve ambiguity before launch.
Use the confirmed existing absolute cwd by default; another cwd requires the
user's instruction. Never substitute the launching agent's current directory.
The CLI independently validates a single matching interactive transcript.

Check known open dialogs read-only. If this dialog is already open, report its
exact window/tab/session rather than creating a duplicate. An explicit request
to open another copy authorizes one creation. Retain the evidence linking source
UUID to the requested history and target tab.

Invoke the skill's one `launch-codex --resume UUID` call. No handoff, new prompt,
ack, `--last`, picker or fork. The process is `codex resume UUID -C ABS_DIR`, with
only existing supported wrappers. Do not send `/status`, shell commands, Enter
or exit commands to verify the restored state.

After CLI `launched`, observe recovered history or dialog identifier **in the
returned target tab** read-only. A matching original transcript proves what was
selected, not what the target restored. Report “диалог восстановлен” only with
that additional target evidence. If unavailable, report exactly:
«команда resume запущена, восстановление истории не подтверждено» and known IDs.
Missing/contradictory identity or history remains unconfirmed. Bound each
additional read to at most 10 seconds; keep observations finite and report
missing access. Do not retry creation or fall back to another transport.

## Structural process examples

These fictional examples document the argv representation; they are not
behavioral tests or live launch evidence. `expected_argv` excludes argv0.

```json
[
  {
    "processTitle": "codex",
    "commandLine": "codex resume 77777777-7777-4777-8777-777777777777 -C /tmp/example-project",
    "expected_argv": ["resume", "77777777-7777-4777-8777-777777777777", "-C", "/tmp/example-project"],
    "matches": true
  },
  {
    "processTitle": "codex",
    "commandLine": "codex",
    "expected_argv": ["resume", "77777777-7777-4777-8777-777777777777", "-C", "/tmp/example-project"],
    "matches": false
  }
]
```
