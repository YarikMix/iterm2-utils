# iterm2-utils: Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Получить работающий CLI для явного выбора и настройки clipboard, shell integration и отдельных hotkeys.
**Architecture:** Read-only discovery строит Context; чистые feature builders возвращают ChangeSet. Один engine применяет адресные изменения с receipts, проверкой ожидаемого значения и откатом.
**Tech Stack:** macOS/zsh, Python 3.11+ stdlib (`dataclasses`, `tomllib`, `plistlib`, `unittest`), iTerm2 profiles/preferences.
**Spec:** [Спецификация](../specs/2026-10-22-iterm2-utils-design.md); [общий порядок и карта файлов](2026-10-22-iterm2-utils.md).

## Global Constraints

- «Агент сначала уточняет у коллеги, какие фичи подключить»; пустой выбор — ошибка без записи.
- `tui.copy_on_select = "never"`; `CopySelection = false` только при выборе clipboard.
- «Codex-профиль никогда не назначается `claude`»; правило — `&codex`.
- «Установка идемпотентна»; общие файлы и symlinks пользователя сохраняются.
- macOS + zsh; «Старые репозитории и текущая рабочая установка автора при разработке нового пакета не изменяются».

## Review Focus

1. Symlink `.zshrc` и Unicode пути — пишется цель с прежними правами, source корректно quoted: задача 2/4.
2. TOML с inline/dotted tables, multiline strings, несколькими профилями — формат сохраняется либо адресная ошибка до записи: задача 2/3.
3. Другой процесс меняет файл между plan/apply — CAS останавливает запись, не теряет чужую правку: задача 2.
4. У пользователя только Claude или только Codex — выбранный набор не требует второй CLI: задача 1.
5. Hotkeys без clipboard и унаследованный Keyboard Map — исходные сочетания сохраняются, копирование не добавляется: задача 3.

---

## Общие интерфейсы, создаваемые задачей 1

В `iterm2_utils/models.py` — dataclasses; это контракт всех трёх планов:

- `Selection(agents: frozenset[str], features: frozenset[str], shortcuts: frozenset[str], parent_profile: str, adopt_legacy: bool = False)`.
  Agents: `codex`, `claude`; features: `clipboard`, `status`, `notifications`, `restore`, `mcp`, `shell`, `shortcuts`; shortcut IDs: `ctrl-v-ru`, `alt-enter`, `ctrl-q`, `resume`.
- `Paths(home: Path, zshrc: Path, codex_home: Path, claude_settings: Path, config: Path, cache: Path, data: Path, profiles: Path, repo: Path)`; все пути абсолютные. Claude settings по умолчанию `~/.claude/settings.json`.
- `Finding(feature: str, agent: str | None, code: str, state: str, message: str)`; state: `ready`, `missing_dependency`, `conflict`, `pending_ui`, `new_session`, `unavailable`.
- `Context(paths: Paths, executables: dict[str, Path], versions: dict[str, str], capabilities: frozenset[str], profiles: dict[str, dict], installed: dict[str, dict])`.
- `FileEdit(path: Path, before: bytes | None, after: bytes | None, mode: int, owner: str)`; `PreferenceEdit(domain: str, key: str, before: object, after: object, owner: str)`; `RegistrationEdit(agent: str, name: str, before: dict | None, after: dict | None, owner: str)`.
- `UiStep(code: str, feature: str, agent: str | None, instruction: str)`; `ChangeSet(edits: list[FileEdit | PreferenceEdit | RegistrationEdit], ui: list[UiStep], findings: list[Finding])`.
- `Plan(selection: Selection, changes: ChangeSet, fingerprint: str)`; `Receipt(version: str, selection: Selection, resources: list[dict], pending_ui: list[UiStep])`; `Outcome(receipt: Receipt, findings: list[Finding])`.
- `Runner.run(argv: list[str], *, timeout: float, stdin: str | None = None) -> subprocess.CompletedProcess[str]` в `commands.py`; `run` не использует shell=True и не логирует argv/payload целиком.
- Каждый builder имеет `build(context: Context, selection: Selection) -> ChangeSet`, не пишет файлы и не запускает GUI. `owner` — стабильный ID фичи; для общей зависимости `owner="shared:<id>"`, ссылки потребителей хранятся в receipt.

## Task 1: Диагностика, выбор фич и CLI без побочных эффектов

**Files:** Create `iterm2_utils/{__init__,__main__,cli,models,commands,discovery,planner}.py`, `tests/{__init__,test_discovery,test_selection,test_cli}.py`, `tests/support.py`, `README.md`, `.gitignore`.
**Interfaces:** Consumes spec + contracts above. Produces `discovery.discover(paths: Paths, runner: Runner) -> Context`, `planner.validate(selection: Selection, context: Context) -> list[Finding]`, `planner.plan(context: Context, selection: Selection) -> Plan`, `cli.main(argv: list[str]) -> int`. Fixtures in `tests/support.py` provide fake CLI/app binaries in TemporaryDirectory, never load real user dotfiles.

- [ ] **1. RED:** Tests `test_empty_choice_writes_nothing`, `test_claude_only_never_probes_codex`, `test_missing_binary_blocks_only_affected_feature`, `test_doctor_redacts_other_mcp_env`. Assert empty choice exits 2; doctor/plan leave tree bytes identical; a fake secret in unrelated config is absent from stdout/stderr; unsupported Codex-only feature on Claude appears in findings, not installed selection.
Assertions (fixture-local captures):

```python
assert exit_code == 2
assert tree_after == tree_before
assert "UNRELATED_SECRET_MARKER" not in stdout + stderr
```

- [ ] **2. Verify RED:** `python3 -m unittest tests.test_discovery tests.test_selection tests.test_cli -v`; expected missing imports/CLI, no real process probing from fixtures.
- [ ] **3. Implement interfaces:** Add `doctor [--json]`, `plan --agent codex|claude|both --features <csv> [--shortcuts <csv>] [--parent-profile <name>] [--json]`. Commands return only inspection/plan. Exit 0 ready, 2 selection/conflict/missing dependency, 3 pending UI/new session. Installed iTerm discovery: explicit override, `/Applications/iTerm.app`, `~/Applications/iTerm.app`; validate `Info.plist` and capability probes with 5s timeout. Resolve `ZDOTDIR`, `CODEX_HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME` without printing environment. Never source `.zshrc` during inspection.
- [ ] **4. Verify GREEN:** same unittest command; `python3 -m iterm2_utils --help` lists only implemented subcommands; README documents read-only usage and incomplete installation state.
- [ ] **5. Commit:** `git add iterm2_utils tests README.md .gitignore` after scoped status review; `git commit -m "feat: add read-only setup discovery and feature selection"`.

## Task 2: Адресные правки, CAS и журнал владения

**Files:** Create `iterm2_utils/{engine,state}.py`, `iterm2_utils/config/{__init__,jsonfile,tomlfile,zshrc,preferences}.py`, `tests/{test_engine,test_config,test_state}.py`.
**Interfaces:** Consumes `Context/Plan/ChangeSet/*Edit/Receipt/Runner`. Produces `engine.apply(plan: Plan, context: Context, runner: Runner) -> Outcome`, `engine.revert(receipt: Receipt, context: Context, runner: Runner, owners: frozenset[str]) -> Outcome`, `state.load(path: Path) -> Receipt | None`, `state.save(path: Path, receipt: Receipt) -> None`. Config helpers: `jsonfile.patch(content: bytes, pointer: tuple[str | int, ...], value: object, *, remove: bool = False) -> bytes`; `tomlfile.set_tui_key(content: bytes, key: str, value: object) -> bytes`; `zshrc.block(content: bytes, name: str, replacement: str | None) -> bytes`; preference read/write via bounded `defaults` runner.

- [ ] **1. RED:** Add tests `test_cas_refuses_concurrent_edit`, `test_symlink_target_mode_preserved`, `test_second_write_failure_rolls_back_only_own_first_write`, `test_uninstall_preserves_user_changed_value`, `test_unknown_or_corrupt_receipt_is_not_ownership`, `test_multiline_toml_does_not_change_neighbor_values`. Assert rollback leaves concurrently changed bytes intact and reports unresolved resource; private backups 0600; receipt dirs 0700; unrelated parsed TOML identical before/after; unsupported inline/dotted form gives conflict before writes.
Assertions (fixture-local captures):

```python
assert destination.read_bytes() == concurrent_user_bytes
assert stat.S_IMODE(backup.stat().st_mode) == 0o600
assert unrelated_toml_before == unrelated_toml_after
```

- [ ] **2. Verify RED:** `python3 -m unittest tests.test_engine tests.test_config tests.test_state -v`; expected missing engine/helpers.
- [ ] **3. Implement interfaces:** Receipt resource fields exactly `kind,target,locator,before,installed,owners,version`; `before` records existence explicitly. Compare expected bytes/values before apply; stage sibling temp file, preserve target symlink, atomic replace target, private unique backup. Keep private journal until phase complete; recover interrupted transaction before next mutation. Uninstall recomputes address-level inverse against current values, never restores an entire old config over user additions. Runtime payload version swap and MCP registrations use same ownership outcomes, not implicit success.
- [ ] **4. Verify GREEN:** same command; add CLI `install --agent ... --features ... [--dry-run]` and `uninstall --features <csv> [--dry-run]`; integration test selects no implemented features and proves no real HOME writes. JSON report serializes semantic findings, not raw file bodies or exception lines from config.
- [ ] **5. Commit:** scoped new modules/tests, `git commit -m "feat: preserve config ownership with compare-and-swap rollback"`.

## Task 3: Наследуемые профили, clipboard и отдельные hotkeys

**Files:** Create `iterm2_utils/features/{__init__,profiles}.py`, `tests/test_profiles.py`; Modify `planner.py`, `README.md`.
**Interfaces:** Consumes task 1–2. Produces `features.profiles.build(context: Context, selection: Selection) -> ChangeSet`. Own file `DynamicProfiles/iterm2-utils.json`; deterministic UUIDv5 namespace URL + names `iterm2-utils:codex`, `iterm2-utils:claude`. No custom startup command: profile applies to running foreground job; normal shell launch stays inherited.

- [ ] **1. RED:** Tests `test_copy_sequences_exactly_one_command`, `test_hotkeys_only_does_not_disable_copy_on_select`, `test_existing_parent_keyboard_map_preserved`, `test_parent_binding_conflict_requires_choice`, `test_codex_rule_not_applied_to_claude`, `test_custom_codex_profile_override_is_reported`. Assert C/cyrillic bindings keys `0x63`/`0x441`, physical keycode `0x8`, modifier masks `0x40000`/`0x100000`; values `0x03` and `0x1b 0x5b 0x39 0x39 0x3b 0x39 0x75`; no newline/focus action. Parent Keyboard Map copied then merged because profile dictionary inheritance alone may replace it. Custom `[profiles.<name>.tui]` override of copy_on_select is diagnosed; do not claim all Codex invocations read a single setting.
Assertions (fixture-local captures):

```python
assert profile["Bound Hosts"] == ["&codex"]
assert profile["Keyboard Map"]["0x63-0x40000-0x8-0x1"]["Text"] == "0x03"
assert profile["Keyboard Map"]["0x441-0x100000-0x8-0x1"]["Text"] == "0x1b 0x5b 0x39 0x39 0x3b 0x39 0x75"
assert emitted_resume_bytes == b"/resume" + bytes([10])
```

- [ ] **2. Verify RED:** `python3 -m unittest tests.test_profiles -v`; expected missing builder/bindings.
- [ ] **3. Implement builder:** Codex rule `&codex`; Claude hotkeys profile `&claude` with no copy C bindings. Clipboard creates own `CopySelection=false` preference edit + targeted `tui.copy_on_select="never"`. Shortcut mappings: ctrl-v-ru physical `0x9`, char `0x43c`, control, bytes `0x16`; alt-enter physical `0x24`, char `0xd`, alt mask `0x20000`, bytes `0x1b 0x0d`; ctrl-q physical `0xc`, char `0x71`, control, bytes `0x03 0x03`; resume physical `0xf`, char `0x52`, Cmd+Shift mask `0x120000`, send-text `/resume` + actual LF. Verify send-text escaping yields byte `0a`, not backslash+n. Capability mismatch produces finding and keeps that binding uninstalled. Competing APS rules and prevent-APS setting are conflicts, not silently overridden.
- [ ] **4. Verify GREEN:** same unittest command; `test_install_update_uninstall_profile_roundtrip` uses fake preferences and confirms no Default replacement, shared profile retained for remaining shortcuts. Document native Cmd+V and unproven large-text race.
- [ ] **5. Commit:** scoped profile builder/planner/tests/docs, `git commit -m "feat: add selective agent profiles and bilingual Codex copy"`.

## Task 4: Shell integration, стабильный runtime и единая оболочка Codex

**Files:** Create `features/shell.py`, `runtime/codex.zsh`, `vendor/shell_integration/iterm2_shell_integration.zsh`, `vendor/shell_integration/LICENSE`, `sources.lock.json`, `THIRD_PARTY_NOTICES.md`, `tools/check_sources.py`, `tests/{test_shell,test_payload}.py`, `tests/test_codex_shell.zsh`; Modify `planner.py`.
**Interfaces:** Produces `features.shell.build(context: Context, selection: Selection) -> ChangeSet`, `shell.runtime_payload(context: Context, selection: Selection) -> ChangeSet`. Installed entry paths stable under `<data>/current/`; managed block `# >>> iterm2-utils >>>` / matching end. Shared shell enabled when status/notifications/restore requires no-daemon; no-daemon wrapper itself does not imply selected shell-marks feature. Restore later supplies `current/codex_restore/codex-resume.zsh`.

- [ ] **1. RED:** Tests `test_payload_survives_checkout_move`, `test_shell_marks_only_inside_iterm`, `test_existing_integration_is_reused`, `test_no_daemon_once_and_service_subcommands_passthrough`, `test_alias_codex_conflict`, `test_unicode_source_path_is_literal`. Fake Codex records argv: `agents`, `remote-control`, `app-server` receive unchanged arguments; unknown CLI lacking `--no-daemon` passes through for status, while restore capability is unavailable. Explicit existing `--no-daemon` not duplicated. Paths containing apostrophe/space cannot execute commands during source.
Assertions (fixture-local captures):

```python
assert service_argv == ["agents"]
assert interactive_argv.count("--no-daemon") == 1
assert source_checkout_needed is False
```

- [ ] **2. Verify RED:** `python3 -m unittest tests.test_shell tests.test_payload -v`; `/bin/zsh tests/test_codex_shell.zsh`; expected absent shell/payload.
- [ ] **3. Implement interfaces and import pinned script:** use source URL/hash from master plan; import official license headers verbatim. `check_sources.py` verifies SHA-256 lock entries. Source bundled zsh shell integration only for `$TERM_PROGRAM == iTerm.app` and when not already loaded. Detect managed legacy codex blocks rather than wrapping an arbitrary function. Separate `current` runtime copy from checkout and reference the selected Python absolute path; version switch occurs after content validation. Source optional restore wrapper after no-daemon dispatcher to preserve chaining.
- [ ] **4. Verify GREEN:** both commands; `python3 tools/check_sources.py` passes; tests install/uninstall marks while status requires dispatcher and assert dispatcher retained. Use read-only fake app setup only.
- [ ] **5. Commit:** scoped shell/payload/tests/vendor/notices, `git commit -m "feat: package portable shell integration and Codex dispatch"`.
