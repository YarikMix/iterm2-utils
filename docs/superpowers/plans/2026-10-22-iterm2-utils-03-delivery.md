# iterm2-utils: Agent Setup and Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Завершить выборочную установку/миграцию/обновление и опубликовать набор, который коллега настраивает одним обращением к агенту.
**Architecture:** Общий lifecycle использует receipts и builders первых двух частей. Скилл выбирает фичи с человеком, вызывает детерминированный CLI, затем выполняет только оставшиеся UI-действия и повторную проверку.
**Tech Stack:** Python 3.11+/unittest, zsh, Agent Skills SKILL.md, optional Peekaboo, GitHub Actions/gh.
**Spec:** [Спецификация](../specs/2026-10-22-iterm2-utils-design.md); [основной план](2026-10-22-iterm2-utils.md); контракты [I](2026-10-22-iterm2-utils-01-core.md) и [II](2026-10-22-iterm2-utils-02-integrations.md).

## Global Constraints

- «Агент сначала уточняет у коллеги, какие фичи подключить»; существующая явная авторизация сохраняется.
- «Если Peekaboo отсутствует, даёт коллеге точные инструкции для ручного шага».
- «Обновление работает только с собственными записями и управляемыми блоками».
- «Удаление убирает только принадлежащие пакету компоненты»; пользовательские изменения не затираются backup.
- «Мок-тесты не называются живой приёмкой»; публикуется реально проверенная матрица.
- Публичный `https://github.com/YarikMix/iterm2-utils`; корпоративные сервисы/PAIW для установки не требуются.
- «Старые репозитории и текущая рабочая установка автора при разработке нового пакета не изменяются».

## Review Focus

1. Уже установлен старый plugin/функция codex/MCP — не перезаписывать, предложить reuse/явную миграцию: задача 9.
2. Удаляется status, но notifications/restore нужны общие hooks/wrapper — зависимости остаются: задача 9.
3. Агент не имеет Peekaboo или получил отказ — остаются точные ручные шаги, не ложная готовность: задача 10.
4. Пользователь выбрал только часть набора и только одного агента — меню/план/результат не расширяют выбор: задача 10.
5. Source checkout удалён, версия обновилась, machine paths в архиве — runtime продолжает работу, публичный артефакт переносим: задача 11.

---

## Task 9: Составные операции, pending UI и явная миграция

**Files:** Create `iterm2_utils/{lifecycle,migration}.py`, `tests/{test_lifecycle,test_migration,test_pending_ui}.py`; Modify `cli.py`, `planner.py`, `state.py` через владельца общего engine.
**Interfaces:** Consumes all builders and engine. Produces `lifecycle.install(context: Context, selection: Selection, runner: Runner, *, dry_run: bool = False) -> Outcome`, `lifecycle.update(context: Context, runner: Runner, *, dry_run: bool = False) -> Outcome`, `lifecycle.uninstall(context: Context, owners: frozenset[str], runner: Runner, *, dry_run: bool = False) -> Outcome`, `lifecycle.reconcile_ui(context: Context, code: str, runner: Runner) -> Outcome`, `migration.inspect(context: Context) -> list[Finding]`, `migration.build(context: Context, selection: Selection) -> ChangeSet`.

- [ ] **1. RED:** Tests `test_legacy_status_reused_without_duplicate_hooks`, `test_adopt_legacy_is_required_for_transfer`, `test_partial_uninstall_retains_shared_runtime`, `test_user_modified_mcp_is_not_removed`, `test_failed_feature_does_not_rollback_independent_completed_feature`, `test_readonly_plan_and_dryrun_do_not_create_backups`, `test_native_ui_reconcile_claims_only_new_cc_status_hooks`, `test_update_with_no_receipt_has_no_implicit_full_selection`. Assert existing plugin/settings/shell blocks unchanged without adopt; update with receipt preserves exact selected features; uninstall leaves conversation files and cache; timeout remains unconfirmed, not automatically retried.
Assertions (fixture-local captures):

```python
assert "status" not in outcome.receipt.selection.features
assert "notifications" in outcome.receipt.selection.features
assert shared_hook_still_exists is True
assert unrelated_after == unrelated_before
```

- [ ] **2. Verify RED:** `python3 -m unittest tests.test_lifecycle tests.test_migration tests.test_pending_ui -v`; expected no lifecycle wiring.
- [ ] **3. Implement lifecycle and CLI:** Complete `install/update/uninstall/doctor/plan` with `--dry-run`, `--json`, explicit selection for first install; update defaults to receipt selection only. `--adopt-legacy` handles recognized `codex-iterm2-status`/`codex-resume` blocks and exact source commands, never fuzzy basename matches. Reuse first; transfer disables the specifically identified old status plugin through supported mechanism, preserves its source/cache and reversible prior enabled value, then replaces only known hooks/blocks. Unknown shell functions/aliases stop that feature with actionable conflict; do not source or rewrite arbitrary functions. After each feature checkpoint save receipt; failed dependent resources rollback within that feature, independent successes remain reported. Shared resources keep consumer refs. Implement `reconcile --step <code>`: compare pre-UI relevant settings snapshot, identify only exact new native cc-status entries, mark externally pre-existing resources as reused; no claiming unrelated Workgroup changes. Failed UI verification remains pending, not installed.
- [ ] **4. Verify GREEN:** same command plus `python3 -m unittest discover -s tests -t . -v`; synthetic all-feature install→repeat→update→partial uninstall→full uninstall preserves foreign settings/mtime where unchanged. Nonzero/pending command returns structured outcomes, never stores full CLI outputs or unrelated credentials.
- [ ] **5. Commit:** scoped lifecycle/migration/tests, `git commit -m "feat: support selective lifecycle and explicit legacy migration"`.

## Task 10: Общий скилл, bootstrap и проверка действий агента

**Files:** Create `skills/iterm2-setup/SKILL.md`, `skills/iterm2-setup/references/{features,ui,troubleshooting}.md`, `iterm2_utils/skill_install.py`, `tests/{test_skill_install,test_agent_workflow}.py`, `tools/check_skill.py`, `AGENTS.md`; Modify `cli.py`, `README.md`.
**Interfaces:** Consumes read-only discovery, plan/install/doctor/reconcile and Finding states. Produces `skill_install.build(context: Context, agents: frozenset[str]) -> ChangeSet` and CLI `bootstrap-skill --agent codex|claude|both [--dry-run]`. Test support models permitted tool invocations and filesystem artifacts, not skill wording.

- [ ] **1. RED:** `test_skill_install_does_not_replace_foreign_directory`, `test_bootstrap_uses_actual_home_and_codex_home`, `test_partial_choice_limits_install`, `test_no_peekaboo_produces_pending_instruction`, `test_peekaboo_denial_does_not_trigger_osascript_bypass`, `test_user_says_done_requires_reconcile`, `test_missing_python_does_not_install_second_agent`. For skill behavior first save held-out requests/fixtures and expected actions before writing instruction: clean Codex-only with only clipboard; Claude-only notifications with no Peekaboo; both agents but existing foreign MCP and selected shell only; partial install and manual API confirmation. Assert actual CLI edits/calls/report states for each outcome, not matching prose.
Assertions (fixture-local captures):

```python
assert any(f.state == "pending_ui" for f in outcome.findings)
assert unselected_feature_writes == []
assert fallback_after_peekaboo_policy_denial == []
```

- [ ] **2. Verify RED:** `python3 -m unittest tests.test_skill_install -v`; expected missing bootstrap. Run a baseline independent agent on held-out fixtures without new skill, read-only/fake tools, save actual behavior as baseline. Do not forward real user settings/transcripts. If no independent harness supports controlled tools, record limitation and use concrete workflow contract tests; do not claim behavioral GREEN from parsing Markdown.
- [ ] **3. Write skill/bootstrap:** Short standard frontmatter `name: iterm2-setup`, descriptive automatic discovery, no requirement for PAIW/superpowers/other private skills. Entry: obtain/read repo, choose Python>=3.11, doctor; ask which detected-agent features to enable; list required dependencies before installing via existing package manager; plan→install→doctor→reconcile. Do not require repeated approval for previously selected necessary writes. Peekaboo detection via actual available tool schemas/connection, not assuming CLI installation equals permission; no tool means localized manual menu path, system dialog remains human. Explain current session may need restarting to load hooks but never restart user's session automatically. Distinguish top-level Profiles (opens new tab) from Session→Edit Session→Use Selected Settings (existing tab). Include large-text race limitation and Codex-only scope. Bootstrap copies self-contained skill + necessary public references to Codex `${CODEX_HOME:-~/.codex}/skills/iterm2-setup` and Claude `~/.claude/skills/iterm2-setup`; if corresponding official discovery also supports shared `.agents/skills`, document it as alternative, not a duplicate install. Foreign path conflict is reported; owned version updated by receipt. README has one message colleagues can paste with GitHub URL and a manual CLI fallback; skill can be read before dynamic discovery refresh.
- [ ] **4. Verify GREEN:** structural skill validation plus unittest; independent fresh agent re-runs same held-out requests against isolated fake HOME/tool fixture after skill creation. It must actually pick only allowed edits and leave blocked UI pending. Fresh process/context required after body changes; stale cached skill list/body is not evidence. Add docs for update/uninstall/missing deps and `AGENTS.md` minimal repo invariants. No machine-specific author paths or private dependency skills in exported package.
- [ ] **5. Commit:** scoped skill/bootstrap/tests/docs, `git commit -m "feat: guide Codex and Claude through selective iTerm setup"`.

## Task 11: Переносимость, живая приёмка и публичная публикация

**Files:** Create `.github/workflows/test.yml`, `tools/{check_export,build_release}.py`, `tests/test_export.py`, `docs/compatibility.md`, `CHANGELOG.md`, `LICENSE`; Modify README and lock/notices only when verified source facts change.
**Interfaces:** Consumes complete CLI/skill/all tests. Produces `build_release.build(repo: Path, destination: Path) -> Path` with allowlisted archive (no `.git`, local cache, receipts, fixtures containing user state); `check_export.check(repo: Path) -> list[str]` checks provenance/licensing/private paths/internal URLs. Default release `v0.1.0-beta.1`, no unsupported stable-production claim.

- [ ] **1. RED:** `test_export_excludes_state_and_secret_fixtures`, `test_missing_notice_or_source_hash_fails`, `test_fresh_extract_has_no_source_checkout_dependency`, `test_release_cli_scenarios_are_hermetic`. Archive permitlist excludes `.env*`, auth/config backups, `.git/config`, logs and transcripts regardless of ignore rules. Fixture private marker must be absent from archive bytes, while all runtime module imports and licenses present.
Assertions (fixture-local captures):

```python
assert b"PRIVATE_FIXTURE_MARKER" not in archive_bytes
assert "skills/iterm2-setup/SKILL.md" in archive_members
assert "vendor/codex_status/LICENSE" in archive_members
```

- [ ] **2. Verify RED:** `python3 -m unittest tests.test_export -v`; expected missing export/build tool.
- [ ] **3. Implement/export and CI:** Linux/macOS unit tests Python 3.11 and current Python, fake app/CLI/preferences for all mutation tests, zsh shell tests on macOS; no AppleScript/GUI mutation on CI runner. Export only source/skill/vendor/licenses/docs needed by package. Lock verified bytes and no mutable branch dependency. Scans exclude the existence of public GitHub URLs but reject real corporate URLs/author home paths in shipped code/resources; documentation fixture examples use neutral paths. `tools/check_export.py` returns errors, not full offending secret lines.
- [ ] **4. Verify automated package:** `python3 -m unittest discover -s tests -t . -v`; `/bin/zsh tests/test_codex_shell.zsh`; `/bin/zsh tests/restore/test_codex.zsh`; `python3 tools/check_sources.py`; `python3 tools/check_skill.py`; `python3 tools/check_export.py`; build and re-run same CLI fixture smoke from freshly extracted archive in separate directory. Move original checkout away in fake environment; installed runtime must still work. Record exact test totals, versions and limitations.
- [ ] **5. Verify live acceptance:** Before opening any own window, warn user. Use isolated macOS account/VM or explicitly isolated app preferences and test HOME; do not install over author’s current working config. In one dedicated test tab verify copy in EN/RU, profile changes on `codex` start/exit, no extra command after copy; selected hotkeys byte-level behavior; shell marks. For each installed agent verify actual emitted working/waiting/idle and notifications without raw hook synthesis being called live CLI evidence. Verify foreground suppression/click to correct tab, no false completion on interrupt; fzf selection launches only selected Codex conversations and preserves CODEX_HOME/cwd; MCP reads test session and cannot execute arbitrary shell. Close only own test windows. If clean/live environment is unavailable, finish isolated tests and document precisely which live cases remain unverified in beta matrix; do not overwrite current setup to obtain a checkmark.
- [ ] **6. Commit and publish:** Source/skill branch review against spec (not only task checkboxes), resolve findings and re-run only affected checks. Commit scoped package/docs. User already authorized public `YarikMix/iterm2-utils`; no new permission loop is needed. Verify `gh api user --jq .login` = `YarikMix` and repo name availability, create `gh repo create YarikMix/iterm2-utils --public --source . --remote origin` without implicit push, set branch `main`, push reviewed branch/initial main without force, create beta release from built archive/checksums. If remote now exists unexpectedly, inspect and reconcile instead of overwriting. Check remote source/README/skill links and CI result with gh; final response links repo and reports actual validation limitations. Do not publish any private repo/working-tree contents outside scoped files.

## Самопроверка после всех задач

Все семь feature IDs доступны для выбора; каждая комбинация может быть представлена без скрытых фич. Общая CLI/engine-логика не продублирована в скилле. Ни один task не требует, чтобы пользователь перенёс секреты или поставил PAIW. Наличие инструкции к UI не выдаётся за выполненный UI-шаг. Документированные непроверенные live-сценарии не превращаются в обещание их поддержки.
