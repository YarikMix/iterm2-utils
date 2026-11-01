# Codex launch execution record

Implementation and authorized local delivery are complete at `4c7d705` on
`feat/codex-launch`. All seven task reviews passed. The one whole-branch review
found I1 (helper process mistaken for launch) and M1 (overstated restore recheck);
one fix wave and its scoped re-review closed both with no remaining findings.
The branch/worktree are retained. No merge, push or published release occurred.

## Verification

- Before the final fix: full Python suite 467 PASS; dispatcher zsh PASS;
  restore shell 37 PASS / 0 FAIL; 27 sources; 2 structural skill checks;
  109 export files; release build and whitespace checks PASS.
- After the final fix: 57 affected launch/checks/CLI/export tests PASS; an
  additional synchronized fake-process test covered 20 phases of 8 wrapper
  chains. Skill structure, export and whitespace checks PASS. The full suite
  was not repeated; its earlier result is historical, not a new run.
- Final archive rebuilt from `4c7d705` successfully. Archive tests exercise
  bundled transport and standalone restore after removing source/archive.
- Updated skill installed using supported bootstrap; both file hashes and
  receipt payload/ownership verified. Existing personal memory routing updated;
  private content is excluded from this repository and release.
- Current skill SHA-256: `803ecd6d3bb0c41aaa13353d05fee27e277de38dcb04de52bc908414b27d699e`.
- Handoff reference SHA-256: `00bb558c11bd34b475ef3ac398c0a47b0ee5d0e0c60834ab3d53ebf1ab3270cd`.

Behavioral RED/GREEN remains BLOCKED without authorized isolated inference.
Live Codex launch, fresh handoff acknowledgement, clipboard EN/RU and neighboring
session preservation remain unverified without an isolated Mac environment.
Current-session skill discovery was not verified; a fresh session may be needed.
The existing setup skill was absent in the personal destination and was not
installed; coexistence is proven by isolated tests only.

## Decisions and tradeoffs

The following is the complete ordered set of controller rulings from execution.
They preserve why the implementation differs from the initial plan and the cost
if a decision proves wrong.

- Use the already isolated worktree; no second worktree — branch exists and is clean — cost if wrong: isolation checks must be revisited.

- Full suite once at baseline and once after all code tasks; per-task focused tests only unless failures justify broader checks — developer test policy and approved Task 6 — cost if wrong: integration defect caught at final gate.

- Task 6 records suite/package evidence; controller performs the one final whole-branch review after repository tasks and delivery task review — avoids duplicate review seats while preserving skill gate — cost if wrong: final correction can require refreshed installation.

- No publication/push or unauthorized live GUI tests; installation and named personal memory update are authorized by accepted design — separate delivery from live acceptance — cost if wrong: delivery permissions may require escalation.

- Task 2 uses canonical app-server config/read in the intended login-shell environment. Ordinary Codex runtime initialization (including its existing damaged-SQLite backup/rebuild path) is permitted as part of the authorized launch, not a settings mutation; document it, never invoke on developer real state during development. No temporary config overrides or duplicate config resolver. Reason: source-backed resolver is bounded and preserves actual loader semantics; cost if wrong: preflight may touch ordinary Codex state before tab creation.

- Support direct binary, source-verified packaged wrappers and simple no-daemon-only wrapper; unknown config-changing shell chain returns launch_config_unverified. Do not statically analyze arbitrary shell. AppServer branch does not propagate interactive --profile, so do not pretend it does. Cost: unsupported custom wrappers require explicit later support.

- Match live iTerm GUID/name against unique materialized New Bookmarks raw profile, then compare four copy bindings. Unknown/incomplete/ambiguous raw state blocks. Do not introduce a new Python iTerm dependency or inheritance resolver. Cost: some custom profile setups may remain unverified.

- Task2 adds narrow Runner.codex_config bounded stdio JSON-RPC transport and returns tuple[LaunchInspection|None, findings] instead of tuple[Path|None, findings]. Frozen inspection carries verified it2/zsh/profile GUID and minimal same-shell identity for Task3. Reason: canonical config/read requires initialize handshake; metadata prevents global cache/repeated server probe and TOCTOU identity mismatch. Cost: commands.py and its focused tests enter Task2 scope; Task3 brief updated at handoff.

- Task3 retains the tab by starting verified interactive zsh after guarded Codex finishes or guard fails, inheriting CODEX_RESTORE_NO_AUTO. This avoids automatic close-on-exit profiles; user startup files that exit remain outside our control. Cost: startup runs again for the keep-open shell.

- Expand Task3 ownership narrowly to defer type annotations in bundled restore iterm.py and refresh provenance/hash. Its standalone shell child uses Python3.9 and Task1 union annotations broke import; focused integration regression exposed it. Preserve legacy restore compatibility rather than raise its interpreter requirement. Cost: Task3 review must cover this dependency correction in addition to launch files.

- Strengthen the plan's jobName-only success criterion with evidence that distinguishes actual interactive launch from helper commands. Spec requires actual Codex session, so its contract overrides the insufficient plan criterion; no retry or heuristic delay. Cost: narrow extra process/launch evidence and regressions may be necessary.

- Accept final-review Declined-to-judge boundaries for arbitrary user startup effects and atomic concurrent config/profile/runtime changes. Preserve user login shell and documented bounded snapshots rather than add sandboxing/locks. Cost: user startup or concurrent edits can still prevent a verified launch.
