# Codex Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Запускать самостоятельный Codex с поручением в одной новой вкладке iTerm2 через отдельный навык и проверяемую CLI-команду, сохраняя совместимость ручного копирования EN/RU.

**Architecture:** Новая подкоманда `launch-codex` выполняет узкую предварительную проверку и использует существующий транспорт `it2` из bundled restore с совместимым расширением параметров создания вкладки. Навык `iterm2-launch` подготавливает handoff и подтверждает получение задачи по уникальному ack. Установка навыка расширяет существующий bootstrap с отдельным receipt; установка функции restore не нужна.

**Tech Stack:** macOS, zsh, Python 3.11+, stdlib/unittest, штатный `it2`; без новых зависимостей.

**Spec:** `docs/superpowers/specs/2026-11-01-codex-launch-design.md` — обязательна к чтению вместе с планом.

## Global Constraints

- Только Codex; новая сессия, не resume. CLI: `python3 -m iterm2_utils launch-codex --window WINDOW_ID --profile PROFILE_NAME --cwd ABS_DIR --handoff ABS_FILE --json`.
- Все четыре значения обязательны: нет выбора текущего активного окна по умолчанию.
- Не добавлять `--no-alt-screen`, собственные model/API/config overrides или отключение защит.
- Перед запуском shell установить только для создаваемого процесса существующий `CODEX_RESTORE_NO_AUTO=1`.
- Существующие настройки Codex, shell-функция запуска, модель и endpoint сохраняются.
- Не повторять создание вкладки/запуск при неопределённом исходе; не закрывать её и не завершать процессы пользователя при ошибке.
- stdout не содержит handoff, сырые настройки, полный экран терминала, stderr внешних команд или секреты.
- Разработка и автотесты: TemporaryDirectory HOME/Paths, fake Runner/adapters. Никаких реальных настроек, GUI, auth или изменений разрешений разработчика.
- CLI/bootstrap/релиз/restore должны оставаться работоспособными из распакованного архива без исходного checkout. Bootstrap без `--skill` сохраняет прежнее поведение.
- Ни fixture, ни структурный validator не доказывают живую работу clipboard или поведение агента.
- Рабочая ветка `feat/codex-launch` в отдельном worktree; не менять основной checkout. Перед каждым коммитом проверять и индексировать только файлы задачи. Если появится другой исполнитель в том же worktree, не коммитить его изменения.

## Review Focus

1. Проектный/именованный override или другая конфигурация в login shell меняет TUI — нельзя объявить режим совместимым по одному пользовательскому TOML; тесты Task 2/3.
2. Профиль уже запускает Codex либо shell предлагает restore — новая команда запускает ровно один Codex; тест Task 3.
3. Вкладка создана, а ответ потерян; параллельно пользователь переключил окно — не появляется повторная/чужая вкладка; тесты Task 1/3.
4. Пути с кириллицей, кавычками, переводами строк и `$()` — значение приходит целиком, shell-подстановка не выполняется; тест Task 3.
5. Старое подтверждение или просто видимый стартовый экран — не доказательство принятого поручения; поведенческие сценарии Task 4 и статусы Task 3.

## Файлы и ответственность

- `runtime/codex_restore/codexlib/iterm.py`: совместимое расширение `new_tab` для явного профиля/команды и сохранение известного ID при ошибке. Не переносить весь restore.
- `iterm2_utils/launch_checks.py`: только входы/совместимость и ограниченное чтение относящихся к запуску настроек.
- `iterm2_utils/launch.py`: сборка команды, запуск одной вкладки и итоговые статусы; небольшой специализированный `LaunchITerm(ITerm)` переиспользует bounded `_run`, инвентаризацию и разрешение ID.
- `iterm2_utils/cli.py`: новая подкоманда, JSON/exit-коды и явный выбор навыка bootstrap; не прогонять общий doctor по всем интеграциям для запуска.
- `iterm2_utils/skill_install.py`: явный bundle `iterm2-launch` и отдельное владение его файлами.
- `skills/iterm2-launch/SKILL.md`, `skills/iterm2-launch/references/handoff.md`: инструкции запуска и формат передачи/подтверждения.
- `tests/test_launch_checks.py`, `tests/test_launch.py`, `tests/restore/test_iterm.py`: изолированные тесты новых границ и регрессия транспорта.
- `tests/test_skill_install.py`, `tests/test_cli.py`, `tests/test_export.py`, `tools/check_skill.py`, `tools/check_export.py`: установка, совместимость интерфейса и комплектность архива.
- `README.md`, `CHANGELOG.md`, `docs/compatibility.md`, `sources.lock.json`, `THIRD_PARTY_NOTICES.md`: публичные контракты, фактическая верификация и provenance изменённого порта.
- `docs/superpowers/validation/2026-11-01-codex-launch/`: ссылки на первоисточники, результаты проверок и отдельные held-out сценарии навыка; не включать в публичный runtime-архив.
- Личная заметка о новых вкладках и индекс памяти — только после готовности и установки навыка, вне публичного git diff.

## Task 1: Явный профиль и команда в существующем транспорте

**Files:** modify `runtime/codex_restore/codexlib/iterm.py`, `sources.lock.json`, `THIRD_PARTY_NOTICES.md`; create `tests/restore/test_iterm.py`; reuse `tests/restore/helpers.py`.

**Interfaces:** preserve `ITerm.new_tab(window_id: str) -> str` for restore; extend to `new_tab(window_id: str, *, profile: str | None = None, command: str | None = None) -> str`. Return remains the normalized terminal session ID. Extend `UnknownTabOutcome(message: str, *, tab_id: str | None = None)` to carry an already observed tab ID; existing callers/catches remain valid. `_created_tab` receives the same keyword parameters. Launch later reads the new tab ID from `panes()` or from the exception.

- [ ] **RED:** add `test_legacy_new_tab_argv_unchanged`, `test_explicit_profile_command_are_single_argv`, `test_result_must_belong_to_requested_window`, `test_created_but_inventory_times_out_retains_tab_id`. Core assertions: `argv == [it2, 'tab', 'new', '--window', window, '--profile', profile, '--command', command]`; only one `tab new` call; unrelated simultaneous tab is never returned; missing/ambiguous inventory raises `UnknownTabOutcome`; known returned tab ID survives later timeout. Legacy call has no new flags.
- [ ] Run `python3 -m unittest tests.restore.test_iterm -v`; confirm failures are missing behavior, not fixture/import defects.
- [ ] Implement the optional flags and exception metadata in the existing transport. Retain process-group cleanup for its own bounded subprocesses, deadline, JSON validation and normalization. Validate optional profile/command before invoking the mutating call. No new retry of `tab new`.
- [ ] Run `python3 -m unittest tests.restore.test_iterm tests.restore.test_restore tests.restore.test_snapshots -v`; all PASS. Update only this port file's bundled `sha256` and transformation description, preserving upstream hash/ref/license; run `python3 tools/check_sources.py`.
- [ ] Commit only the listed files: `feat: support explicit profile and command in tab creation`.

## Task 2: Предварительная проверка режима и входных данных

**Files:** create `iterm2_utils/launch_checks.py`, `tests/test_launch_checks.py`, `docs/superpowers/validation/2026-11-01-codex-launch/source-contracts.md`; extend `iterm2_utils/discovery.py` only to expose/reuse app-bundle lookup if required, preserving existing callers.

**Interfaces:** frozen `LaunchRequest(window_id: str, profile: str, cwd: Path, handoff: Path)`; `validate_request(request: LaunchRequest) -> None` raises `ValueError` with a fixed reason code. `check_profile(profile: dict) -> list[Finding]`. `inspect_launch(paths: Paths, request: LaunchRequest, runner: Runner) -> tuple[Path | None, list[Finding]]` returns the validated it2 executable and sanitized findings. `Finding.feature='launch'`, `agent='codex'`. No GUI mutation or installation here.

- [ ] Establish source contracts before implementing config logic: inspect official Codex 0.166.0 schema/config-loading code and iTerm2 source/help. Record exact keys/defaults, user/system/project/profile precedence, supported read-only effective-config mechanism, `it2 profile show NAME --json` shape, `session.profileName` and `session.jobName` meanings. Use source/fixture copies only. If Codex exposes a read-only effective-config API, prefer it; otherwise resolve only relevant keys according to the verified loading rules, without executing project instructions. An unresolvable effective config yields `launch_config_unverified` before creation; never silently treat it as defaults. Do not build a second general Codex config framework. If no bounded way meets this contract, report that concrete implementation blocker before continuing Tasks 2/3, rather than weakening the approved check.
- [ ] **RED:** `test_invalid_paths_create_no_side_effects`: relative cwd/handoff, missing directory, directory as handoff, unreadable file, symlink/FIFO and NUL reject; a normal readable UTF-8-named file is accepted. Check `f.snapshot() == before`. ID/name must be nonempty and free of NUL/control characters; valid spaces and Unicode in profile names are preserved.
- [ ] **RED:** `test_copy_bindings_compare_semantics`: both `0x63` and `0x441` Ctrl entries send byte `03`; Cmd entries send bytes `1b 5b 39 39 3b 39 75`, Action 11. Additional Version/Apply Mode metadata must not cause false conflicts. Missing/wrong bindings, ambiguous profile names or unavailable inherited values produce blocking findings, with no writes.
- [ ] **RED:** `test_effective_tui_overrides`: default compatible fixture succeeds; `alternate_screen='never'`, fullscreen transcript disabled, conflicting selected profile/project layers and malformed/unreadable config do not. Inherit-only layer missing a key is distinct from explicitly disabling it. Include a fixture where top-level config is compatible but effective project config is not. For the spec's manual-copy acceptance, also check effective `copy_on_select='never'` and the one iTerm2 preference `CopySelection=false` using the existing preference reader; mismatch directs to setup without writes. Findings never include secret sentinels in unrelated MCP/provider fields.
- [ ] **RED:** missing/non-macOS platform, unknown/incompatible protocol, missing Codex/zsh/it2, unavailable window or profile all fail before `tab new`. A non-default `CODEX_HOME`, `ZDOTDIR` and selected app bundle are honored through existing path conventions; do not print those environments wholesale.
- [ ] Run `python3 -m unittest tests.test_launch_checks -v`, observe RED, implement the interfaces using existing path resolution and safe config readers, then rerun to PASS. Keep supported-version/source evidence separate from live acceptance.
- [ ] Commit the checks, tests and source evidence: `feat: validate Codex launch prerequisites`.

## Task 3: Команда запуска одной адресной вкладки

**Files:** create `iterm2_utils/launch.py`, `tests/test_launch.py`; modify `iterm2_utils/cli.py`, `tests/test_cli.py`.

**Interfaces:** consumes Task 1 transport and Task 2 request/checks. `build_command(request: LaunchRequest, zsh: Path) -> str`; `launch(request: LaunchRequest, paths: Paths, runner: Runner) -> tuple[int, dict]`. `LaunchITerm(ITerm)` adds `profile(name: str) -> dict` and `variable(terminal: str, name: str) -> str`, using inherited bounded `_run`. Import bundled transport from `runtime.codex_restore.codexlib.iterm` in checkout/archive; never import an installed restore or depend on its receipt. No new base framework.

**Output:** `mode='launch_codex'`, `status`, `window_id`, `tab_id`, `session_id`, `profile`, `findings`; unavailable IDs are null. `launched` / exit 0 requires exact session identity, expected applied profile, and `session.jobName == 'codex'`; `created_unverified` / exit 3 preserves IDs when those observations are incomplete; `unknown` / exit 3 means mutation may have happened without a fully identified result; `blocked` / exit 2 means a definite prerequisite failure before mutation. No `received` CLI status: receipt of the task belongs to the skill's ack check.

- [ ] **RED:** `test_launch_selects_exact_window_profile_and_one_process`: use fake transport and temporary profile whose custom Command would launch another Codex. Assert one `tab new` with an explicit overriding command, no `session run`, no focus/close, and no `--no-alt-screen` or model/API flags. Change active window during the fake call; returned session still belongs to requested window.
- [ ] **RED:** `test_login_shell_keeps_function_and_blocks_auto_restore`: execute only in temporary HOME/ZDOTDIR with fake `codex` shell function and fake binary. `.zshrc` logs `CODEX_RESTORE_NO_AUTO`; assert it is `1`, the function is invoked once, no restore prompt/start occurs, argv contains `-C`, exact cwd and one prompt referencing the handoff. No actual Codex/network/GUI. Reject a mismatch between config location/version observed at preflight and inside the target shell before calling Codex; do not claim a validated effective config for a different executable/HOME.
- [ ] **RED:** `test_quoting_does_not_execute_user_values`: table-driven cwd/handoff with spaces, Cyrillic, single/double quotes, newlines, backticks and `$()`; fake function receives byte-equivalent arguments, sentinel files from substitutions do not appear. The prompt never inlines handoff contents. Use `shlex.join/quote` at each shell boundary, not JSON escaping.
- [ ] **RED:** `test_mutation_timeout_never_retries`, `test_no_job_is_created_unverified`, `test_wrong_profile_is_not_launched`, `test_failed_observation_preserves_ids`, `test_subprocess_stderr_is_not_echoed`. Assert status/exit codes above and exactly one create attempt; no close/kill of terminal processes. Include malformed inventory and a known tab ID with unresolved session ID.
- [ ] Run `python3 -m unittest tests.test_launch tests.test_cli -v`; establish RED. Implement command construction through a login interactive zsh, with `CODEX_RESTORE_NO_AUTO=1` set before startup, and the narrow launch flow. Budget each external call at most 3 seconds and total launch observation 15 seconds; poll only reads within that deadline. Failure after successful creation retains the tab, never rolls it back.
- [ ] Register the four required args and `--json` in CLI. Dispatch before general `discover()`/feature receipt handling; existing setup commands keep their output contract. Text mode prints the same sanitized status/IDs. Reject arbitrary extra flags. Rerun targeted tests to PASS and the restore Python regression to verify namespace imports do not disturb standalone restore.
- [ ] Commit: `feat: launch Codex in a verified iTerm2 tab`.

## Task 4: Навык запуска и проверка получения handoff

**Files:** create `skills/iterm2-launch/SKILL.md`, `skills/iterm2-launch/references/handoff.md`, `docs/superpowers/validation/2026-11-01-codex-launch/skill-cases.md`, `docs/superpowers/validation/2026-11-01-codex-launch/skill-results.md`; reuse isolated fake CLI/MCP pattern from `tests/test_agent_workflow.py` rather than allowing model commands on the real machine.

**Interfaces:** consumes Task 3 JSON and exit codes. One UUID per launch creates a private local directory containing `handoff.md` and initially absent `ack.json`. Handoff states `request_id`, absolute ack path and task. Ack schema: `{request_id, thread_id, cwd, accepted_task, first_step}` with nonempty strings and matching UUID/cwd. This is acknowledgement of reading, not approval of a design or completion of the task. CLI remains unaware of ack.

- [ ] Before writing the skill, apply `superpowers:writing-skills` and prepare held-out cases: normal new Codex task, existing foreign/profile without bindings, lost create response, stale/mismatched ack, missing source-session ID, request for an internal subagent. Record baseline behavior in fresh isolated processes with no real tools; do not put held-out names/IDs/expected full answers into the skill. If authorized inference/auth is unavailable, record that the behavioral run is blocked, not PASS; do not reuse this session's cached skill as evaluation.
- [ ] Write the minimal discovery description and instructions: warn about new tab; use current verified checkout/release; identify parent session and window explicitly; prepare task-scoped handoff with restrictions and material paths; inspect compatible profile; call exactly Task 3 command; never append compatibility-breaking flags or fall back after denied automation.
- [ ] Define receipt checks: verify returned target ID, then fresh ordinary non-symlink `ack.json`, matching request UUID/cwd and required nonempty fields. Wait at most 120 seconds, in intervals no longer than 10 seconds, with a progress message by 60 seconds. If incomplete, report IDs and actual status, retaining artifacts. Never resend the prompt/create again automatically. An old ack, startup banner, process name or empty file is insufficient.
- [ ] For `unknown`, inspect existing target/read-only inventory and known IDs; if identity cannot be established, report uncertainty. For `blocked`, explain the specific prerequisite and use setup skill when needed, not silently install features. For an internal-subagent/Claude request, do not launch Codex in a new tab.
- [ ] Run `python3 tools/check_skill.py skills/iterm2-launch`; PASS is structural only. Rerun the same held-out cases in fresh isolated processes with the new skill; inspect actual calls and loaded body, not only prose summaries. Save exact commands, skill hash and result/limitation. No genuine API-bound process without verified endpoint and existing authorization.
- [ ] Commit skill and verification artifacts: `feat: add Codex tab launch skill`.

## Task 5: Установка второго навыка без изменения старого bootstrap

**Files:** modify `iterm2_utils/skill_install.py`, `iterm2_utils/cli.py`, `tests/test_skill_install.py`.

**Interfaces:** extend `build(context, agents, *, skill='iterm2-setup') -> ChangeSet`, `install(context, agents, runner, *, dry_run=False, skill='iterm2-setup') -> list[Finding]`. Static bundles: setup retains existing `FILES`; launch has `SKILL.md`, `references/handoff.md`. CLI `--skill` choices are `iterm2-setup|iterm2-launch`, default setup. Launch accepts only `--agent codex`; reject claude/both before file inspection or writes.

- [ ] **RED:** `test_default_bootstrap_retains_legacy_receipt`, `test_launch_bootstrap_is_codex_only`, `test_both_skill_receipts_coexist`, `test_launch_dry_run_has_no_probes_or_writes`, `test_launch_foreign_modified_symlink_preserved`. Assert setup still owns `data/bootstrap-skill/receipt.json`; launch uses `data/bootstrap-skill-iterm2-launch/receipt.json`. Destinations differ by skill name; feature receipt and all other skill files remain byte-identical.
- [ ] Run `python3 -m unittest tests.test_skill_install -v`; confirm RED. Generalize the current explicit bundle/destination/context selection with the keyword argument only. Preserve CAS, modes, ownership, corruption errors and existing public signatures/defaults; no implicit installation of both skills.
- [ ] Rerun `python3 -m unittest tests.test_skill_install tests.test_cli -v`; all PASS, including existing source-update and separate-agent bootstrap scenarios. Commit: `feat: install the Codex launch skill explicitly`.

## Task 6: Поставка, регрессия и фактическая приёмка

**Files:** modify `tools/check_skill.py`, `tools/check_export.py`, `tests/test_export.py`, `README.md`, `CHANGELOG.md`, `docs/compatibility.md`; create `docs/superpowers/validation/2026-11-01-codex-launch/verification.md`.

**Interfaces:** default `check_skill.py` validates both shipped skills while explicit directory argument keeps its behavior. `EXPORT_FILES` explicitly includes new runtime modules, skill/reference and tests, with no personal memory or validation transcripts. Release archive contains the `runtime` namespace needed by launch and the complete independent installed restore.

- [ ] **RED:** add `test_extracted_release_launch_without_restore_install` and `test_launch_and_standalone_restore_after_source_removed`: build/extract fixture archive, move source checkout out of reach, import/run launch with fake adapters, then install fixture restore and remove archive. Restore help/fixture lifecycle must still work; launch must not require a restore receipt. Test both default setup bootstrap and explicit launch bootstrap from the archive.
- [ ] Run `python3 -m unittest tests.test_export -v`; confirm RED. Update explicit exports and validation entrypoint, then rerun to PASS. Do not handwave namespace-import coverage as `--help` success alone: exercise fake launch through its transport.
- [ ] Document exact CLI, required profile/setup, flags omitted, preserved shell wrapper, statuses and no-retry rule. Add a changelog entry using the repository's current format. Record source-supported versions and distinguish fixtures, skill behavioral runs and live clipboard evidence.
- [ ] Run once on final implementation: `python3 -m unittest discover -v`; `/bin/zsh tests/test_codex_shell.zsh`; `/bin/zsh tests/restore/test_codex.zsh`; `python3 tools/check_sources.py`; `python3 tools/check_skill.py`; `python3 tools/check_export.py`; `python3 tools/build_release.py --destination dist`; `git diff --check`. Expected: zero failures, both skills structurally valid, sources/export checks pass, archive built. Record actual counts; repeat only affected checks after new changes.
- [ ] Inspect the complete diff against the SPEC, including packet/restore/installation callers; obtain final review according to the chosen execution method. No claim of complete implementation while a required fixture regression remains failing.
- [ ] In an available isolated Mac account/VM only: launch from another agent; check profile before interaction, one Codex, fresh matching ack, Cmd+C → Cmd+V in ABC/Russian without manual restart or auto-copy, unchanged neighboring session. Preserve observed versions/steps/results. If unavailable, mark live-unverified; do not open the developer's real tabs as a substitute. A user-authorized exception to AGENTS.md must be explicit before such acceptance.
- [ ] Commit docs/export/tests: `test: verify Codex launch distribution and compatibility`. Do not publish a release or push/merge as part of this plan.

## Task 7: Подключение готового навыка и личного правила

**Files:** installed Codex skill via supported bootstrap; existing private `new-agent-task-open-iterm2-tab.md` and its MEMORY.md index entry. These files never enter the public repo or archive.

**Interfaces:** consumes completed Tasks 1–6 and explicit `bootstrap-skill --skill iterm2-launch --agent codex`; preserve the same public command/receipt, no manual copying over foreign skills.

- [ ] After development gates, run bootstrap dry-run for the requested personal installation, inspect the concrete diff/ownership result, then install through the supported path within authorized scope. This is delivery of the requested skill, not live GUI acceptance; do not inspect unrelated real app settings. On a foreign destination preserve it and report exact conflict.
- [ ] Verify installed skill/reference hashes against the chosen source and confirm both skill paths coexist. Do not declare discovery in the running parent process refreshed without evidence; explain if a fresh session is required.
- [ ] Read applicable personal memory routing/write rules. Update the existing new-agent-tab note and its index text: use `iterm2-launch` for Codex, never add `--no-alt-screen` with the internal-copy profile, confirm handoff receipt, keep existing task authorization/window warning guidance. State the diagnosed mode incompatibility and the live-check limit accurately. User chose this memory routing in the design; no new destination question is needed.
- [ ] Check the links point to the actually installed skill and review only this task's private diff. Final report includes installed location, feature/test status and any live-unverified boundary. Do not claim clipboard fixed by fixture checks alone.

## Self-review before handoff

- Spec command/profile/window/config validation → Tasks 1–3; shell integrations and one-start invariant → Task 3.
- Handoff, unique receipt, timeouts and no-repeat behavior → Task 4 and Task 3 statuses.
- Bootstrap compatibility, ownership and export → Tasks 5–6; old restore's independent installation → Tasks 1 and 6.
- Private memory routing and usable installation → Task 7, after readiness rather than a premature link.
- All five Review Focus cases have named checks. Shared signatures and keyword defaults are consistent across tasks.
- Important implementation evidence still to collect is explicitly owned by Task 2 (effective configuration/CLI schemas), not assumed from a matching profile name. Live and behavioral acceptance remain separate from deterministic tests.

Execution method has not been selected yet. Recommended: subagent-driven with task-level review, then whole-branch review; these tasks change public CLI/bootstrap and shared restore boundaries.
