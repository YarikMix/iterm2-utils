# API launch and exact resume acceptance

Verification date: **2026-11-02**; the live handoff began at 00:19:12 MSK.
Final tested code/skill snapshot: `0ac1a75642010b33b6a3365ecb015ecbf163a5cf`.
Environment: Darwin 25.6.0 arm64, Python **3.13.7**, official `iterm2` SDK
**2.23**, iTerm2 **3.7.6**, Codex **0.166.0**, zsh 5.9. The selected bundle's
short version and build version were both read as 3.7.6. This final update changes
only documentation; no new CI run or production acceptance is claimed.

## Evidence matrix

| Kind | Actual evidence | Status / boundary |
| --- | --- | --- |
| Automated fixtures | Final code suite: 611 tests, OK (skipped=1); release checks below | PASS within isolated fixture boundaries |
| Structural skills | Both skills and public references pass the validator | PASS; does not evaluate agent behavior |
| Offline behavior | [Task 4 results](skill-results.md): 5 final samples, 30/30 proposed decisions/recipes at `29f5073` | Recorded text simulation; later quoted-argv instruction amendment was not behaviorally resampled |
| Independent code review | Whole-branch finding on previous shipped restore fixed in `f978aac`; scoped re-review PASS; quoted-argv fix `0ac1a75` scoped review PASS | Code findings addressed; final evidence-document review is a separate gate |
| Live handoff CLI | Exactly one create with known exact SDK IDs/profile/cwd; CLI returned created_unverified/3 in 32.25s before quoted-argv fix | Original result preserved; no retry or successful fresh final-fix handoff run |
| Later handoff receipt/target | Safe-open ack validation, fields/actual thread/canonical cwd, unique marker in exact pane, then read-only exact inventory/profile GUID/job/parsed argv | Verified later; ack written 244.62s after launch, outside original 120-second receipt window |
| Live exact resume | After clean own-Codex exit, one exact-UUID resume: launched/0 in 6.4s; exact own dialog/cwd and recovered marker/history observed read-only | PASS; no new prompt or verification input to resumed Codex |
| Cleanup | Both own tabs closed by exact IDs after verification; final inventory shows them absent and parent present | PASS; no foreign tab closed, no extra create |
| Clipboard EN/RU | No actual clipboard exercise | Unverified; launch/receipt/history do not establish copy/paste behavior |
| Installed launch skill | Codex-only bootstrap dry-run ready, apply succeeded through CAS; all 3 installed files plus receipt bytes verified | PASS; user settings, profiles and permissions were not edited |

## Live observations and limits

The first handoff invocation used the pre-fix verifier. Its exact target was
created once, but iTerm2's actual commandLine quoted the complete prompt. The
literal-only verifier rejected that legitimate representation and returned
created_unverified/3; that live-discovered defect was subsequently fixed and
reviewed. The known own tab was retained without a second create or fallback.
The later fix accepts only the complete expected argv, either literally joined
or safely shell-tokenized, including the existing wrapper limits; it never
executes observed text.

A Codex folder-trust prompt appeared, then later disappeared. The controller did
not approve the dialog or modify trust; no specific human action is attributed
without an explicit response. Subsequent ack and history establish continuation
after that screen. The ack was safely checked as an ordinary file with matching
fields, actual thread identifier and canonical cwd, and the unique marker was
observed in the exact pane. Read-only inventory/profile GUID/job/parsed argv
then confirmed the same first target. **The 244.62-second receipt is late**: it
does not satisfy the original 120-second window and does not convert the original
CLI result into launched/0. There was no fresh successful handoff rerun on the
final fix; its live timely-receipt path remains unverified.

After these observations, the first own Codex exited cleanly using `/quit` and a
separate Enter. The second one-shot launch resumed that test dialog's exact UUID
in its canonical cwd without a new task. Its launched/0 result and read-only
recovered unique marker/history are separate evidence. Both own successful test
tabs were then closed; private IDs, handoff, ack and screenshots remain outside
this public evidence and release. No user working dialog was used as a fixture.

The selected real bootstrap ran dry-run followed by apply via receipts/CAS.
Installed SKILL.md, both references and receipt bytes matched the checked source.
No dependencies were installed, no permissions changed and no clipboard result
is claimed. The observed trust-screen interruption is not a reason to automate
permission/trust dialogs.

## Automated verification

| Exact command / checkpoint | Actual result |
| --- | --- |
| `python3 -m unittest discover -v` at final `0ac1a75` | 611 tests in 134.552s, OK (skipped=1); 610 passed, zero failures/errors; saved owning-task log inspected, suite not repeated for docs-only finalization |
| `python3 tools/check_skill.py` after final docs | 2 skills structurally valid; not behavioral evaluation |
| `python3 tools/check_export.py` after final docs | 134 allowlisted files; provenance/licenses/private-reference checks passed |
| `git diff --check` after final docs | Exit 0, no output |
| `/bin/zsh tests/test_codex_shell.zsh` at earlier `29f5073` checkpoint | Exit 0, dispatcher tests passed; no count emitted |
| `/bin/zsh tests/test_appearance_shell.zsh` at that checkpoint | 22 tests in 15.070s, OK |
| `/bin/zsh tests/restore/test_codex.zsh` at that checkpoint | 37 tests in 26.501s, OK; pass=37 fail=0 |
| `python3 tools/check_sources.py` at that checkpoint | 27 pinned sources verified |

Development checks use isolated fixture homes, fake runners/SDK adapters and
synthetic executable boundaries. They include extracted-release CLI/bootstrap,
receipt/CAS, exact mode argv, quoted observations and previous shipped restore
compatibility. These fixtures are distinct from the controller's real acceptance.
Baseline: **577 tests, OK, skipped=1**; final **611**, net **+34**. The sole skip
is `test_distinct_case_sensitive_directories_remain_distinct`, because the fixture
filesystem is case-insensitive. The earlier 607-test checkpoint remains historical.

The recorded behavioral score and frozen skill fingerprints refer to the sampled
`29f5073` instruction. Only its quoted-argv contract paragraph changed afterward;
see [the later amendment and current fingerprint](skill-results.md#later-instruction-amendment-and-evaluation-boundary).
Code regressions and structural checks cover that amendment; no fresh 30/30 model
behavior claim is made. A prior documentation-only cleanup removed a real dialog
UUID from the current specification without changing requirements.

## Release artifact

`python3 tools/build_release.py --destination /private/tmp/iterm2-launch-api-resume-release`
completed with exit 0 after the exported README/compatibility updates. Archive:
`iterm2-utils-v0.1.0-beta.1.tar.gz` (**439079 bytes**).

SHA-256: `19d5c6246a608ed8e802292b43c20be5895b9f840a0bd372c798a26fb9e4b406`.
The adjacent `.sha256` contains that digest and only the archive basename. An
assert-based check confirmed **134 entries**, **134 unique regular files**,
exact export-allowlist equality and **134 source byte comparisons**. This replaces
the earlier hermetic-checkpoint archive; only non-exported acceptance/report
text was finalized after building. Code/skill bytes were preserved after the
final 611-test run and installed-skill verification. The archive is not published;
private live artifacts are excluded.
