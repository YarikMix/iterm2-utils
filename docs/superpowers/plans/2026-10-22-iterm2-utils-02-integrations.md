# iterm2-utils: Runtime Integrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить статусы, уведомления обоих агентов, восстановление Codex и выбираемый MCP в работающую основу части I.
**Architecture:** Builders используют ChangeSet из части I; один установленный hook dispatcher включает только выбранные обработчики. Native Claude status остаётся отдельной штатной интеграцией iTerm2; наши уведомления не дублируют её статусные hooks.
**Tech Stack:** Python 3.11+ stdlib/unittest, zsh, iTerm2 it2, native cc-status, terminal-notifier, fzf 0.60+, uvx.
**Spec:** [Спецификация](../specs/2026-10-22-iterm2-utils-design.md); [общий порядок](2026-10-22-iterm2-utils.md); обязательные типы и Runner — [часть I](2026-10-22-iterm2-utils-01-core.md).

## Global Constraints

- «Hooks адресуют явный UUID вкладки»; никогда не подставлять активную вкладку.
- «Не меняют разрешения инструментов и не сохраняют prompts, команды или их вывод».
- `mcp-server-iterm2==0.1.1` с `mcp<2`; отдельная выбираемая фича.
- «Для Claude Code используется штатная интеграция iTerm2 с `cc-status` и её штатным установщиком».
- «Сам разговоры не запускает, пока человек не подтвердил выбор»; restore только Codex.
- «При неизвестном исходе открытия вкладки не повторяет запуск вслепую».
- Runtime не зависит от checkout и корпоративных сервисов; источник и версия каждого перенесённого компонента фиксируются.

## Review Focus

1. PermissionRequest перед auto-review — нет ложного permission-баннера: задача 6.
2. Повторный Stop, новый prompt и поздний hook прошлого turn — не дублировать/не перепутать уведомления: задача 5–6.
3. Вкладка закрылась/UUID неизвестен/доступ к Automation отсутствует — no-op, без active fallback: задача 6.
4. Timeout после создания вкладки restore — резервирование сохраняется, второй запуск не создаётся: задача 7.
5. Notifications-only и одновременно установленный чужой MCP/status plugin — фичи независимы, конфликт не перезаписывает чужой сервер: задача 5, 8.

---

## Task 5: Переносимый status runtime и штатные статусы Claude

**Files:** Create `features/status.py`, `runtime/{hook,events}.py`, `vendor/codex_status/{status,iterm_support}.py`, `vendor/codex_status/LICENSE`, `tests/{test_status_feature,test_runtime_events}.py`; Modify `sources.lock.json`, `THIRD_PARTY_NOTICES.md`, `planner.py`.
**Interfaces:** Consumes common `Context/Selection/ChangeSet/Runner` and shell payload. Produces `features.status.build(context: Context, selection: Selection) -> ChangeSet`; `runtime.events.Event(agent: str, name: str, session_id: str, terminal_uuid: str, turn_key: str | None, tool_name: str | None, notification_type: str | None, background_running: bool)`; `normalize(raw: dict, agent: str, terminal_env: str | None) -> Event | None`; `runtime.hook.dispatch(event: Event, settings: dict, runner: Runner) -> None`; `runtime.hook.main(argv: list[str]) -> int`. Raw JSON processed in memory, not persisted. Hook dispatch references event-only whitelisted fields, never transcript file.

- [ ] **1. RED:** Tests `test_wrong_uuid_is_noop`, `test_late_stop_does_not_idle_new_turn`, `test_notifications_only_does_not_call_set_status`, `test_all_hook_failures_return_empty_json_zero`, `test_claude_status_is_pending_native_ui_without_workgroup`, `test_existing_status_is_reused`. Assert no new status hooks when external matching plugin already enabled; statuses working/waiting/idle target only supplied UUID; notification/restore disabled flags invoke neither handler. Wrong/malformed UUID means zero `it2` calls. Every hook failure prints `{}` and returns 0 in <=3s budget.
Assertions (fixture-local captures):

```python
assert status_calls_for_notifications_only == []
assert status_calls_for_unknown_uuid == []
assert hook_stdout == "{}" + chr(10)
assert hook_exit == 0
```

- [ ] **2. Verify RED:** `python3 -m unittest tests.test_status_feature tests.test_runtime_events -v`; expected missing runtime/builders.
- [ ] **3. Implement dispatcher and port status transition:** Import publicly accessible pinned base from master plan, retain license and upstream transition test vectors; add owned-runtime settings adapter so no external plugin config/env is required. Codex events: SessionStart, UserPromptSubmit, PreToolUse, PermissionRequest, PostToolUse, PreCompact, PostCompact, SubagentStart, SubagentStop, Stop, Interrupt, SessionEnd; one exact own command per event with timeout 3s. Native Claude status becomes UiStep to `iTerm2 > Install/Reinstall Claude Code Integration`, choosing only API/hook/Session Status; no Workgroup/Auto-Enter checkbox. Doctor afterwards identifies cc-status hook without displaying other settings. Bootstrap does not silently invoke an entire native installer as though all its optional steps were selected.
- [ ] **4. Verify GREEN:** same command plus imported status behavioral tests. Existing Codex wrapper uses task 4 no-daemon dispatcher; target lacking support reports capability separately. `doctor --live --json` checks status/API reachability with bounded read-only command and returns pending UI if access missing. Do not create probe tabs here.
- [ ] **5. Commit:** scoped runtime/status/vendor/tests/lock, `git commit -m "feat: integrate explicit-session Codex and native Claude status"`.

## Task 6: Уведомления с точным событием и переходом в свою вкладку

**Files:** Create `features/notifications.py`, `runtime/{notifier,claude_notifications,focus}.py`, `tests/{test_notifications_feature,test_notifier,test_claude_notifications}.py`, `docs/notification-events.md`; Modify `runtime/{hook,events}.py` and `config/tomlfile.py` through owner of common files.
**Interfaces:** Consumes `Event`, `Runner`, `Receipt`, status transition, fake clock. Produces `features.notifications.build(context: Context, selection: Selection) -> ChangeSet`; `notifier.Notice(agent: str, terminal_uuid: str, session_id: str, token: str, kind: str)`; `notifier.transition(previous: dict, event: Event) -> tuple[dict, Notice | None]`; `notifier.deliver(notice: Notice, context: Context, runner: Runner) -> bool`; `focus.focus(terminal_uuid: str, it2: Path, runner: Runner) -> bool`. Callbacks only absolute quoted argv; no payload interpolated into AppleScript source.

- [ ] **1. RED:** `test_codex_permission_request_never_sends_custom_banner`, `test_native_approval_policy_is_targeted_and_reversible`, `test_claude_stop_once_per_prompt`, `test_claude_interrupt_session_end_and_stop_failure_do_not_complete`, `test_claude_permission_notification_is_not_permission_decision`, `test_focus_unknown_and_closed_tab_do_nothing`, `test_foreground_tab_suppresses_banner`, `test_notification_only_never_sets_status`, `test_notifier_timeout_does_not_hang_hook`. Assert duplicate Stop sends once; new UserPromptSubmit allows next completion; unrelated env/JSON fields absent from cache; no fallback activation when exact UUID lookup fails.
Assertions (fixture-local captures):

```python
assert codex_permission_hook_banners == []
assert len(claude_banners_for_duplicate_stop) == 1
assert banners_for_interruption_or_unknown_target == []
assert persisted_keys.isdisjoint({"last_assistant_message", "tool_input", "prompt"})
```

- [ ] **2. Verify RED:** `python3 -m unittest tests.test_notifications_feature tests.test_notifier tests.test_claude_notifications -v`; expected missing adapter.
- [ ] **3. Implement exact mapping:** Codex custom kinds only input (`PreToolUse` for `request_user_input`/`request_user_input_async`) and complete (confirmed main Stop followed by idle, retaining upstream pending work semantics). Codex permission banners rely on native `tui.notifications = ["approval-requested"]`; preserve/restore prior setting via task 2, validate support before writing. Do not reintroduce banners from PermissionRequest: installed newer snapshot deliberately removed them due auto-review. Claude hook registration: SessionStart/UserPromptSubmit reset turn; Notification matcher `permission_prompt|idle_prompt|elicitation_dialog|elicitation_url_dialog` maps attention; main Stop maps complete; SessionEnd clears, not completes. StopFailure/SubagentStop do not produce completion. Use `prompt_id` when present, fallback counter advanced only by UserPromptSubmit; `stop_hook_active` and duplicate Stop cannot create repeated notices. When Stop reports active background_tasks, suppress completion until a later main Stop confirms no active background work; do not invent a completion on arbitrary subagent events. Official source read at planning: `https://code.claude.com/docs/en/hooks.md` (Stop does not run on user interrupt; API failure is StopFailure; Notification exposes notification_type). Cache retains only IDs/state/token/timestamps, not last_assistant_message or tool payload.
- [ ] **4. Verify GREEN:** all three tests; target terminal-notifier discovered dynamically, Python/notifier prerequisites affect only notifications. Claim token before asynchronous delivery; helper lifetime <=10s, no unbounded daemon. Unknown focus/Automation permission skips banner rather than stealing focus. Record policy/older-version limitations in `docs/notification-events.md`; do not mark live banners verified yet.
- [ ] **5. Commit:** scoped files/tests, `git commit -m "feat: add deduplicated agent notifications without false approval banners"`.

## Task 7: Порт восстановления Codex без связи с исходным checkout

**Files:** Create `features/restore.py`, `runtime/codex_restore/{codex-sessions,codex-resume.zsh,codexlib/}`, `tests/restore/` (перенесённые исходные тесты), `tests/test_restore_feature.py`; Modify dispatcher, notices/lock.
**Interfaces:** Consumes common models/engine and stable shell dispatcher. Produces `features.restore.build(context: Context, selection: Selection) -> ChangeSet`. Preserve existing `codexlib.cli.main(argv: list[str]) -> int`, `ITerm.panes() -> list[Pane]`, `restore.choices(paths: Paths, client: ITerm, auto: bool, now: float) -> tuple[list[Choice], list[str]]`, `restore.prepare(paths: Paths, client: ITerm, selected_ids: list[str], caller_terminal: str, now: float) -> FirstResume | None` contract and argv protocol from source module; internal restore `Paths` is distinct from setup `models.Paths`, do not interchange them. Hook dispatcher forwards original in-memory event to restore only when enabled.

- [ ] **1. RED:** Port existing source tests unchanged first; add `test_installed_restore_survives_checkout_move`, `test_other_codex_home_is_preserved`, `test_no_automatic_launch_before_fzf_confirmation`, `test_unknown_new_tab_outcome_is_not_retried`, `test_restore_only_uses_no_daemon_without_status`, `test_claude_only_restore_is_unavailable`. Verify current pane first, others selected in saved order/cwd, nonexistent cwd and already-open IDs skipped, background helpers excluded, all metadata files 0600, cache retained on uninstall.
Assertions (fixture-local captures):

```python
assert new_tab_calls_after_uncertain_result == 1
assert selected_codex_home == expected_codex_home
assert launched_before_confirmation == []
```

- [ ] **2. Verify RED:** `python3 -m unittest discover -s tests/restore -t . -v` and `python3 -m unittest tests.test_restore_feature -v`; `/bin/zsh tests/restore/test_codex.zsh`. Source standalone tests can pass baseline; new payload/dispatcher tests must fail before integration.
- [ ] **3. Port only module and tests:** Source subtree `tools/codex-resume` at commit `15f225cb4ac15abb7f95f87cbddc7406ba0ba7f9` in the existing agent-utils checkout. Do not copy any other repo files or publish that checkout's configs. Preserve authorship/provenance in notices; package all required modules locally. Adapt default it2/app paths to Context-selected install instead of `/Applications` literals; preserve explicit CODEX_HOME, no-auto env flag and `resume --all`. Own register/finish/claim operations keep source behavior and timeouts. Replace source installer with common builder, leaving runtime protocol intact. Feature detects fzf>=0.60 and no-daemon capability; does not silently skip restoration when prerequisites fail.
- [ ] **4. Verify GREEN:** same three commands; import/path scan confirms source checkout not required. Fake-it2 acceptance asserts that unknown tab creation dispatch reserves request and reports inspection instructions; no automatic retry or working-session kill.
- [ ] **5. Commit:** scoped restore/runtime/tests/notices, `git commit -m "feat: bundle portable selected Codex session restoration"`.

## Task 8: MCP-регистрация в выбранном агенте

**Files:** Create `features/mcp.py`, `config/mcp.py`, `tests/test_mcp.py`; Modify engine RegistrationEdit adapter, planner, README.
**Interfaces:** Consumes `RegistrationEdit/Runner/Context`. Produces `features.mcp.build(context: Context, selection: Selection) -> ChangeSet`; `config.mcp.inspect(agent: str, name: str, context: Context, runner: Runner) -> dict | None`; `config.mcp.apply(edit: RegistrationEdit, context: Context, runner: Runner) -> None`; `config.mcp.probe(context: Context, runner: Runner, agent: str) -> Finding`.

- [ ] **1. RED:** Tests `test_pinned_server_argv`, `test_foreign_same_name_is_not_overwritten`, `test_disabled_or_other_scope_server_is_a_conflict`, `test_claude_only_does_not_edit_codex`, `test_installed_process_without_connection_is_not_ready`, `test_timeout_after_add_is_reconciled_not_repeated`, `test_python_api_dependency_does_not_enable_mcp_for_status`. Assert exact args `uvx --with mcp<2 mcp-server-iterm2==0.1.1`; nonselected agent gets no CLI calls; unrelated secret config fields absent from diagnostics/receipts.
Assertions (fixture-local captures):

```python
assert edit.after["command"] == "uvx"
assert edit.after["args"] == ["--with", "mcp<2", "mcp-server-iterm2==0.1.1"]
assert writes_for_nonselected_agent == []
```

- [ ] **2. Verify RED:** `python3 -m unittest tests.test_mcp -v`; expected missing config adapter.
- [ ] **3. Implement RegistrationEdit:** Use supported agent CLI (`codex mcp add iterm2-observe -- ...`; `claude mcp add --transport stdio --scope user iterm2-observe -- ...`) after help/capability check, not overwriting whole config. Registration name `iterm2-observe`; existing exact managed definition reused; foreign/disabled same-name registration remains untouched and produces conflict. Rollback/removal compares observed config against owned definition before invoking remove. Never log raw `mcp get` output or env values. No API server token/auth changes; Python API requiring confirmation is pending UI. Tool-set policy must remain limited to observation and metadata; if chosen package version exposes arbitrary execute/write-input tool, stop with incompatibility instead of silently broadening access.
- [ ] **4. Verify GREEN:** same command; live probe checks list sessions through actual protocol, not merely process existence; protocol failures remain unavailable, no shell command sent to user terminal. Document agent-specific registration location/restart requirement in README.
- [ ] **5. Commit:** scoped adapter/tests/docs, `git commit -m "feat: configure pinned optional iTerm MCP for either agent"`.
