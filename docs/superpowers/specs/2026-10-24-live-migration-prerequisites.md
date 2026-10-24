# Исправления для применения native-миграции

Пользователь запросил применить уже реализованную миграцию на своей машине.
Исходная спецификация `2026-10-23-native-cc-status-design.md` остаётся обязательной.
Это ограниченные исправления обнаруженных препятствий, без новых функций.

## Подтверждённые причины

1. Консервативный TOML editor отвергает обычный quoted scalar key в посторонней
   таблице, например `"model.example" = "model.previous"`. Поэтому изменение
   известного plugin.enabled невозможно даже при корректном остальном документе.
2. `terminal-notifier` принимает `-version`; используемый discovery `--version`
   возвращает exit1. Read-only `-help` подтверждает установленную 3.1.0.
3. Approval-only notifications ограничены Codex 0.163.0. В установленном 0.164.0
   фильтрация по `approval-requested` подтверждена исходниками release commit
   `6aaac694803004a63c6f393d153c96d22521a6b9`:
   `codex-rs/tui/src/chatwidget/notifications.rs` и `core/config.schema.json`.

## Требуемое поведение

- Поддержать basic/literal quoted scalar keys в span scanner через TOML parser,
  отличая имя с точкой внутри кавычек от настоящего dotted path. Правка выбранного
  ключа сохраняет все другие statements побайтно. Quoted replacement key обязан
  оставаться валидным. Настоящие dotted и inline edits остаются конфликтом.
- Для terminal-notifier использовать только read-only `-version`, для остальных
  программ сохранить прежние probes. Не отправлять уведомления ради discovery.
- Добавить ровно 0.164.0 в проверенную approval-notifications capability; неизвестные
  версии остаются заблокированными. Не расширять Alt+Enter capability и hooks enum:
  новые PreModelRequest/PostModelRequest не нужны для этой миграции. Источник
  native error остаётся limited/unverified; StopFailure не добавлять.
- Не ослаблять foreign-notifications guard. Перенос выполнить двумя проверенными
  этапами: status+restore с explicit adoption существующих shell blocks, затем
  notifications после реального отключения legacy. Без --coexist-notifications.
- Реальные изменения делает только controller штатным CLI после reviews/tests.
  Workers используют исключительно TemporaryDirectory и fake runners. Профиль,
  clipboard, MCP, Claude и прочие настройки не менять.

## Приёмка

Регрессии на quoted keys с точками, кавычками и multiline values; настоящий dotted
key и inline parent сохраняют conflict. Fake terminal-notifier отклоняет --version
и принимает -version. Для 0.164.0 approval-only builder доступен и обратим, для
0.165.0/unknown заблокирован. После полного suite controller получает безопасный
реальный preview, выполняет миграцию и проверяет receipt/settings/hooks; загрузка
новых hooks может потребовать новой сессии и человеческого trust. Не перезапускать
текущий разговор. Live API readiness не объявлять доказательством доставки событий.
