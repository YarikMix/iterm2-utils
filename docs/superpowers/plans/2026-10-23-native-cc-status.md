# Native cc-status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести принадлежащие iterm2-utils статусы Codex на штатный cc-status, сохранив безопасную адресацию, обратимость установки и отдельные дополнительные функции.

**Architecture:** Существующий установленный Python-hook доставляет проверенные события в cc-status из выбранного iTerm2 bundle; машина видимых состояний принадлежит iTerm2. Минимальный адаптер согласует UUID, фильтрует устаревшие lifecycle события и преобразует input/compact. Notifications и restore продолжают работать отдельными handlers, с прежним receipt/CAS и общим бюджетом.

**Tech Stack:** macOS, zsh, Python 3.11+ stdlib/unittest, iTerm2 3.7.6+ cc-status/it2, текущий transaction engine. Новых Python dependencies и Swift build нет.

**Spec:** [2026-10-23-native-cc-status-design.md](../specs/2026-10-23-native-cc-status-design.md). Исполнитель читает оба документа и исходную спецификацию пакета; этот план не заменяет требования спеки.

## Global Constraints

- Цель: macOS + zsh; installer и Python runtime — Python 3.11+, stdlib.
- Для нового backend Codex нужен iTerm2 **3.7.6 или новее**.
- **Не копируем `cc-status`/`it2` в runtime и не закрепляем их хеш как vendored зависимость.**
- Видимый backend Codex всегда `cc-status`; автоматического fallback к старой машине нет.
- Сохраняется абсолютный бюджет одного Python-hook **2.7 секунды**, внешний timeout **3 секунды**, stdout — ровно `{}` и exit 0 при штатных ошибках.
- В native фазу входят lock и subprocess; её общий лимит **1.8 секунды**, ожидание lock не более **0.4 секунды**, child timeout — оставшееся время этой фазы.
- **Нет `StopFailure`, `Notification` и `PostToolUseFailure`.** Это ограничение Codex 0.163.0, не запрет для отдельного Claude adapter.
- Эта миграция поддерживает обычные локальные панели. При непустом `TMUX` native вызов не делается.
- Автотесты работают только с TemporaryDirectory HOME, fake bundle/runner и искусственными payload. Они не читают настоящие настройки агента/iTerm2.
- В receipts пакет не присваивает себе файлы приложения или штатный symlink iTerm2.
- Нельзя дополнительно установить прямой вызов `cc-status` на то же событие.
- `status: false` гарантирует отсутствие native вызовов.
- Notifications/restore и их shared hooks/runtime сохраняются, если ещё выбраны.
- Реализация начинается после просмотра этих документов пользователем. Ранее выбранный метод — subagent-driven; разработка не меняет рабочую установку автора и не публикует новый release автоматически.

## Review Focus

1. In-place обновление bundle оставляет новый CLI рядом со старым app process: не возвращать Python fallback и не объявлять живую совместимость по одному пути; tests Task 2 и live-check Task 6.
2. Две UUID-переменные противоречат друг другу или TMUX наследует чужую: no-op вместо выбора активной вкладки; tests Task 1/2.
3. При CAS failure миграция выключила legacy, но ещё не установила новый handler: весь status checkpoint откатывается, чужие данные остаются; tests Task 4.
4. После удаления status остаются notifications/restore другого агента: shared config не включает чужие функции и не запускает native; tests Task 3/4.
5. Native умеет `error`, но Codex 0.163.0 не испускает `StopFailure`: нет неизвестных ключей в hooks.json и ложного сообщения об успешной поддержке ошибок; tests Task 1/3/5.

---

## Карта файлов и интерфейсов

Новые файлы:

| Файл | Ответственность |
| --- | --- |
| `runtime/native_status.py` | Подготовка native payload/env, узкий identity guard, ограниченный вызов cc-status |
| `tests/test_native_status.py` | Контракты доставки, преобразований, identity и изоляции subprocess |
| `tests/test_native_status_migration.py` | Обновление beta.1, external reuse/adoption, rollback/uninstall |
| `tests/fixtures/beta1-status.json` | Переносимый снимок ресурсов beta.1 для миграционных тестов, только placeholders |
| `docs/native-status-events.md` | Проверенные версии/commit, события и отличия от native example |

Изменяемые файлы:

- `runtime/events.py`: собственный CODEX_EVENTS, выбор UUID из двух env; нормализованные notification/restore поля сохраняются.
- `runtime/hook.py`: Runner с env/process-group cleanup, native dispatch перед независимыми handlers, общий deadline.
- `iterm2_utils/discovery.py`: native bundle capability, полный/частичный external native inventory, bounded live-read.
- `iterm2_utils/features/status.py`: native settings и одна регистрация hooks, external reuse без второго writer.
- `iterm2_utils/planner.py`, `iterm2_utils/lifecycle.py`: выбор backend/consumers, диагностические findings и атомарная миграция.
- `iterm2_utils/migration.py`: прежний exact legacy adoption для нового backend.
- `tests/support.py`, `tests/test_lifecycle.py`, `tests/test_shell.py`: fake bundle/capabilities; только общие fixtures, без изменения целей прежних tests.
- `tests/test_discovery.py`, `tests/test_status_feature.py`, `tests/test_runtime_events.py`, `tests/test_payload.py`, `tests/test_pending_ui.py`, `tests/test_migration.py`, `tests/test_cli.py`, `tests/test_agent_workflow.py`: затронутые контракты и регрессии.
- `README.md`, `CHANGELOG.md`, `docs/compatibility.md`, `docs/notification-events.md`, `skills/iterm2-setup/references/features.md`, `skills/iterm2-setup/references/troubleshooting.md`, `skills/iterm2-setup/references/ui.md`: установка, новые состояния и честная матрица проверки.
- `tools/check_export.py`, `tests/test_export.py`: явная упаковка новых файлов и smoke из архива.

Не переписывать `runtime/notifier.py`/`claude_notifications.py` и vendor state machine
ради унификации со статусами. Vendored helpers `terminal_id`, `locked`, `read_state`,
`write_state` можно переиспользовать без вызова `transition` для видимого status.
Сохраняются source hashes/лицензии неизменённых файлов. Версия опубликованной beta.1
и tag не переписываются; новый номер release выбирается при отдельной подготовке публикации.

### Согласованные контракты новых функций

```python
# runtime/events.py (существующий Event и normalize сохраняются)
CODEX_EVENTS: tuple[str, ...]  # те же 12 имён из §2 спеки
def terminal_from_environment(environment: dict[str, str]) -> str | None: ...

# iterm2_utils/discovery.py
def native_codex_hook_state(paths: Paths, app: Path) -> str: ...
# Возвращает ровно 'absent', 'complete', 'conflict'; никогда не исполняет hook.

# runtime/native_status.py
def prepare_payload(event: Event, raw: dict) -> dict | None: ...
def prepare_environment(event: Event, environment: dict[str, str]) -> dict[str, str] | None: ...
def forward(event: Event, raw: dict, settings: dict, runner,
            *, environment: dict[str, str], deadline: float) -> str: ...
# deadline — абсолютный monotonic deadline всего hook.
# Результат: 'sent', 'ignored', 'unavailable', 'timeout', 'failed'.
# sent означает только exit0 subprocess, не подтверждение показанного статуса.

# runtime/hook.py
class Runner:
    def run(self, argv: list[str], *, timeout: float,
            stdin: str | None = None, env: dict[str, str] | None = None
            ) -> subprocess.CompletedProcess: ...
# timeout/BaseException убирает process group.
def dispatch(event, settings: dict, runner: Runner, *, restore_metadata=None,
             raw_event: dict | None = None, environment: dict[str, str] | None = None,
             deadline: float | None = None) -> None: ...
```

Runtime settings имеют `status_backend="cc-status"`, `iterm2_app=<absolute bundle>`,
`native_identity_cache=<cache/native-identity>`, прежние `status`/`it2` и независимые
flags/notification_agents. Для external native/legacy reuse `status` нашего handler
равен false; выбор `status` в receipt остаётся true. Inventory хранит только booleans:
`codex-native-status: {enabled: true}` для complete, `{conflict: true}` для conflict.

## Task 1: Зафиксировать доступный native backend и точные события Codex

**Files:** Create `docs/native-status-events.md`; modify `runtime/events.py`, `iterm2_utils/discovery.py`, `tests/support.py`, `tests/test_discovery.py`, `tests/test_runtime_events.py`.

**Interfaces:** Consumes текущие `Paths`/`Context`/`Event`; produces `CODEX_EVENTS`, `terminal_from_environment`, `native_codex_hook_state`, capability `iterm2:cc-status-codex` и boolean external inventory.

- [ ] **Step 1: Добавить failing tests точного контракта и адресации.**

```python
def test_codex_events_match_released_schema(self):
    self.assertEqual(set(events.CODEX_EVENTS), {
        'SessionStart', 'SessionEnd', 'UserPromptSubmit', 'PreToolUse',
        'PermissionRequest', 'PostToolUse', 'PreCompact', 'PostCompact',
        'SubagentStart', 'SubagentStop', 'Stop', 'Interrupt'})
    self.assertEqual(len(events.CODEX_EVENTS), 12)

def test_terminal_environment_conflicts_are_noop(self):
    self.assertEqual(events.terminal_from_environment({'TERM_SESSION_ID': 'w0t0p0:'+UUID}), UUID)
    self.assertEqual(events.terminal_from_environment({'ITERM_SESSION_ID': UUID}), UUID)
    self.assertIsNone(events.terminal_from_environment({
        'ITERM_SESSION_ID': UUID, 'TERM_SESSION_ID': 'w0t0p0:AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'}))
    self.assertIsNone(events.terminal_from_environment({'ITERM_SESSION_ID': 'bad', 'TERM_SESSION_ID': UUID}))
    self.assertIsNone(events.terminal_from_environment({}))
```

Дополнить таблицей: оба согласованы в bare/prefixed формате; пустая присутствующая
переменная не маскируется второй; lower-case UUID нормализуется; UUID с injection
отклоняется. Существующий normalize проверяет несовпадающий payload `terminal_uuid`.

Discovery tests: настоящий fake utilities sibling, bundle 3.7.6/3.7.7 допускается,
3.7.5/unknown/non-executable/missing sibling/missing required help flag не допускаются.
Снимок файлов до/после совпадает, `cc-status` не запускался. External native inventory:
десять native событий без compact + точные tokens `--agent codex` дают complete;
partial/duplicate/другая app/подозрительная shell-обёртка дают conflict; произвольный
обычный чужой hook сохраняется и не объявляется status writer по догадке.

- [ ] **Step 2: Убедиться, что новые tests падают из-за отсутствующих интерфейсов.**

Run: `python3 -m unittest tests.test_discovery tests.test_runtime_events -v`.
Expected: новые tests FAIL/ERROR по отсутствующим names/capabilities, прежние не
заменяются ослабленными assertions.

- [ ] **Step 3: Реализовать контракты и fake bundle.**

`CODEX_EVENTS` определяется в events, старое имя `EVENTS` сохраняется alias для
совместимых import consumers. Не добавлять extras в список регистрации Codex.
`normalize` продолжает понимать Claude-only Notification/StopFailure/PostToolUseFailure.
`terminal_from_environment` валидирует оба присутствующих источника до возврата UUID.
Discovery использует bundle version/executable + read-only `it2 set-status --help`
и шесть флагов §4.1. `native_codex_hook_state` разбирает shlex tokens/группы/матчеры,
сверяет resolved путь с выбранным bundle, не читает содержимое чужих executable.
Штатный symlink допустим только при разрешении в этот bundle. JSON/TOML bodies и
auth/env не попадают в inventory. Записать в docs два commit из спеки и различие
реального Codex enum с iTerm2 example; никаких сетевых запросов во время tests/runtime.

- [ ] **Step 4: Запустить contracts.**

Run: `python3 -m unittest tests.test_discovery tests.test_runtime_events -v`.
Expected: PASS, no live settings/GUI. Временные fixtures поддерживают прежние it2
status probes; не объявлять наличие capability в тех negative tests, где его нет.

- [ ] **Step 5: Зафиксировать только Task 1.**

Run: `git add runtime/events.py iterm2_utils/discovery.py tests/support.py tests/test_discovery.py tests/test_runtime_events.py docs/native-status-events.md`
и `git commit -m "feat: detect native Codex status capabilities"`.
Если на execution действует запрет коммитов/shared worktree, оставить path-scoped
review diff и соблюдать тот запрет; чужие изменения не stage/revert.

## Task 2: Доставка в cc-status с budget, identity guard и cleanup

**Files:** Create `runtime/native_status.py`, `tests/test_native_status.py`; modify `runtime/hook.py`, `tests/test_runtime_events.py`, `tests/test_payload.py`.

**Interfaces:** Consumes Task 1 events/UUID resolver, `Event`, vendor lock/JSON helpers;
produces `prepare_payload`, `prepare_environment`, `forward`, расширенные Runner/dispatch
с сигнатурами из карты. Не меняет notification/restore Event.

- [ ] **Step 1: Добавить failing tests native доставки и отсутствия Python writer.**

Прямой `hook.dispatch` получает TemporaryDirectory settings с fake bundle и
FakeRunner, записывающим argv/stdin/env; `raw_event` — искусственный словарь.
Названия и ключевые assertions:

```python
def test_status_only_uses_one_native_process(self):
    # Arrange fake cc-status + it2, event, settings и canonical environment.
    # Patch vendor status.transition и status_command так, чтобы любой вызов падал.
    hook.dispatch(event, settings, runner, raw_event=raw, environment=environment)
    self.assertEqual(len(runner.calls), 1)
    self.assertEqual(runner.calls[0][0], [str(app/'Contents/Resources/utilities/cc-status'), '--agent', 'codex'])
    self.assertEqual(json.loads(runner.calls[0][2])['hook_event_name'], 'Stop')
    self.assertLessEqual(runner.calls[0][1], 1.8)

def test_input_mapping_contains_no_question(self):
    payload = native_status.prepare_payload(input_event, {'tool_input': {'questions': ['PRIVATE']}})
    self.assertEqual(payload, {'hook_event_name': 'Notification',
                              'notification_type': 'elicitation_dialog', 'message': 'Input needed'})
```

В каждом таком тесте arrange строит Event через `events.normalize` и фиксированные
UUID из `tests/test_runtime_events.py`; `settings` использует §4.2 спеки. Это локальные
test variables, не скрытый helper API. FakeRunner расширяется recording env через
отдельный список, сохраняя прежние `(argv, timeout, stdin)` tuples.

Добавить `test_compact_does_not_send_session_reset`, `test_private_fields_not_persisted`,
`test_conflicting_or_tmux_environment_never_calls_native`, `test_replaced_bundle_binary_is_used`,
`test_late_stop_and_foreign_session_are_ignored`, `test_session_end_blocks_tail_events`,
`test_turn_start_and_stop_are_serialized`, `test_no_native_when_status_disabled`.
Для replacement заменить fake executable на том же пути между двумя вызовами;
для serialization — два threads/fake runner с Event barriers и проверкой порядка
identity admission/native call. Проверить все три преобразования из §4.4.

Ещё до RED добавить process-level tests
`test_native_timeout_kills_child_process_group` и
`test_overall_alarm_kills_child_process_group`: temp Python executable порождает
sleeping child и записывает только его PID. Assert hook process
`(returncode, stdout, stderr) == (0, '{}\n', '')`, elapsed <3 s, PID больше не running,
нет второго запуска. Fixture явно wait/reap-ит свои процессы даже при assertion failure.
Также malformed/oversize stdin, slow settings, failed executable, held lock, native
exit nonzero, отключённый API-noop: никаких настоящих app/сокетов/GUI.
Native failure при наличии оставшегося времени всё ещё допускает mocked notification/
restore handler; исчерпанный общий deadline не продлевается.

- [ ] **Step 2: Зафиксировать RED.**

Run: `python3 -m unittest tests.test_native_status -v`.
Expected: FAIL/ERROR без native_status/API, не успешный silent no-op.

- [ ] **Step 3: Реализовать native adapter и runtime Runner.**

`prepare_payload` создаёт новый allowlisted dict по §4.4, без записи raw и без mutation
исходного raw/Event. `prepare_environment` требует совпадения event UUID с resolver,
отвергает непустой TMUX, возвращает копию env с двумя согласованными prefixed UUID.
`forward` проверяет backend и app-local native pair каждый раз, затем под одним lock
по UUID читает/проверяет/обновляет только session/turn/ended identity и вызывает native.
SessionStart compact не сбрасывает identity. Native state/фоновые агенты не дублируются.
Если identity cache повреждён, текущий ending не допускается без новой SessionStart /
UserPromptSubmit; это конфликт владения, а не повод завершить случайную сессию.

Абсолютный phase deadline — `min(deadline, monotonic()+1.8)`; lock wait ограничен
0.4 s, child получает остаток с резервом 0.15 s на cleanup. Runner использует Popen
без shell, `start_new_session=True`, capture stdout/stderr; при timeout/BaseException
убивает всю группу SIGKILL, дренирует pipes и reap-ит direct child, затем передаёт
ошибку дальше. Резерв входит в 1.8 s, общий SIGALRM остаётся 2.7 s. Не выводить
сырые subprocess streams и не повторять вызов. Missing pair возвращает unavailable.

`main` создаёт absolute deadline до чтений, передаёт raw/env в dispatch, сохраняет
restore_metadata отдельно. Native handler идёт первым, исключения независимых
handlers не прерывают остальных; общий HookBudgetExpired по-прежнему прерывает всё.
Удалить старую visible-status ветку с revision/report locks из hook, а не оставлять
её fallback. Utilities vendor остаются для shared helpers и notifications.

- [ ] **Step 4: Запустить contracts и проверку реальной изоляции fake subprocess.**

Run: `python3 -m unittest tests.test_native_status tests.test_runtime_events tests.test_notifier tests.test_claude_notifications tests.test_payload -v`.
Expected: PASS. После удаления fixture checkout установленный hook вызывает fake
bundle executable, не импортирует checkout и не создаёт старый status-cache JSON.

- [ ] **Step 5: Commit Task 2 path-scoped.**

Run: `git add runtime/native_status.py runtime/hook.py tests/test_native_status.py tests/test_runtime_events.py tests/test_payload.py tests/support.py`
и `git commit -m "feat: delegate Codex tab states to cc-status"`.

## Task 3: Подключение native backend и независимость функций

**Files:** Modify `iterm2_utils/features/status.py`, `iterm2_utils/planner.py`, `iterm2_utils/features/shell.py`, `tests/test_status_feature.py`, `tests/test_lifecycle.py`, `tests/test_shell.py`, `tests/test_selection.py`.

**Interfaces:** Consumes Task 1 capability/inventory, Task 2 runtime settings;
produces pure ChangeSet с одним shared hook command на событие, existing ownership
names `shared:hooks`/`shared:codex-hooks`/`shared:runtime` и точными agent-feature consumers.

- [ ] **Step 1: Добавить failing installer tests.**

```python
def test_native_status_settings_and_allowed_hooks(self):
    result = status.build(context, selection)
    settings = json.loads(next(e.after for e in result.edits if e.path == context.paths.config/'runtime.json'))
    self.assertEqual(settings['status_backend'], 'cc-status')
    self.assertEqual(settings['iterm2_app'], str(context.executables['iterm2']))
    self.assertTrue(settings['status'])
    hooks = json.loads(next(e.after for e in result.edits if e.path == context.paths.codex_home/'hooks.json'))['hooks']
    self.assertEqual(set(hooks), set(events.CODEX_EVENTS))
    self.assertEqual(len(hooks), 12)
    self.assertNotIn('StopFailure', hooks)
    self.assertTrue(all(len(v) == 1 and v[0]['hooks'][0]['timeout'] == 3 for v in hooks.values()))
```

В этом тесте context создаётся `discover(resolve_paths(), f.runner)` внутри
`with Fixture() as f`, selection — Codex/status через текущий Selection.
Добавить table-driven install status-only/notifications-only/restore-only/обе агента
с разными agent_features. Assert settings `status` true только при owned Codex status;
notification_agents строго выбранные, notifications/restore false без выбора,
runtime_payload не содержит app binaries. Повторный install не добавляет второй hook.
Negative capability блокирует только status checkpoint; notifications/restore без
status не требуют cc-status. Foreign complete native reused не создаёт второго writer,
но отдельные notifications/restore получают наши status=false hooks.

- [ ] **Step 2: Run RED.**

Run: `python3 -m unittest tests.test_status_feature tests.test_selection tests.test_lifecycle -v`.
Expected: новые assertions FAIL, прежде чем менять builder.

- [ ] **Step 3: Реализовать конфигурацию через текущие pure builders.**

`status.build(context, selection)` добавляет native settings для owned status,
точные CODEX_EVENTS и прежний hook command. Неизбранная фича не получает flags.
Полный внешний native набор даёт reuse без ownership; `status=false` у нашего
handler, `--no-daemon` wrapper всё равно нужен выбранному Codex status. Legacy reuse
сохраняет прежний путь без второго shell wrapper. В planner два вида reuse
различаются; только legacy reuse убирает статус из runtime_selection как прежде.
Partial/ambiguous native inventory возвращает `native_hook_conflict`, блокирующий
status checkpoint. Не трогать произвольные unrelated hooks.
Consumer maps учитывают каждую agent-feature пару и runtime settings даже при
notifications-only Claude. Claude native UI checkpoint и snapshots сохраняются.
Тестовые Context в LifecycleFixture/ShellFixture получают **fake** bundle version,
executables и native capability; отсутствующие dependencies не маскируются.

- [ ] **Step 4: Run GREEN и существующие shell contracts.**

Run: `python3 -m unittest tests.test_status_feature tests.test_selection tests.test_lifecycle tests.test_shell tests.test_notifications_feature tests.test_restore_feature tests.test_pending_ui -v`.
Run: `/bin/zsh tests/test_codex_shell.zsh` и `/bin/zsh tests/restore/test_codex.zsh`.
Expected: PASS; no-daemon exclusions после глобальных options сохранены, чужие
alias/functions по-прежнему conflict; Claude status не пишет Codex config.

- [ ] **Step 5: Commit Task 3 path-scoped.**

Run: `git add iterm2_utils/features/status.py iterm2_utils/planner.py iterm2_utils/features/shell.py tests/test_status_feature.py tests/test_lifecycle.py tests/test_shell.py tests/test_selection.py`
и `git commit -m "feat: install native status without enabling other features"`.

## Task 4: Безопасная миграция beta.1 и selective uninstall

**Files:** Create `tests/test_native_status_migration.py`, `tests/fixtures/beta1-status.json`; modify `iterm2_utils/migration.py`, `iterm2_utils/lifecycle.py`, `tests/test_migration.py`, `tests/test_pending_ui.py`.

**Interfaces:** Consumes Tasks 1–3 pure plan/runtime contract; produces beta.1-compatible
update через существующие `lifecycle.update/install/uninstall` без новой схемы receipts.
`state.VERSION` остаётся `'1'`; новый metadata flag не даёт ownership чужих hooks.

- [ ] **Step 1: Создать переносимый beta.1 fixture и failing migration tests.**

Снимок взять из поведения исходного commit `8c5643ed574f016bca46952ae6cd804d09195580`
в отдельном **временном** source tree с fake HOME, не из настоящего receipt автора.
Нормализовать temp paths placeholders и сохранить JSON с receipt и содержимым
подконтрольных файлов; loader заменяет placeholders на текущий temp root.
Tests/архив не требуют git, сети или присутствия исходного commit.
Проверить `state.validate(receipt)` до использования и сохранить hash fixture.

Обязательные tests и assertions:

- `test_beta1_update_is_native_and_preserves_selection`: после update
  `status_backend == 'cc-status'`, число owned commands остаётся 12, independent
  agent_features/shortcuts неизменны; старые cache записи не считаются native identity.
- `test_beta1_cas_conflict_preserves_previous_installation`: чужой edit hook или
  settings вызывает conflict, старые current/settings/receipt/foreign edit сохранены.
- `test_adoption_write_failure_restores_legacy_writer`: injected `_write_file` failure
  на runtime settings/hook после выключения plugin возвращает `enabled=true`, старые
  shell/hooks/current и receipt; ошибка не оставляет два writer или ни одного.
- `test_uninstall_status_preserves_other_consumers`: notifications/restore и Claude
  выбор остаются; runtime hook больше не вызывает native; обратное удаление notifications
  сохраняет native status. Полный uninstall удаляет только owned entries.
- `test_external_native_reuse_survives_uninstall`: external десять entries остались
  побайтно как были, package не владеет app/symlink; partial/duplicate native остаются
  conflict без файловых изменений.
- `test_legacy_restore_and_status_adopt_atomically`: прежние exact managed blocks
  и restore hooks мигрируют одной группой и условно восстанавливаются при uninstall.

- [ ] **Step 2: Run RED.**

Run: `python3 -m unittest tests.test_native_status_migration tests.test_migration -v`.
Expected: новый сценарий legacy/native update воспроизводит расхождение, а не
падает из-за невалидного искусственного receipt. Подтвердить, что beta.1 fixture
сам по себе валиден независимо от нового installer.

- [ ] **Step 3: Реализовать миграцию в существующих lifecycle checkpoints.**

Не вводить shell migration script. Использовать `engine.apply`/CAS и consumers:
выключение legacy plugin, замена runtime/current, settings и hooks — один status
checkpoint; inverse сохранён в receipt. Для valid owned beta.1 update не нужен
`--adopt-legacy`; external legacy требует этот флаг как раньше. Не удалять repositories,
plugin cache, backups или conversation files. Согласовать `_context` refresh с новым
native inventory, а reuse native не считать собственным hook лишь из-за совпадения пути.
Если engine уже выполняет нужное атомарно, production engine не менять: тест фиксирует
существующее свойство. Partial uninstall recomposes shared settings в той же операции,
где исчезает writer/восстанавливается legacy. Foreign changes дают conflict до этого.

- [ ] **Step 4: Run GREEN, включая Claude UI ownership.**

Run: `python3 -m unittest tests.test_native_status_migration tests.test_migration tests.test_lifecycle tests.test_pending_ui tests.test_engine tests.test_state -v`.
Expected: PASS; prior native Claude hooks остаются внешними, duplicate snapshot
по-прежнему pending; до/после fault injection разрешены только наши durable backups/
journal, но не повреждённые live addresses.

- [ ] **Step 5: Commit Task 4 path-scoped.**

Run: `git add tests/test_native_status_migration.py tests/fixtures/beta1-status.json iterm2_utils/migration.py iterm2_utils/lifecycle.py tests/test_migration.py tests/test_pending_ui.py`
и `git commit -m "feat: migrate owned status installs with reversible native setup"`.

## Task 5: Doctor, инструкции и границы поддержки error

**Files:** Modify `iterm2_utils/discovery.py`, `iterm2_utils/lifecycle.py`, `iterm2_utils/planner.py`, `tests/test_discovery.py`, `tests/test_status_feature.py`, `tests/test_cli.py`, `tests/test_agent_workflow.py`, `README.md`, `CHANGELOG.md`, `docs/compatibility.md`, `docs/notification-events.md`, `skills/iterm2-setup/references/features.md`, `skills/iterm2-setup/references/troubleshooting.md`, `skills/iterm2-setup/references/ui.md`.

**Interfaces:** Consumes native inventory/settings from Tasks 1–4; produces bounded
Findings `status_backend`, `native_status_capability`, `codex_error_event`,
`status_api`, без нового CLI-флага. Для error-source limitation используется
неблокирующий `state='limited'`, одинаково для known missing и unknown version с
разными явными messages; ready всего API не означает ready error-source.

- [ ] **Step 1: Добавить failing doctor/CLI tests.**

```python
def test_live_status_accepts_native_terminal_states(self):
    for state in ('', 'idle', 'working', 'waiting', 'done', 'error'):
        runner.responses['it2'] = json.dumps({'status': state, 'detail': 'PRIVATE'})
        findings = live_status(context, runner, selection)
        self.assertEqual(next(f for f in findings if f.code == 'status_api').state, 'ready')
        self.assertNotIn('PRIVATE', repr(findings))

def test_codex_0163_reports_error_source_limitation(self):
    findings = lifecycle.doctor(context, receipt, runner)
    limitation = next(f for f in findings if f.code == 'codex_error_event')
    self.assertEqual(limitation.state, 'limited')
    self.assertIn('StopFailure', limitation.message)
    self.assertIn('0.163.0', limitation.message)
```

Arranges используют Fixture/valid installed receipt и явный UUID env. CLI tests
assert limitation остаётся в doctor JSON (не теряется при filtering findings),
не вызывает exit2; corrupted native settings/missing pair дают exit2, pending trust/
new-session остаются exit3. Для unknown Codex версия ошибки явно unverified и нет
регистрации StopFailure. Native/external native/legacy backend различаются без raw
command bodies. `doctor --live` вызывает только bounded get-status конкретного UUID,
никогда set-status/cc-status и не открывает UI. Invalid returned status не ready.

- [ ] **Step 2: Run RED.**

Run: `python3 -m unittest tests.test_status_feature tests.test_discovery tests.test_cli -v`.
Expected: FAIL новых native states/limitation assertions на прежнем doctor.

- [ ] **Step 3: Реализовать read-only findings и обновить инструкции.**

`live_status` использует Task 1 UUID resolver и расширенный status allowlist;
inventory/capability/backend/limitations передаются через `lifecycle.doctor` без
потери новых не-blocking Findings. Ready установленных файлов/exit0 native не
считаются доказательством event delivery. При конфликтующем env/TMUX live target
не угадывается; finding сообщает ограничение.
В references описать установку selected native Codex, legacy reuse vs `--adopt-legacy`,
новую сессию/trust и отсутствие готового штатного Codex installer. Для Claude оставить
штатное меню и ограничения Workgroup/Auto-Enter. README/changelog не называют
ошибки Codex 0.163.0 поддержанными, notifications document отделяет старый notification
transition от теперь native status; compatibility перечисляет source/fixture/live
доказательства раздельно. Не переписывать существующий setup skill ради нового
workflow и не добавлять лишние подтверждения уже выбранной настройки.

- [ ] **Step 4: Run GREEN и structural skill check.**

Run: `python3 -m unittest tests.test_status_feature tests.test_discovery tests.test_cli tests.test_agent_workflow -v`.
Run: `python3 tools/check_skill.py`.
Expected: PASS. Structural проверка не называется независимой проверкой поведения
агента; если fresh-model eval недоступен, так и остаётся в compatibility.

- [ ] **Step 5: Commit Task 5 path-scoped.**

Commit перечисленные Files с message `docs: explain native status setup and Codex error limits`;
перед add сверить status и stage только эту задачу, без `git add -A`.

## Task 6: Упаковка, полная проверка и отдельная живая приёмка

**Files:** Modify `tools/check_export.py`, `tests/test_export.py`, `docs/compatibility.md`; при необходимости точечно `tests/test_payload.py`. CI workflow сохраняется, поскольку уже запускает нужные suites на Linux/macOS × Python 3.11/current.

**Interfaces:** Consumes весь новый runtime/install contract; produces проверенный
export allowlist и актуальную матрицу фактических проверок. Не создаёт GitHub tag/release.

- [ ] **Step 1: Добавить failing export smoke из распакованного архива.**

Assert `runtime/native_status.py`, новые tests, beta.1 fixture и
`docs/native-status-events.md` входят в EXPORT_FILES/архив; ровно один экземпляр
каждого пути. Отсутствуют app binaries, реальные receipts/settings, raw payload и
private references. Fixture archive тест ставит status, удаляет source checkout,
вызывает installed hook с fake bundle и видит native invocation. Native subprocess
не ищет ничего в checkout/PATH. Смена fixture native executable на месте применяется
без повторного копирования payload. Проверить source/attribution обоих сохранённых
vendor status файлов: они по-прежнему нужны notifications/helpers.

- [ ] **Step 2: Run RED.**

Run: `python3 -m unittest tests.test_export -v`.
Expected: новый allowlist/archive assertion FAIL до правки списка.

- [ ] **Step 3: Обновить явный allowlist и smoke.**

Добавить только новые согласованные runtime/docs/tests/fixture paths. Не применять
recursive auto-export и не добавлять app utilities в sources.lock. Не менять хеши
нетронутого vendor кода. Если всё же потребовалась адаптация pinned файла — записать
новый sha256 и transformation в lock при сохранённом upstream hash, а не отключать
проверку. Development spec/plan остаются в repo, не обязаны входить в release archive.

- [ ] **Step 4: Полная локальная проверка.**

Run последовательно:

```sh
python3 -m unittest discover -s tests -t . -v
/bin/zsh tests/test_codex_shell.zsh
/bin/zsh tests/restore/test_codex.zsh
python3 tools/check_sources.py
python3 tools/check_skill.py
python3 tools/check_export.py
python3 tools/build_release.py --destination dist
```

Expected: все tests PASS, все source hashes/skill/export checks PASS, архив и
basename-only checksum созданы и smoke-tested. Записать фактические количества tests,
версии Python/zsh/ОС и SHA проверенного code snapshot; старые beta.1 counts не
копировать как новые. Не запускать широкий повторный прогон после этих checks без
нового изменения/падения. CI/живую приёмку не считать выполненными локальными tests.

- [ ] **Step 5: Выполнить или честно отметить изолированную live-матрицу.**

Перед собственным окном предупредить пользователя. Использовать отдельный разрешённый
контур настроек/учётную запись Mac; не подменять реальные author HOME/settings и не
обходить UI/TCC. Если контура нет — записать live-unverified и не запускать проверки
на существующих разговорах. Каждая проверка адресует только свою тестовую вкладку.

| Проверка | Что доказывает |
| --- | --- |
| Native синтетические start/prompt/stop/interrupt/StopFailure | Реальный renderer working/done/idle/error; не источник Codex error |
| Настоящий Codex 0.163.0: prompt, tool, permission, input, Esc, compact | Какие события действительно испускаются и как работают три преобразования |
| Две панели/две сессии, переключение активной вкладки во время ответа | Explicit UUID, отсутствие status в соседней вкладке |
| Parallel/detached subagents и main Stop | Штатный учёт фоновой работы и отсутствие раннего done |
| Native Claude на записанной версии + notifications отдельно | Нет второго writer/двойных banners и false completion |
| API off / native unavailable / bundle updated | Безопасная деградация, doctor различает setup/API/event delivery |

Не генерировать ошибку агента удалением auth или изменением настоящего API endpoint.
Отсутствие StopFailure в Codex 0.163.0 отмечается unsupported source, даже когда
синтетический renderer error успешно проверен. Native особенности parallel waiting
и окончания фоновых задач после ошибки фиксируются без локального status fallback.

- [ ] **Step 6: Commit Task 6 path-scoped.**

Commit Task 6 files path-scoped с message `test: verify native status export and acceptance boundaries`.

- [ ] **Step 7: Финальное ревью реализации по спецификации.**

Исполнить финальное review по **спеке**, а не только по task checklist; сверить
все пять Review Focus и original invariants. Реализацию нельзя объявлять завершённой
с потерянными обязательными fixture checks; live gaps явно раскрываются. Публикацию
и миграцию рабочей установки автора этим шагом не выполнять.

## Самопроверка плана перед передачей

- §1/§3/§8 спеки покрыты Tasks 2–3/5: native UI policy и сохранённые независимые функции.
- §2 и error limitation — Tasks 1/3/5/6: enum pinned, отсутствие invalid hook keys,
  synthetic renderer отделён от реального источника.
- §4.1 — Tasks 1/2/6: bundle capability, lookup на каждом событии, без vendoring.
- §4.2–4.5 — Tasks 1/2/3: единый writer, payload, UUID/identity, deadline/process cleanup.
- §5 — Tasks 3/4: external reuse, beta.1 update, ownership, rollback, selective uninstall.
- §6 — Task 5: read-only doctor, не-blocking limitation, версии и инструкции.
- §7 — все Task test steps и Task 6: fake fixtures, archive independence, zsh/live matrix.
- Все пять Review Focus имеют названные tests; новые runtime сигнатуры определены
  один раз в карте, поздние задачи используют их, не вводя альтернативные имена.
- Спека проверена свежим builder-check; существенных вопросов не осталось. План
  проверен автором по покрытию, типам/сигнатурам, гранулярности и соотношению со спекой.

## Перед исполнением

Пользователь просматривает спеку и план. После подтверждения используем ранее
выбранный `superpowers:subagent-driven-development`, создаём execution worktree через
`superpowers:using-git-worktrees` и проверяем его AGENTS.md. Каждый implementer получает
свои Files/Interfaces, оба документа и указание, что он не один в codebase и не должен
отменять чужие изменения. До этого — только документация.
