# Repo appearance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переиспользуемая opt-in функция `appearance`: цвет и составная иконка вкладки по папке запуска shell/Codex.

**Architecture:** Использовать существующие selection, ChangeSet/engine, receipts/CAS и versioned runtime. Локальный JSON содержит правила, короткоживущий Python helper меняет только свойства собственной сессии через официальный API iTerm2; существующий dispatcher вызывает его без второго wrapper или agent hooks.

**Tech Stack:** macOS, zsh, Python 3.11+, стандартная библиотека, официальный модуль `iterm2` только для живого API, unittest/fake adapters, готовые PNG.

**Spec:** [Согласованная спецификация](../specs/2026-11-01-repo-appearance-design.md). Исполнитель читает оба документа.

## Global Constraints

- База worktree — `origin/main` `24789a8e861cc676982cc4990ba7bce7a3b6cf46`, ветка `feat/repo-appearance`.
- Первая версия — macOS/zsh, Python 3.11+, Codex-only feature `appearance`; Claude не подключать.
- Назначение при запуске интерактивной shell и интерактивного Codex, включая resume/fork; обычный `cd` не запускает назначение.
- Физический `$PWD` вызывающей shell; нет совпадения — нет изменения текущего оформления. Не извлекать путь из разговора или аргументов `--cd`.
- Сохранить общий dispatcher, restore, `--no-daemon`, аргументы, код выхода, статусы, clipboard и настройки других агентов.
- Только валидная собственная сессия через `runtime.events.terminal_from_environment`; конфликтующие ID отклонять, active-tab fallback отсутствует.
- Менять только сессионные цвет/использование цвета и custom icon/mode; Default, целый профиль и заголовок не менять.
- Без daemon, постоянных таймеров/наблюдателей, MCP, agent hooks, pip и скачивания картинок при shell startup.
- `plan`/dry-run ничего не пишут, не запускают GUI/API/пользовательскую shell. Builders возвращают ChangeSet.
- Разработка и fixture-тесты не читают/не меняют настоящие agent/iTerm settings; использовать TemporaryDirectory HOME/Paths и fake Runner/API.
- Личные пути, конфиги и receipts не публиковать. Runtime и icons работают без checkout/исходного JSON/PNG.
- При работе по Superpowers SDD сохраняй обязательные этапы, артефакты, согласования, тестирование и ревью. Ponytail применяй для выбора простейшей реализации, полностью выполняющей согласованную спецификацию. Упрощение не должно сокращать требования или обходить этапы SDD.
- Не коммитить между задачами. Сохранять проверяемый diff и результаты; публикацию оформлять после итогового review, без изменения основного checkout.

## Review Focus

1. Пробелы, Unicode, кавычки и `$()` в путях остаются данными; нет исполнения команд — задачи 1 и 3.
2. SSD отсутствует при установке/запуске/обновлении: не создавать каталог, не искать fallback, не мешать Codex — задачи 1 и 4.
3. APS на входе/выходе Codex и быстрый следующий запуск: поздний helper не перекрашивает новую сессию/новое назначение — задачи 2 и 3.
4. Частичный uninstall сохраняет shared shell/runtime и чужие edits; update не требует удалённый source JSON/PNG — задача 4.
5. Модуль `iterm2` есть в другом Python, но не в выбранном, либо API не разрешён: не выдавать готовность и не зависать — задачи 2 и 4.

## Карта изменений и договорённости

| Файлы | Ответственность |
|---|---|
| `runtime/appearance.py` (новый) | Общие чтение/валидация правил, выбор корня, lazy API adapter и внутренний CLI helper |
| `runtime/appearance.zsh` (новый), `runtime/codex.zsh` | Однократный shell startup, запуск и завершение Codex без нового wrapper |
| `runtime/assets/appearance/` (новый) | Готовые PNG и исходные SVG символов; attribution в `THIRD_PARTY_NOTICES.md` |
| `iterm2_utils/features/appearance.py` (новый) | Pure builder локального JSON и копий пользовательских PNG |
| `models.py`, `planner.py`, `cli.py`, `discovery.py`, `lifecycle.py`, `features/shell.py` внутри `iterm2_utils/` | Выбор функции, ephemeral input, prerequisites, checkpoints/CAS, doctor и runtime consumers |
| `tools/check_export.py`, `tools/check_skill.py`, `tests/test_payload.py`, `tests/test_export.py` | Явная поставка runtime/assets и проверки установки без checkout |
| `README.md`, `CHANGELOG.md`, `docs/compatibility.md`, `skills/iterm2-setup/` | Настройка коллегой, пример JSON, ограничения и фактическая live-матрица |

Решения исполнителя для единообразия интерфейсов:

- Вход JSON: `{"projects": [{"root": "/path/to/repo", "color": "#65A85A", "icon": "android-mail"}]}`. Корневое поле только `projects`; правило содержит ровно `root`, `color`, `icon`; список непустой.
- Встроенные имена: `ios`, `android`, `kotlett`, `ios-mail`, `ios-cloud`, `android-mail`, `android-cloud`. Прозрачные готовые PNG, простые оригинальные SVG того же назначения; никаких генераторов при установке.
- Установленный JSON — `context.paths.config / 'appearance.json'`; пользовательские PNG — `context.paths.data / 'appearance/icons/<sha256>.png'`. Встроенные — через стабильный `data/current/assets/appearance/`.
- `Context.appearance_config: Path | None = None` — дополнительное поле только для текущего plan/install; источник не сохранять в Selection/receipt. Без него builder читает установленный JSON. Сам installed JSON остаётся CAS-owned ресурсом.
- API helper CLI — `appearance.py --config FILE --cwd DIR --phase shell|launch|return`; ID берётся только из environment. `--probe` разрешает read-only проверку explicit-session API без записи свойств для doctor/reconcile.
- Точные внутренние константы timeout и защита от устаревшего launch-job выбираются в задаче 2; общий hard deadline не более 3 секунд, проверка через fake clock. Не строить новый постоянный сервис или очередь.
- Уточнение исполнения Task 3: process substitution с приватным lifetime FD заменяет первоначальное предположение о shell `wait`: после TERM ждать EOF supervisor, zsh штатно reap-ит дочерний процесс. Это позволяет избежать job notifications без изменения MONITOR; PID не сигналить при EOF/смене owner, FD не передавать Codex/worker. Проверки PTY и no-late-writes обязательны.

### Task 1: Правила и готовые иконки

**Files:** Create `runtime/appearance.py`, `runtime/assets/appearance/{ios,android,kotlett,ios-mail,ios-cloud,android-mail,android-cloud}.{png,svg}`, `tests/test_appearance_rules.py`; modify `THIRD_PARTY_NOTICES.md`.

**Interfaces:** `load_rules(path: Path) -> list[dict[str, str]]`, `select_rule(rules: list[dict[str, str]], cwd: Path) -> dict[str, str] | None`, `BUILTIN_ICONS: frozenset[str]`. API-модуль импортируется лениво, эти функции доступны без `iterm2`. Имена иконок проверяет registry; доступность/копирование custom PNG проверяет installer задачи 4.

- [ ] Написать падающие unittest: пять вариантов, root/child, похожий соседний путь, наиболее длинный корень, физический симлинк, повтор root, отсутствующий root, неверные JSON/цвет/поля/icon, метасимволы в пути. Использовать временные существующие корни; отсутствие корня не делает весь набор невалидным.

```python
def test_root_boundary_and_nested_precedence(self):
    self.assertEqual(select_rule(self.rules, self.root / 'mail' / 'src')['icon'], 'android-mail')
    self.assertIsNone(select_rule(self.rules, self.root / 'mail-copy'))
    self.assertEqual(select_rule(self.nested_rules, self.root / 'mail' / 'nested')['color'], '#568DCE')
```

- [ ] RED: `python3 -m unittest tests.test_appearance_rules -v`; ожидается ошибка отсутствующего модуля/поведения, а не сторонней зависимости.
- [ ] Реализовать указанные функции через pathlib/json/re, без shell и сканирования дерева репозитория. Нормализовать цвет в `#RRGGBB`, корни физически; недоступный cwd/root не выбирать. Подготовить перечисленные PNG/SVG и зафиксировать собственное происхождение/лицензию ассетов.
- [ ] GREEN: та же команда; проверить семь PNG с валидными сигнатурой/размерами/прозрачностью и соответствием registry. Проверить отсутствие созданного `INJECTED` и каталогов недоступного root.
- [ ] Зафиксировать результат задачи в рабочем отчёте без коммита. Маленькие PNG позже оцениваются в реальном размере в задаче 5.

### Task 2: Применение через официальный API и ограниченный переход APS

**Files:** Modify `runtime/appearance.py`; create `tests/test_appearance_runtime.py`.

**Interfaces:** потребляет Task 1 и `runtime.events.terminal_from_environment(environment)`; производит `apply(config: Path, cwd: Path, phase: str, *, environment: dict[str, str]) -> str` с результатами `applied|ignored|unavailable|timeout` и `probe(*, environment: dict[str, str]) -> str` с `ready|unavailable|timeout`. Синхронный entrypoint владеет asyncio/deadline; tests подменяют private API adapter, не требуют установленного SDK.

- [ ] Написать fake-API тесты на explicit UUID, только четыре разрешённых свойства, `IconMode.CUSTOM`, выбор builtin/custom path, no match, отсутствующий SDK/API/session, отказ и deadline. Проверить светлую/тёмную конфигурацию профиля по фактическому API: цвет виден в активном режиме без смены прочих свойств.

```python
def test_conflicting_ids_do_not_connect(self):
    result = apply(self.config, self.repo, 'shell', environment=self.conflicting_ids)
    self.assertEqual(result, 'ignored')
    self.api.connect.assert_not_called()
```

- [ ] RED: `python3 -m unittest tests.test_appearance_runtime -v`.
- [ ] Добавить lazy import официального SDK и запись через LocalWriteOnlyProfile в найденную по ID сессию. `launch` ограниченно наблюдает переход profile/job, назначает после перехода `&codex` и закрывает подписку/соединение не позднее deadline; отсутствие перехода также ограничено. Использовать события API, не предполагать, что фиксированного sleep достаточно.
- [ ] Добавить тесты APS: профиль сменился после первоначального назначения, Codex завершился раньше обработки события, в той же вкладке началось новое назначение. Подписка заканчивается, устаревшая работа не пишет поверх нового назначения. Выбранную минимальную защиту от устаревания документировать в одной строке.
- [ ] GREEN: обе `tests.test_appearance_rules` и `tests.test_appearance_runtime`; проверить cleanup при cancellation/timeout и отсутствие открытия API при невалидном ID. Внутренний CLI не печатает traceback, пути, команды или ложное `applied`.

### Task 3: Встраивание в shell, Codex и restore

**Files:** Create `runtime/appearance.zsh`, `tests/test_appearance_shell.zsh`; modify `runtime/codex.zsh`, `iterm2_utils/features/shell.py`, `tests/test_shell.py`, `tests/test_codex_shell.zsh`; при необходимости точка вызова в `runtime/codex_restore/codex-resume.zsh`, с тестом в `tests/restore/test_codex.zsh`.

**Interfaces:** `appearance.zsh` объявляет `_iterm2_utils_appearance(phase, cwd)` и однократный bootstrap для интерактивной iTerm-сессии. Получает `ITERM2_UTILS_PYTHON` и абсолютный `ITERM2_UTILS_APPEARANCE_CONFIG` из managed shell block, вызывает CLI задачи 2. `shell.build`/`runtime_payload` сохраняют свои сигнатуры.

- [ ] Написать fake-helper shell тесты: первый interactive startup один раз, source дважды, обычный cd, source неинтерактивно/в другом терминале, Codex interactive/resume/fork и служебные subcommands. Проверить точные argv и код выхода fake Codex, включая сбой helper.

```python
def test_appearance_is_dispatcher_consumer_without_enabling_shell_marks(self):
    text = self.render_shell(('appearance',))
    self.assertIn('appearance.zsh', text)
    self.assertIn('codex.zsh', text)
    self.assertNotIn('iterm2_shell_integration.zsh', text)
```

- [ ] RED: `python3 -m unittest tests.test_shell -v` и `/bin/zsh tests/test_appearance_shell.zsh`.
- [ ] Подключить helper в existing dispatcher только после interactive-классификации; сохранить исходный физический cwd и результат команды. Короткоживущий launch-helper не блокирует старт; на выходе из Codex завершается/снимается и выполняется bounded `return` для сохранения оформления после обратного APS. Оградить helper от наследования во вложенные shell, не глушить stderr/выход самого Codex.
- [ ] Добавить `appearance` к consumer/dependency множествам shell/runtime; оформлению не требуется включать feature `shell` с command marks. Использовать существующую конфликтную проверку неизвестных aliases/functions; не копировать и не оборачивать чужую функцию.
- [ ] GREEN: `python3 -m unittest tests.test_shell -v`, `/bin/zsh tests/test_codex_shell.zsh`, `/bin/zsh tests/test_appearance_shell.zsh`, `/bin/zsh tests/restore/test_codex.zsh`. Отдельно доказать, что реальный restore-путь вызывает назначение, а helper не меняет статус/код возврата restore.

### Task 4: Opt-in, установка, doctor, update и uninstall

**Files:** Create `iterm2_utils/features/appearance.py`, `tests/test_appearance_feature.py`; modify `iterm2_utils/{models,cli,planner,discovery,lifecycle}.py`, `iterm2_utils/features/shell.py`, `tests/{test_selection,test_cli,test_discovery,test_lifecycle,test_pending_ui,test_payload}.py`.

**Interfaces:** `appearance.build(context: Context, selection: Selection) -> ChangeSet`; `Context.appearance_config` описан выше. Selection не хранит source path. CLI добавляет `--appearance-config` только plan/install; feature включается в `FEATURES`, `CODEX_ONLY`, все существующие guards/`agents_for`/`resource_pairs`, lifecycle ORDER и таблицу affected builders. Owner — существующая exclusive схема `appearance` → `codex:appearance`; shell/runtime остаются shared consumers.

- [ ] Написать fixture-тесты нового выбора и явного JSON, без изменения реального HOME. Проверить ошибка до записи при первом отсутствии правил, CLAUDE-only unsupported, bootstrap ничего не включает, path без feature отклоняется. Неверный JSON/цвет/icon не проходит в частично применённый appearance checkpoint.

```python
def test_update_survives_source_removal(self):
    installed = self.install_appearance_with_custom_png()
    self.source_json.unlink()
    self.source_png.unlink()
    self.assertEqual(self.update_findings(), [])
    self.assertEqual(self.installed_rule()['icon'], installed.icon_path)
```

- [ ] RED: `python3 -m unittest tests.test_appearance_feature tests.test_selection tests.test_cli -v`.
- [ ] Реализовать builder: прочитать explicit input либо owned installed JSON, проверить PNG/registry, описать копии custom PNG с content hash и installed JSON как FileEdit. Проверять размер/структуру PNG до копирования без новой image dependency. Fingerprint учитывает содержимое правил и иконок; public findings не содержат payload/личные пути. Для update собственный нормализованный JSON и копии достаточны, custom-source больше не нужен.
- [ ] Discovery отдельно проверяет import `iterm2` в выбранном Python без API/GUI. Отсутствие модуля — `missing_dependency`, UI-разрешение API — отдельный pending шаг `appearance_api`. `doctor --live` и `reconcile --step appearance_api` используют read-only probe задачи 2; offline doctor не снимает pending и не объявляет применение цвета проверенным.
- [ ] Включить feature в checkpoints и shared-resource ownership, не переписывая engine. Проверить merged install/другую feature без JSON, повторную установку без JSON, явную замену нового набора, changed-file CAS, ошибки записи и частичный uninstall со status/restore/shell другого агента. Повторно изменённый чужой файл сохраняется; running sessions не трогать.
- [ ] GREEN: перечисленные unit-модули плюс `tests.test_discovery tests.test_lifecycle tests.test_pending_ui tests.test_payload`. Проверить snapshot dry-run побайтно, отсутствие API вызовов и startup shell в plan, недоступный SSD без mkdir/fallback, источник custom PNG с Unicode/метасимволами и повреждённый owned JSON.

### Task 5: Поставка, документация и итоговая проверка

**Files:** Modify `tools/check_export.py`, `tools/check_skill.py`, `tests/test_export.py`, `tests/test_payload.py`, `README.md`, `CHANGELOG.md`, `THIRD_PARTY_NOTICES.md`, `docs/compatibility.md`, `skills/iterm2-setup/SKILL.md`, `skills/iterm2-setup/references/{features,troubleshooting,ui}.md`; create `docs/repo-appearance.md` с нейтральным JSON-примером, включить в export.

**Interfaces:** существующие `runtime_payload`, `EXPORT_FILES`, `build(repo, destination)`; никакого второго installer. Явно разрешить только известные assets/appearance PNG и необходимые source SVG, не любое расширение/каталог из checkout.

- [ ] Добавить падающие payload/export тесты: семь встроенных иконок, helper и лицензии попадают в установленный runtime/archive; после удаления checkout и исходного JSON/PNG fixture runtime выбирает иконки из installed data. Assets отсутствуют/подменены симлинком — поставка отклоняется.
- [ ] RED: `python3 -m unittest tests.test_payload tests.test_export -v`.
- [ ] Обновить allowlists/runtime identity, затем README/skill: восьмая опция, только Codex, JSON schema, свои PNG, выбор существующего Python с SDK, plan/install/doctor/update/uninstall. Сохранить запрет включать функции через bootstrap и ownership существующих skill-копий. В changelog описать поведение, не обещать live-приёмку до неё.
- [ ] GREEN и общая проверка: `python3 -m unittest discover -v`; `/bin/zsh tests/test_codex_shell.zsh`; `/bin/zsh tests/test_appearance_shell.zsh`; `/bin/zsh tests/restore/test_codex.zsh`; `python3 tools/check_sources.py`; `python3 tools/check_skill.py`; `python3 tools/check_export.py`; `python3 tools/build_release.py --destination dist`; `git diff --check`. Baseline до изменений: 424 unittest PASS; повторяется после реализации, не при одном изменении плана.
- [ ] Провести итоговое независимое review по **спецификации и diff**, а не только по задачам плана, исправить подтверждённые дефекты и перепроверить затронутое. До публикации убедиться, что реальные личные root/config/receipts в diff/archive отсутствуют.
- [ ] Отдельная live-приёмка через публичный CLI после code review: составить локальный JSON пяти согласованных root/цветов из персонального черновика, проверить доступность MobileSSD перед использованием его целей, выполнить конкретный plan/dry-run и применить только appearance. Это настройка запрошенных пользователем функций, не dev-fixtures; не читать секреты/не запускать мобильные сборки. TCC/API approval, если потребуется, остаётся пользователю.
- [ ] Предупредить перед открытием собственных временных вкладок. Проверить пять сочетаний и читаемость пары символов при штатном размере; каждый start shell/Codex, APS на входе/выходе, resume/restore, обычный cd, no-match и запуск с недоступным target без повреждения соседних вкладок. Временно меняемые тестовые настройки восстанавливать адресно, свои вкладки закрыть, пользовательские оставить.
- [ ] Записать фактическую fixture/live-матрицу в compatibility. При недоступном GUI/API честно оставить live pending; не объявлять исходную задачу полностью выполненной по одним unit-тестам. Персональную конфигурацию в публичный отчёт не включать.

## Self-review плана

Проверено автором по согласованной спецификации: поведение и правила → 1/3;
иконки/лицензии → 1/5; explicit-session API/ошибки/APS → 2/3;
opt-in, prerequisites, dry-run, CAS/update/uninstall → 4;
независимая от checkout поставка, публичные docs и live → 5.
Пять пунктов Review Focus имеют проверки в указанных задачах.
Интерфейсы `load_rules`, `select_rule`, `apply`, `probe`, `Context.appearance_config`
и пути installed data согласованы между задачами. Новых сервисов/агентов/
командного семейства не добавляется. Продуктовый код ещё не изменён.

## Исполнение после согласования плана

Рекомендуется **subagent-driven**: пять последовательных задач с отдельной
проверкой каждой, затем review всей функции по спецификации. Между runtime,
dispatcher и CAS есть значимые границы; независимая проверка каждой поможет
поймать нарушение сохранности настроек до локальной установки.
Альтернатива — native исполнение в этой сессии с одним независимым итоговым review.
Пользователь согласовал план и выбрал `superpowers:subagent-driven-development`.
Реализация выполняется последовательно с отдельным review каждой задачи.
