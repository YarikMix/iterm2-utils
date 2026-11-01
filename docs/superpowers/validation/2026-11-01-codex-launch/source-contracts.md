# Контракты исходников перед Task 2

Дата проверки: 2026-11-01. Это source verification, **не живая приёмка**.
Читались только публичные файлы GitHub, скачанные в `/tmp`; пользовательские
настройки, auth, environment-файлы и daemon не читались. Первичная source-разведка
выполнена до production-кода; текущая реализация описана в последнем разделе.

## Точные версии

- Codex `rust-v0.166.0`: commit
  [`6ff1e1ca3b30fc8b914720681fcf5fe62e95f856`](https://github.com/openai/codex/commit/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856).
- iTerm2 `v3.7.6`: commit
  [`7ce456b98db38d3f0bafd70ffec87752e69d5d58`](https://github.com/gnachman/iTerm2/commit/7ce456b98db38d3f0bafd70ffec87752e69d5d58).

## Codex: ключи и реальные значения по умолчанию

[`core/config.schema.json`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/core/config.schema.json#L5045)
и [`config/src/types.rs`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/config/src/types.rs#L800):

| Поле | Default | Для согласованной проверки запуска |
| --- | --- | --- |
| `tui.alternate_screen` | `auto` | `never` блокирует, `auto`/`always` допустимы |
| `tui.fullscreen_transcript` | `true` | `false` блокирует |
| `tui.copy_on_select` | `auto` | требуется явное эффективное `never` |

Все значения `alternate_screen`: `auto`, `always`, `never`; все значения
`copy_on_select`: `auto`, `always`, `never`. Отсутствие `copy_on_select` нельзя
выдавать за ручное копирование. Отсутствие ключа в отдельном слое не равно его
отсутствию в эффективной конфигурации.

Реальная загрузка default подтверждена
[`core/src/config/mod.rs:4788`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/core/src/config/mod.rs#L4788).

## Codex: layering и выбранный профиль

Канонический loader:
[`config/src/loader/README.md`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/config/src/loader/README.md),
[`loader/mod.rs:124`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/config/src/loader/mod.rs#L124).
Высокий приоритет поверх низкого: legacy MDM managed config → legacy managed file
→ CLI/session overrides → trusted project layers → selected user profile → user
config → enterprise cloud-managed bundle → system config. Имеются также packaged
defaults, managed requirements и ограничения точных значений. Disabled/untrusted
project layers присутствуют в описании, но не участвуют в эффективном merge.
Project discovery учитывает trust и непроектные настройки; простой обход родителей
и merge TOML не эквивалентен loader. Project-local denylist включает `profile`,
`profiles`, provider/endpoint и другие поля, но не перечисленные TUI keys
([`loader/mod.rs:84`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/config/src/loader/mod.rs#L84)).

`--profile NAME` выбирает `$CODEX_HOME/NAME.config.toml`, расположенный между user
и project layers; loader получает `user_config_profile`
([`loader/mod.rs:202`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/config/src/loader/mod.rs#L202)).
Несмотря на сохранённые описания `profile`/`profiles` в JSON schema, runtime
**отклоняет** legacy `profile = "NAME"`:
[`core/src/config/mod.rs:3539`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/core/src/config/mod.rs#L3539).
Следовательно, fixture `[profiles.NAME.tui]` из старого setup нельзя объявлять
проверкой фактически выбранной конфигурации 0.166.0.

## Codex: read-only RPC и ограничения его транспорта

`config/read` существует. Params: `{ "cwd": ABS_DIR, "includeLayers": true }`.
Response: `{ "config": {...}, "origins": {...}, "layers": [...] }`;
`includeLayers` default `false`, `cwd` optional. Без `cwd` ответ намеренно
thread-agnostic и исключает project layers.

Первоисточники:
[`protocol/v2/config.rs:390`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/app-server-protocol/src/protocol/v2/config.rs#L390),
[`config_manager_service.rs:130`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/app-server/src/config_manager_service.rs#L130),
[`config_processor.rs:111`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/app-server/src/request_processors/config_processor.rs#L111).
Ответ содержит произвольные settings; только OTEL exporter credentials явно
redacted в service. Нельзя печатать/сохранять сырой response, MCP/provider поля,
stderr или исключения, включающие конфигурацию. Нужна allowlist трёх TUI полей.

RPC read не равен read-only запуску сервера. `codex app-server --stdio` до запросов:

- инициализирует AuthManager и managed loader
  ([`app-server/src/lib.rs:599`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/app-server/src/lib.rs#L599));
- инициализирует sqlite state runtime
  ([`:672`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/app-server/src/lib.rs#L672));
- при corrupt DB или blocking file **перемещает** runtime DB в backup и повторяет
  init для fresh start
  ([`:1424–1468`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/app-server/src/lib.rs#L1424));
- запускает log DB/telemetry. Обычные runtime-логи сами по себе ещё не означают
  нарушения спецификации; recovery с перемещением DB требует отдельного ruling.

Существующий daemon теоретически позволяет избежать startup, но его безопасное
обнаружение/инициализация и соответствие будущей shell-инвокации не установлены.
Ни daemon, ни реальная конфигурация для этой проверки не использовались.

### Точечная проверка process-local isolation

Есть `CODEX_SQLITE_HOME`
([`state/src/lib.rs:144`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/state/src/lib.rs#L144)).
Это process-local env; он не выбирает CODEX_HOME и не меняет config layers.
Непустое значение resolve относительно launch cwd
([`core/src/config/mod.rs:276`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/core/src/config/mod.rs#L276)).
Однако порядок выбора sqlite home — **effective `cfg.sqlite_home` → env → CODEX_HOME**
([`:4329`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/core/src/config/mod.rs#L4329)).
`cfg.sqlite_home` уже может содержать managed exact requirement. Env не гарантирует
изоляцию startup DB, пока отсутствие effective sqlite_home не установлено.

Дополнительно явный `cfg.log_dir` задаёт local SQLite logs home, если managed
sqlite_home requirement отсутствует
([`:4342`](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/core/src/config/mod.rs#L4342)).
По точечно прочитанным config/mod.rs, state/lib.rs, app-server/lib.rs и
startup_config.rs независимого env для принудительного log/state relocation
не установлено. Это ограниченный source search, не утверждение об отсутствии во
всём дереве. Overrides `-c sqlite_home=...`/`-c log_dir=...` были бы конфигурационными
override и здесь не реализованы. Startup с одним CODEX_SQLITE_HOME пока нельзя
объявить полностью изолированным от пользовательских DB.

## iTerm2: `profile show` не содержит raw profile

[`it2core/Commands/ProfileCommand.swift:94`](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/it2cli/Sources/it2core/Commands/ProfileCommand.swift#L94):
`it2 profile show NAME --json` возвращает curated object с `guid`, `name`, `font`,
`font_size`, `background_color`, `foreground_color`, `transparency`, `blur`,
`cursor_color`, `selection_color`, optional `badge_text`. Цвета/blur сохраняются
как JSON-encoded strings, это не raw profile dictionary. **Keyboard Map отсутствует.**
Нельзя подменять этот ответ fixture с `Keyboard Map` и считать контракт проверенным.

`profile list --json` возвращает array `{ "guid": STRING, "name": STRING }`
([`:39–89`](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/it2cli/Sources/it2core/Commands/ProfileCommand.swift#L39)).
`findProfileGuid` берёт **первое** совпадение имени
([`:378–407`](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/it2cli/Sources/it2core/Commands/ProfileCommand.swift#L378));
launch обязан отдельно блокировать неоднозначные имена.
Подкоманд raw `get`/`dump` у `profile` нет: только list/show/apply/set.

Raw API `ListProfilesRequest` запрашивается внутри show, однако подходящего
существующего CLI-транспорта для raw ответа пока не подтверждено.
Существующий discovery читает defaults и DynamicProfiles, но индексирует их по
имени, теряя неоднозначность, и не доказывает фактические inherited runtime values.

Raw profile key `Keyboard Map` подтверждён
[`ITAddressBookMgr.h:319`](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/sources/Settings/Profiles/ITAddressBookMgr.h#L319).
Для согласованного профиля требуются Ctrl EN/RU entries `0x63`/`0x441`, mask
`0x40000`, keycode `0x8`, physical flag `0x1`, Action `11`, bytes `03`; Cmd mask
`0x100000`, Action `11`, bytes `1b 5b 39 39 3b 39 75`. Сравнивать семантику bytes,
игнорировать дополнительные Version/Apply Mode metadata. Это требование brief
и существующего profiles builder, **не новая live-проверка**. Глобальный
`CopySelection` должен быть boolean `false`; имеющийся preference reader пригоден.

## iTerm2: наблюдаемые session variables

[`PTYSession.m:3272`](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/sources/PTYSession/PTYSession.m#L3272):
`session.profileName` — имя исходного/применённого profile; для локально
переименованной divorced session ищется original profile. Это проверка имени,
не доказательство актуальных binding values.

[`PTYSession.m:7913`](https://github.com/gnachman/iTerm2/blob/7ce456b98db38d3f0bafd70ffec87752e69d5d58/sources/PTYSession/PTYSession.m#L7913):
`session.jobName` — display foreground process, предпочтительно глубочайший job
с stdin/stdout на session tty; не всегда самый глубокий дочерний процесс.
Fallback возможен при неизвестном tty/remote session; имеется iTermServer exec
window workaround. `codex` здесь может подтвердить наблюдаемый job, но не чтение
handoff/принятие задачи и не работу clipboard.

## Первичный блокер: разрешён отдельным ruling перед Task 2/3

Проверка должна относиться к **будущему вызову сохранённой shell-функции** через
interactive login zsh. Эта функция/startup могут выбрать иной CODEX_HOME,
`--profile` либо `-c` flags. Проверка родительского PATH и user TOML не устанавливает
этот контракт; даже config/read другого app-server отражает его собственные
startup overrides, а не произвольное будущее исполнение функции.

На момент первичного отчёта не было подтверждённого bounded механизма, сохраняющего
shell-функцию, учитывающего её effective overrides и проверяющего raw inherited
profile bindings без GUI mutation. Требуется решение контроллера о способе
read-only discovery/обоснованной границе поддерживаемой функции. Подмена defaults,
универсальный второй Codex loader и ослабление согласованной проверки не выполнены.

## Принятый bounded контракт реализации

Контроллер принял `task-2-constraints.md`/`config-ruling-advice.md` после отдельной
архитектурной проверки. Обычная инициализация app-server, **включая описанный выше
recovery SQLite**, разрешена как часть авторизованного запуска пользователя.
Это не filesystem-read-only операция; разработка выполняет только fake transport
и синтетические дочерние процессы с временным HOME.

`Runner.codex_config` создаёт один собственный process group, ждёт identity gate
в том же interactive login zsh из требуемого cwd, затем проводит
initialize → initialized → config/read. Ни thread/start, ни turn/start нет.
Идентичность проверяется до разрешения shell вызвать app-server. Общий deadline,
лимит stdout 1 MiB, stderr discard, cleanup только собственной группы.
Три TUI поля проверяются по каноническому merged response; остальной config не
сохраняется в findings/LaunchInspection. TOML resolver не добавлен.

Поддерживаются direct binary, точные canonical bodies поставляемого dispatcher,
restore и их цепочки, простой passthrough либо wrapper только с `--no-daemon`.
Известные bodies получает чистый `zsh -dfc`, загружающий только поставляемые файлы;
их сравнение включает вызываемые helper functions и предыдущий wrapper.
Для restore проверяется совпадение внешнего helper runtime с поставляемыми
исходниками. Substring-маркеры и неизвестные/profile-changing wrappers не
признаются совместимыми. Legacy выбранный profile — ошибка canonical resolver,
не повод реализовывать старую схему или добавлять новый выбор в launcher.

Идентичность содержит только executable/version, HOME/CODEX_HOME/ZDOTDIR,
fingerprint относящихся к запуску functions, restore root и выбранный Python.
`identity_guard(paths, identity)` повторно сравнивает это в shell реального запуска
перед исходным `codex -C ...`, без второго app-server и без глобального cache.
Task 3 обязан установить cwd **до** login startup и использовать проверенный zsh.

Профиль проверяется по уникальным live name/GUID и единственной совпадающей
материализованной записи `New Bookmarks`. Keyboard Map должен присутствовать
явно; недоступная inheritance блокирует запуск. `CopySelection` читается тем же
существующим preference reader. Второй inheritance resolver/SDK не добавлен.
Ограничение reader: snapshot не является прямым чтением runtime bindings; внешний
источник preferences с совпадающими GUID/name и устаревшим plist может остаться
неразличимым. Неподтверждённые ключи обнаружения внешнего источника в код не
добавлены; контроллер принял этот bounded reader для первой версии. Конкурентное
изменение профиля после проверки не покрывается атомарной гарантией.
