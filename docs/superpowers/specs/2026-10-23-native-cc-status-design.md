# Переход статусов iterm2-utils на штатный cc-status

Дата: 23 октября 2026, МСК. Статус: builder-check пройден; ожидает просмотра
пользователем вместе с планом; реализация не начата.

## 1. Задача и принятый объём

Пользователь выбрал переход на `cc-status`, чтобы уменьшить сопровождение после
обновлений iTerm2 и получить доступный штатный функционал. Отдельный пример —
различать завершение ответа и ошибку агента на вкладке. Запрошены сначала эта
спецификация, затем план; это разрешение подготовить оба документа, без промежуточного
ожидания и без разрешения менять рабочую установку.

Меняем обработку и установку **статусов Codex** в существующем публичном пакете.
Для Claude уже используется штатный установщик iTerm2; его не заменяем вторым
обработчиком. Копирование EN/RU, shortcuts, restore, MCP и shell integration
сохраняют назначение и независимый выбор. Уведомления macOS остаются отдельной
опцией и не превращаются в штатный одноразовый watch уведомлений iTerm2.

База проекта — `8c5643ed574f016bca46952ae6cd804d09195580`, beta.1. Исходная
[спецификация пакета](2026-10-22-iterm2-utils-design.md) продолжает действовать,
кроме явно перечисленных изменений ниже. Технические решения в этом документе,
которые пользователь отдельно не выбирал, предложены автором спецификации.

## 2. Что подтверждено, а что пока нельзя обещать

Исследован выпущенный iTerm2 **v3.7.6**, commit
`7ce456b98db38d3f0bafd70ffec87752e69d5d58`, а не master:

- `cc-status --agent codex` поддерживается и поставляется рядом с `it2` в bundle.
- Native обработчик знает `working`, `waiting`, `idle`, `done`, `error`, обновляет
  детали, считает фоновых агентов и рисует Codex progress ring.
- `StopFailure` переводит завершившийся ход в `error`, если фоновой работы нет.
  Если работа ещё идёт, upstream оставляет `working`. Последний завершившийся
  фоновый агент может затем показать `done`, даже если родитель прежде ошибся.
- `Interrupt` завершает основной ход без ложного `done`, сохраняя учёт фоновой работы.
- В обычной локальной панели адрес берётся из `TERM_SESSION_ID`; `ITERM_SESSION_ID`
  сам по себе для этого native обработчика недостаточен.

Отдельно проверен Codex **rust-v0.163.0**, commit
`83086188ae0614bd882818ff1aa23f3194962012`: его `HookEventName` содержит ровно
`PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`,
`SessionStart`, `SessionEnd`, `UserPromptSubmit`, `SubagentStart`, `SubagentStop`,
`Stop`, `Interrupt`. **Нет `StopFailure`, `Notification` и `PostToolUseFailure`.**
`Stop` не несёт достоверного признака неуспешного завершения API-вызова.

Следовательно, переход даёт Codex штатные статусы и `done`, но **не обещает
автоматический `error` для ошибок Codex 0.163.0**. В его конфигурацию не добавляются
несуществующие события из примера iTerm2. Возможность нарисовать `error` синтетическим
payload проверяет renderer, но не доказывает, что Codex испускает такой hook.
Для Claude и будущих версий Codex поддержку событий подтверждаем отдельно.

Падение теста/команды, сообщение об ошибке в обычном ответе, ошибка собственного
hook и фатальный сбой ответа агента — разные события. Регулярные выражения по экрану,
чтение переписок и предположение «любая ошибка инструмента = error всей сессии»
в эту миграцию не входят. Полное обнаружение ошибок Codex потребует отдельного
подтверждённого источника событий и отдельного решения.

## 3. Пользовательское поведение

| Ситуация | Результат |
| --- | --- |
| Codex принимает запрос/использует инструмент | Native `working` и progress ring |
| Нужно разрешение | Native `waiting` |
| `request_user_input` / `request_user_input_async` ожидает ответа | Native `waiting` через минимальное преобразование события |
| Основной ответ готов, фоновой работы нет | Native `done`; штатный переход к `idle` после пользовательского ввода |
| Основной ответ закончился, агенты ещё работают | Native учёт фоновой работы, обычно `working` |
| Пользователь прервал ход | Native `Interrupt`, без уведомления «ответ готов» |
| Достоверный поддерживаемый `StopFailure` | Native `error` по политике upstream; для Codex 0.163.0 источник отсутствует |
| Запуск / завершение сессии | Штатный сброс статуса и фонового счётчика |
| Compact внутри существующего хода | Рабочий статус без сброса фонового счётчика |

Цвета, сортировка `done`/`error`, сброс после ввода и формат native деталей определяются
iTerm2. Пакет не ведёт параллельную модель этих состояний и не пишет собственный
`it2 set-status`/OSC для их исправления. Особенности конкурирующих permission/tool
событий следуют upstream; нельзя обещать прежний Python-алгоритм очереди ожиданий.
Строгая адресация и защита от заведомо устаревших lifecycle событий сохраняются
отдельно, на границе доставки, а не второй машиной статусов.

## 4. Архитектура

### 4.1. Источник штатных утилит и версии

Цель: macOS + zsh; installer и Python runtime — Python 3.11+, stdlib.
Для нового backend Codex нужен iTerm2 **3.7.6 или новее**, исполняемые
`Contents/Resources/utilities/cc-status` и соседний `it2` из одного проверенного bundle.
Это минимальная поддерживаемая база проекта, не утверждение о первом появлении фичи.

Discovery проверяет bundle ID `com.googlecode.iterm2`, версию, существование и
исполняемость обеих утилит. Read-only `it2 set-status --help` подтверждает наличие
`--background-tasks`, `--background-tasks-delta`, `--turn-open`, `--if-turn-open`,
`--if-background-tasks`, `--json`. Наличие файла или basename не означает совместимость.
`cc-status --help` не вызывается: это обработчик stdin, а не обычный CLI-парсер.
Новые версии допускаются при этих проверках, но не объявляются живьём проверенными.

В settings сохраняется абсолютный путь выбранного app bundle; native executable
разрешается внутри этого bundle при каждом событии. **Не копируем `cc-status`/`it2`
в runtime и не закрепляем их хеш как vendored зависимость.** После штатного обновления
используется новая пара из bundle. Перенос/исчезновение bundle требует doctor/update;
не ищем случайный `cc-status` в PATH и не запускаем другой установленный iTerm2.
В receipts пакет не присваивает себе файлы приложения или штатный symlink iTerm2.

### 4.2. Один вход hooks, один писатель статусов

Сохраняется установленный checkout-independent `runtime/hook.py`. В Codex для
каждого события ровно один наш command-hook с `timeout: 3`; он передаёт событие
native обработчику, затем обслуживает отдельно выбранные notifications/restore.
Нельзя дополнительно установить прямой вызов `cc-status` на то же событие.

`runtime/native_status.py` отвечает за payload, окружение, ограниченный subprocess
и узкую защиту доставки. `runtime/events.py` владеет списком событий Codex независимо
от vendored Python-машины. Видимый backend Codex всегда `cc-status`; автоматического
fallback к старой машине нет. При недоступности native установка статусов блокируется,
а уже установленный hook завершает обработку безопасно; другие функции независимы.

В `runtime.json`: `status_backend: "cc-status"`, `iterm2_app`, `native_identity_cache`
и прежний `status` boolean; `status: false` гарантирует отсутствие native вызовов.
`it2` остаётся для уведомлений/restore. Старый `cache` не используется как native state.
Claude status обрабатывает только его существующая штатная интеграция; Python-hook
Claude notifications не запускает native status повторно.

### 4.3. Адресация и защита доставки

- Интерактивный Codex сохраняет `--no-daemon`; штатный backend не исправляет наследование
  окружения общего app-server. Сохраняются существующие исключения service-команд,
  в том числе после глобальных options. Старые shell wrappers не наслаиваются.
- На входе нужен валидный явный UUID из `ITERM_SESSION_ID`, либо из `TERM_SESSION_ID`,
  если первого нет. Если обе переменные присутствуют, обе должны корректно указывать
  один UUID; malformed или несовпадающие адреса дают no-op и диагностический признак.
- Native subprocess получает копию окружения с нормализованным
  `TERM_SESSION_ID=w0t0p0:<UUID>` и согласованным `ITERM_SESSION_ID`. Это адресация по
  UUID, не использование координат `w0t0p0` и не выбор активной панели.
- Payload `terminal_uuid`, если задан, обязан совпадать с выбранным UUID.
- Эта миграция поддерживает обычные локальные панели. При непустом `TMUX` native
  вызов не делается; tmux/control mode/SSH требуют отдельной приёмки. Нельзя удалять
  `TMUX` из окружения ради обхода штатной защиты от неверной адресации.
- В отдельном приватном `native_identity_cache` хранится только текущий `session_id`,
  `turn_id` и признак `SessionEnd` по UUID. Старый статусный JSON туда не импортируется.
  Событие другой сессии допускается только при `SessionStart`/`UserPromptSubmit`;
  устаревшие `Stop`/`Interrupt`/compact с другим известным turn ID игнорируются.
  После `SessionEnd` хвостовые события игнорируются до следующей границы запуска/хода.
  Проверка, обновление identity и native вызов сериализуются одним lock по UUID.
  Это метаданные принадлежности доставки; working/waiting/done/агенты там не хранятся.

### 4.4. Payload и минимальные преобразования

Native получает JSON через stdin, без shell и без временного raw-event файла.
Передаются только поля, используемые штатным обработчиком: `hook_event_name`,
`tool_name`, `tool_input` для PermissionRequest, `last_assistant_message` для
завершения, `notification_type`, `message`, `agent_id`, а для `background_tasks` —
только `id`/`status`. Поля prompt, cwd, transcript_path, tool output и неизвестные
поля не передаются. Исходный payload живёт только в памяти текущего hook.

Нативные детали разрешений и последнего ответа могут быть видны в Session Status /
Cockpit; это сознательно используемая штатная возможность. Пакет не сохраняет их
в своих caches, receipts, diagnostics, argv собственного hook или логах. Правила
сохранения интерфейса самим iTerm2 не переопределяются этим пакетом.

Ровно три преобразования закрывают существующие сценарии, которых нет в native mapping:

1. `PreToolUse` для `request_user_input`/`request_user_input_async` становится только
   для native вызова `Notification` с `notification_type=elicitation_dialog` и
   фиксированным `message="Input needed"`, без содержимого вопроса. Реальный Codex
   `Notification` hook для этого не регистрируется. `PostToolUse` остаётся исходным.
2. `PreCompact`/`PostCompact` становятся для native `PreToolUse`/`PostToolUse`
   без tool metadata: сохраняют рабочий статус без сброса native count.
3. `SessionStart` с `source=compact` становится для native `PreToolUse`, сохраняя
   identity и native count; обычный startup/resume остаётся `SessionStart`.

Списки событий известной версии Codex не расширяются догадками. Для Codex 0.163.0
регистрируются только перечисленные в разделе 2 двенадцать событий; поддержка
будущего `StopFailure` добавляется после подтверждения официальной схемой и тестом.

### 4.5. Бюджет и изоляция сбоев

Сохраняется абсолютный бюджет одного Python-hook **2.7 секунды**, внешний timeout
**3 секунды**, stdout — ровно `{}` и exit 0 при штатных ошибках.
В native фазу входят lock и subprocess; её общий лимит **1.8 секунды**, ожидание
lock не более **0.4 секунды**, child timeout — оставшееся время этой фазы.
Native выполняется до необязательных handlers, которым остаётся общий остаток.
Deadline не продлевается при ошибке или конкуренции.

Timeout/общий alarm/отмена убирают всю запущенную subprocess process group, включая
дочерний `it2`; сырые stdout/stderr не попадают в контекст агента. Ошибки native,
notifications и restore изолируются; недоставка одного события не вызывает повтор
GUI, перезапуск агента или неограниченные retries. Сбой native не запрещает попытку
остальных выбранных handlers, пока остался общий бюджет. Гарантия доставки при
недоступном API или исчерпанном бюджете не заявляется.

## 5. Совместимость, установка и владение

### Чистая установка и штатная интеграция

Новая установка Codex status записывает backend/settings/наши hooks через текущие
pure builders, transaction engine, receipts/CAS и стабильный `current`.
`status` не включает notifications, restore, Workgroup, Auto-Enter, Diff или Review.
Для Claude остаются существующие UI checkpoint и reconcile: только новые подтверждённые
native записи могут получить ownership; ранее существующие остаются внешними.

Полный внешний набор прямых native Codex hooks из выбранного bundle можно переиспользовать
без присвоения ownership и без второго status writer. Полнота означает по одному
распознанному command-hook для всех десяти native lifecycle событий из списка Codex
без `PreCompact`/`PostCompact`, с аргументами `--agent codex`, без дополнительной
shell-логики и конфликтующих status writers. Это внешняя интеграция: adapter-only
расширения для input/compact для неё не обещаются. Частичный набор, дубликаты,
другая app-копия, неизвестный wrapper или одновременный legacy writer — conflict.
Reuse статусов не отменяет наших hooks для отдельно выбранных notifications/restore.

### Обновление уже установленного пакета

Валидный receipt beta.1 и выбранный Codex status разрешают update принадлежащих
пакету hooks/settings на новый backend. Сохраняются независимые agent_features и
shortcuts. Замена runtime/settings/hooks происходит в одном status checkpoint;
ошибка записи/CAS оставляет предыдущие runtime и receipt целыми. Если общий runtime
используется и другими фичами, его switch содержит совместимые версии всех consumers.

Старый Python driver больше не пишет статус. `vendor/codex_status/status.py` временно
остаётся только как зависимость **уведомлений**: `notifier.transition()` использует его
модель, это не второй writer в UI. Его удаление/переписывание уведомлений — отдельная
задача. Файлы provenance и MIT attribution сохраняются; нельзя объявлять удаление
всего Python-слоя или удалять лицензию по факту замены только status driver.

### Внешний legacy plugin

Активный `iterm2-status`/`codex-iterm2-status` без нашего receipt по умолчанию
переиспользуется как **legacy backend**, с явным диагностическим сообщением, что
это ещё не `cc-status`. Для миграции требуется уже существующий `--adopt-legacy`;
сохраняется точная проверка известных plugin keys и shell blocks. При adoption
отключение известного plugin и установка нового writer — одна транзакция.
Неизвестные/изменённые wrappers требуют разрешения конфликта; старые repositories,
кэши plugin и настройки автора при разработке не меняются.

### Удаление и rollback

Selective uninstall удаляет только принадлежащую пакету регистрацию статусов.
Notifications/restore и их shared hooks/runtime сохраняются, если ещё выбраны;
обратная ситуация не выключает статусы. Отключение legacy восстанавливается по
receipt только при совпадении текущего значения с installed. Возврат legacy writer
допустим только в той же успешной операции, которая удаляет наш writer. Внешние
native hooks не удаляются; app utilities и данные разговоров не принадлежат пакету.
Чужое изменение ресурса даёт conflict, не восстановление полного backup.

## 6. Диагностика и документация

Doctor показывает отдельно: выбранный backend (`cc-status`, external native или
legacy reused); пригодность bundle/утилит; регистрацию hook; need-new-session / trust;
read-only связь с API; поддержку источника ошибок. Для Codex 0.163.0 сообщение
об отсутствии `StopFailure` — неблокирующее ограничение, не отказ всей status фичи.
Для неизвестной версии источник ошибки помечается непроверенным, а не рабочим.

`doctor --live` принимает статусы `""`, `idle`, `working`, `waiting`, `done`, `error`;
не печатает `detail`/payload и не меняет статус. Доступный API не доказывает доставку
hooks. Read-only диагностика не запускает native обработчик и не трогает его stdin.

README, compatibility, notification-events и setup skill/references объясняют:
состояния, native dependency, отличие native error renderer от реального источника
ошибок Codex, внешний legacy reuse и явную миграцию, новую сессию и границы живой
приёмки. Не использовать утверждения «ошибки Codex теперь отображаются» без
подтверждённого события на проверенной версии.

## 7. Проверка и критерии приёмки

Автотесты работают только с TemporaryDirectory HOME, fake bundle/runner и
искусственными payload. Они не читают настоящие настройки агента/iTerm2.

1. Discovery отличает пригодный native bundle от отсутствующего/старого/повреждённого;
   не запускает cc-status и не мутирует prefs. Путь с пробелами/Unicode корректен.
2. Status-only вызывает ровно native `--agent codex`; прежний Python transition /
   status_command не вызываются. Notifications-only и restore-only не вызывают native.
3. Одинаковый UUID, TERM-only, оба разных UUID, malformed, пустой env, чужой payload
   UUID, late Stop, другая сессия, SessionEnd и TMUX проверяют строгую адресацию.
4. Проверяются три payload преобразования; native-only поля не просачиваются в
   notification/restore event. Частные строки отсутствуют во всех файлах/отчётах пакета.
5. Missing/failed/slow native и его child не оставляют процессов; результат hook
   `{}`/exit0 и wall time <3 s. Нет повторного вызова и обхода через legacy writer.
6. Повторный install/update не дублирует hooks, в Codex 0.163.0 ровно 12 допустимых
   имён; скомпилированный renderer не подменяет проверку схемы Codex.
7. Beta.1 receipt, external legacy reuse/adoption, foreign native complete/partial,
   CAS failure, rollback и selective uninstall сохраняют ownership и независимость фич.
8. Все прежние notification/focus/dedup/interrupt/restore и zsh contracts проходят.
9. Runtime работает после удаления checkout; native utility остаётся в bundle.
   Смена bundle utilities на месте подхватывается без копирования приложения в payload.
10. Export allowlist/источники/лицензии, архив и CI включают новые модули/тесты;
    docs отражают фактическую, а не предполагаемую проверку.

Живая приёмка проводится отдельно в изолированной тестовой конфигурации Mac с
предупреждением перед собственным окном; только тестовые вкладки и явные UUID.
Матрица: Codex 0.163.0 + iTerm2 3.7.6, конкретная доступная версия Claude, startup,
работа, input/permission, Stop/done, Esc, параллельные subagents, compact, два UUID,
обновление bundle и отключённый API. Отдельный синтетический `StopFailure` проверяет
native renderer; реальный сбой Codex отмечается как неподдерживаемый источник.
Настройки автора и настоящие разговоры не используются для приёмки. Если изоляция
недоступна, fixture checks можно завершить, но live пункты остаются unverified и
миграция не объявляется проверенной на живом Codex.

## 8. Сознательные изменения относительно исходной спецификации

| Было и почему | Теперь и почему |
| --- | --- |
| §4.2: Python iterm2-status для Codex, native для Claude | Native для обоих; собственный слой Codex ограничен установкой/доставкой |
| working/waiting/idle, готовый ответ = idle | Native `done` отдельно; error только при достоверном событии |
| Собственная очередь waiting/подсчёт subagents в status driver | Алгоритм upstream; не поддерживаем его Python-копию |
| UUID через ITERM_SESSION_ID | Согласованная доставка в TERM_SESSION_ID, с проверкой обоих источников |
| Compact сохранял ход и агентов | Сохраняем это через три явных преобразования вместо native reset |
| Общий Python transition используется status и notifications | Status вызовы удаляются; notification-only dependency пока остаётся |
| Generic status capability без minimum | Native Codex baseline iTerm2 3.7.6 + executable/help checks |

Не изменяются `--no-daemon`, отказ от active-tab fallback, observational hooks,
privacy caches, отдельные notifications, выбор функций и receipt/CAS.

## 9. Первоисточники

- [iTerm2 downloads / changelog](https://iterm2.com/downloads.html).
- [HookEvent.swift v3.7.6](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/cc-status/Sources/cc-status/HookEvent.swift).
- [Addressing.swift v3.7.6](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/cc-status/Sources/cc-status/Addressing.swift).
- [main.swift v3.7.6](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/cc-status/Sources/cc-status/main.swift).
- [It2Runner.swift v3.7.6](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/cc-status/Sources/cc-status/It2Runner.swift).
- [Codex HookEventName 0.163.0](https://github.com/openai/codex/blob/83086188ae0614bd882818ff1aa23f3194962012/codex-rs/protocol/src/protocol.rs#L1688).
- [Codex Stop payload 0.163.0](https://github.com/openai/codex/blob/83086188ae0614bd882818ff1aa23f3194962012/codex-rs/hooks/src/events/stop.rs).
- [Native Codex hooks example](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/tests/codex-hooks.json):
  содержит StopFailure, поэтому не может без сверки копироваться в Codex 0.163.0.

## 10. Граница этого этапа

Результат — эта спецификация и связанный план, проверенные перед передачей пользователю.
Реализация, миграция рабочей установки, новая публикация и живая приёмка начинаются
после просмотра документов пользователем. Ранее выбранный способ исполнения —
`superpowers:subagent-driven-development`; повторно выбирать его не требуется.
