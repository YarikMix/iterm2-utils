# Launch skill verification

## Before authoring

Held-out inputs: `skill-cases.md`, six cases plus stated variations, prepared
before the public skill. Required writing-skills, discovery, testing, TDD and
bulletproofing references were read. No skill test subject was spawned.

Behavioral baseline RED: **BLOCKED**, not run. No authorized isolated inference
endpoint/auth is available in this task. Existing corporate API permission is
limited to code review and does not authorize behavioral evaluation. No real
auth/settings were read to find an alternative. No command, trace, rationalization
or behavioral failure exists to report; none is fabricated.

The agreed plan explicitly permits this limitation. Implementation can proceed
as a reviewable, behaviorally unverified skill. Structural and prose checks will
be reported separately from agent behavior. GREEN must use the same held-out
cases in fresh isolated processes after authorization, not this session's cache.

## Implemented variant and checks

Behavioral GREEN: **BLOCKED**, not run for the same authorization reason. There
are no model invocations, loaded-body traces or actual agent calls to inspect.
All C1–C6 and their variations are BLOCKED for both baseline and skill variants;
none is PASS or a demonstrated RED failure. No baseline rationalizations were
observed, so no empirical rationalization table or wording effectiveness claim
is supplied. No behavioral runner was invented to bypass the missing permission.

Final SHA-256, obtained with the exact command:

```sh
shasum -a 256 skills/iterm2-launch/SKILL.md skills/iterm2-launch/references/handoff.md docs/superpowers/validation/2026-11-01-codex-launch/skill-cases.md
```

```text
0035b4e2691dbdbcab6c9bd16b31dd64631c1458b8907c79e9b3a7592892511c  skills/iterm2-launch/SKILL.md
00bb558c11bd34b475ef3ac398c0a47b0ee5d0e0c60834ab3d53ebf1ab3270cd  skills/iterm2-launch/references/handoff.md
2a84a92aea5467cd87316993b3e56a7d1099bc8af7569532f6b1e785f39b13bb  docs/superpowers/validation/2026-11-01-codex-launch/skill-cases.md
```

Commands run from the task worktree:

| Exact command | Result / scope |
|---|---|
| `python3 tools/check_skill.py skills/iterm2-launch` | Exit 0: `Skill structure valid (not a behavioral evaluation).` Final files checked; portable paths, frontmatter, links, no symlinks. Structural PASS only. |
| `git diff --check` | Exit 0, no output. Whitespace check only. |

The exact separation command used was:

```sh
rg -n 'A17E0B41|win-amber|win-teal|Cedar|Проект лён|launch-study' skills/iterm2-launch
```

No runtime/fixture code changed, so launch tests were not repeated; Task3's
33 PASS evidence remains separate. The controller assigned the complete suite
and default both-skills validator change to Task6. No real HOME/settings, GUI,
auth or model calls were made. Live receipt and clipboard acceptance remain
unverified. Installation/publication is outside this task.

## Content self-review (not a behavioral evaluation)

Compared with the approved spec independently from the plan: explicit parent ID
and session/tab/window mapping; no active-window default; record profile name
and GUID; current checkout/release and exact CLI; one unique private UUID/cwd
handoff; fresh ordinary non-symlink ack; all five nonempty fields; actual receiver
cwd and thread identity; exact request/cwd equality; bounded reads/waits and
progress; preserve IDs/artifacts and no retry; no Codex overrides/permission
bypass; blocked prerequisites use setup; other agent types excluded. Receipt,
launch and clipboard evidence are distinguished. Self-review clarified actual
receiver cwd checking and profile GUID rechecking before final structural PASS.

## Final-review fix: observation instructions

The Task4 hashes above remain historical evidence. The final I1 fix extends
step 6: require the expected processTitle/commandLine, not jobName alone, and
never treat helper commands or elapsed time as launch success. Current hashes:

```text
803ecd6d3bb0c41aaa13353d05fee27e277de38dcb04de52bc908414b27d699e  skills/iterm2-launch/SKILL.md
00bb558c11bd34b475ef3ac398c0a47b0ee5d0e0c60834ab3d53ebf1ab3270cd  skills/iterm2-launch/references/handoff.md
```

`python3 tools/check_skill.py`: exit 0,
`2 skills structurally valid (not a behavioral evaluation).`
Archive bootstrap exercised both bundles in the scoped 57-test GREEN run;
this verifies distribution bytes, not model behavior. Behavioral evaluation
remains **BLOCKED**, live acknowledgment/clipboard remains **unverified**.
The controller owns the subsequent supported bootstrap refresh of the installed
bundle and its receipt/hash verification; this source report does not claim it.
