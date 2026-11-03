# iterm2-utils

**v0.1.0-beta.1** — публичная beta для macOS + zsh.
[Матрица совместимости и непроверенные live-сценарии](docs/compatibility.md).

Выборочная настройка iTerm2 для Codex CLI и Claude Code: ручное копирование,
статусы, уведомления, восстановление диалогов, MCP, shell integration, hotkeys
и оформление вкладки по репозиторию.
Первая версия поддерживает macOS + zsh. Установщик использует Python **3.11+** и
стандартную библиотеку; корпоративные сервисы и личные файлы автора не нужны.

Передайте коллеге одно сообщение для его агента:

> Настрой мне iTerm2 с https://github.com/YarikMix/iterm2-utils. Получи репозиторий,
> прочитай skills/iterm2-setup/SKILL.md и выполни диагностику. Уточни, какие
> возможности для установленных у меня Codex/Claude я хочу подключить, затем
> настрой только выбранное и проверь результат. Нужные ручные шаги объясни.

Агент может прочитать skill непосредственно из checkout: обновление списка skills
в текущей сессии для этого не требуется. Чтобы сделать skill доступным впоследствии:

```sh
git clone https://github.com/YarikMix/iterm2-utils.git
cd iterm2-utils
python3 --version  # требуется >=3.11
python3 -m iterm2_utils bootstrap-skill --agent codex --dry-run --json
python3 -m iterm2_utils bootstrap-skill --agent codex
```

Выберите `--agent claude` или `--agent both`, если нужны соответствующие копии.
Bootstrap устанавливает **только skill**, не включает ни одной функции и не
устанавливает второго агента. Codex получает `${CODEX_HOME:-~/.codex}/skills/iterm2-setup`,
Claude — `~/.claude/skills/iterm2-setup`, вместе с публичными references. Пути
берутся из выбранного HOME/CODEX_HOME, а не из фикстур разработчика. Чужая папка
или изменённый файл вызывают conflict; собственная версия обновляется по отдельному
receipt в data/bootstrap-skill. Для обновления skill повторите bootstrap после
обновления checkout. Текущая сессия может потребовать обновления обнаружения skills.

Формат и discovery: [Codex skills](https://developers.openai.com/codex/skills/),
[Claude skills](https://code.claude.com/docs/en/skills). Codex также поддерживает
общий каталог `~/.agents/skills` — это альтернативное размещение, не вторая копия
поверх bootstrap. Для Claude используется его штатный `~/.claude/skills`.

Для поручения задачи самостоятельному Codex в новой вкладке есть отдельный
[iterm2-launch](skills/iterm2-launch/SKILL.md). Установка только для Codex:

```sh
python3 -m iterm2_utils bootstrap-skill --skill iterm2-launch --agent codex --dry-run --json
python3 -m iterm2_utils bootstrap-skill --skill iterm2-launch --agent codex
```

Без `--skill` bootstrap по-прежнему копирует только `iterm2-setup`. Копии навыков
и их receipts независимы; bootstrap не включает функции терминала. Для запуска
нужны macOS, zsh, Python 3.11+ с официальным модулем `iterm2` именно в этом
Python, доступный iTerm2 Python API и совместимый bundled `it2` (контракт
проверен по v3.7.6) и **Codex 0.166.0**. Другие версии Codex блокируются как
непроверенные. Профиль должен уже существовать с совместимыми Cmd+C/Ctrl+C EN/RU,
`CopySelection = false`; эффективные TUI-настройки Codex должны сохранять
alternate screen (`auto`/`always`), fullscreen transcript и `copy_on_select = never`.
При блокере используйте `iterm2-setup` с явно выбранными функциями, например
`clipboard`. Launch ничего не устанавливает, не ищет чужие Python-окружения и не выдаёт
разрешения; restore и его receipt не требуются. SDK импортируется лениво только
для `launch-codex`; setup/bootstrap и остальные команды его не требуют.
Проверенная живая версия SDK: **2.23** (Python 3.13.7, Codex 0.166.0).
Фактические результаты handoff/resume и ограничения — в
[матрице приёмки](docs/superpowers/validation/2026-11-01-launch-api-resume/acceptance.md).

В checkout или распакованном релизе один раз выберите доступный `python3`
(либо явно выбранный пользователем Python), сохраните его абсолютный
`sys.executable` и проверьте SDK именно им. Не разыменовывайте symlink virtualenv
до базового Python и не сохраняйте вместо него shim менеджера окружений:

```sh
launch_python="$(python3 -c 'import os, sys; p = sys.executable; assert os.path.isabs(p); print(p)')" &&
"$launch_python" -c 'import sys; assert sys.version_info >= (3, 11); import iterm2; print(sys.executable)' &&
"$launch_python" -m iterm2_utils launch-codex --help
```

При ошибке остановитесь до создания вкладки и сообщите выбранный Python и
недостающий prerequisite. Каждая внешняя проверка ограничена 10 секундами средствами
вызывающего инструмента. В отдельных tool-вызовах передавайте сохранённый абсолютный
путь заново: shell-переменные между ними не сохраняются. При смене cwd/PATH повторите
проверку импорта и help тем же Python в контексте запуска. Установка SDK по явной
просьбе пользователя — отдельное действие с повторной проверкой после установки.

Затем тем же Python выполните ровно один режим:

```sh
"$launch_python" -m iterm2_utils launch-codex --window WINDOW_ID --profile PROFILE_NAME --cwd ABS_DIR --handoff ABS_FILE --json
"$launch_python" -m iterm2_utils launch-codex --window WINDOW_ID --profile PROFILE_NAME --cwd ABS_DIR --resume SESSION_UUID --json
```

`--window`, `--profile`, `--cwd` обязательны; ровно один из `--handoff` / `--resume`.
CLI получает конкретный ID окна. Скилл выбирает его по приоритету: явное указание
пользователя, затем согласованная привязка родительской сессии, затем единственное
окно полного валидного API-инвентаря, если runtime ID родителя отсутствует или не
найден. В последнем случае вопрос не нужен. При нескольких окнах без установленного
родителя или противоречащей привязке требуется уточнение; ноль окон и ошибка API
блокируют выбор. Недоступное явно выбранное окно не заменяется другим автоматически.
Фокус, название вкладки и скриншот не определяют цель. Перед запуском выбранный ID
перепроверяется; для выбора по единственности должно оставаться ровно то же окно.
Появилось второе — уточните выбор, цель исчезла — остановите попытку без подмены.
Это повторная проверка, не атомарная защита от конкурентного изменения окон.
`cwd` — существующий абсолютный каталог, `handoff` — читаемый обычный файл по
абсолютному пути, не symlink. Для нового поручения навык готовит уникальные
handoff/ack и отдельно проверяет свежее подтверждение по
[формату handoff](skills/iterm2-launch/references/handoff.md).

Для продолжения нужен точный UUID интерактивного диалога в эффективном
`CODEX_HOME/sessions`; нет `--last`, picker, fork или нового prompt. Навык
сопоставляет относящуюся историю, берёт cwd из подтверждённого transcript и
передаёт другой cwd только по просьбе пользователя. Если нужный диалог уже открыт,
сообщает его вкладку; дубль — по явной просьбе. См. [resume](skills/iterm2-launch/references/resume.md).

Официальный SDK создаёт одну вкладку через `Window.async_create_tab` с профилем и
custom command при создании. Команда не вводится в работающий Codex. Через штатную
функцию в interactive login zsh выполняется `codex -C ABS_DIR <handoff prompt>`
либо `codex resume SESSION_UUID -C ABS_DIR` без поручения. `CODEX_RESTORE_NO_AUTO=1`
задаётся до login shell только новому процессу. Настройки/model/endpoint и защиты
сохраняются; `--no-alt-screen` не добавляется. Поддерживаются direct binary,
точные поставляемые dispatcher/restore и их цепочки, простой passthrough и wrapper
только с `--no-daemon`; неизвестные или меняющие профиль wrappers блокируются.

Подключение и каждая preflight-операция ограничены 10 секундами; создание и
подтверждение делят общий бюджет 30 секунд. Handoff ack ожидается отдельно до
120 секунд. Нет SDK/API/доступа — `blocked`, без автоматической установки и
fallback к `it2 tab new --command`, send/run/send_text.

Проверка effective config выполняет обычную инициализацию app-server и
`config/read` в выбранном login shell/cwd, без thread/turn start. Она может
создавать штатные state/log/recovery SQLite-файлы Codex и выполнять shell startup;
это не filesystem-read-only команда. Служебное окружение login shell не получает
родительские `ITERM_SESSION_ID`/`TERM_SESSION_ID`; окружение родителя сохраняется,
его цвет/иконка и appearance snapshot до создания вкладки не изменяются. Новая
вкладка получает собственную привязку iTerm2 и штатное оформление. Перед запуском
повторно проверяется identity
shell/executable/config-home. Профиль сверяется с материализованным preference
snapshot по уникальным name/GUID; устаревший внешний plist и конкурентное изменение
runtime bindings не исключены. Подробнее — [границы проверки](docs/compatibility.md).

| JSON `status` / exit | Что подтверждено |
| --- | --- |
| `launched` / 0 | В нужном окне найден единственный созданный session ID, совпадают profile name/GUID, наблюдается job `codex` с полной ожидаемой командой выбранного режима |
| `created_unverified` / 3 | Известна созданная вкладка/сессия, но наблюдений для `launched` недостаточно |
| `unknown` / 3 | Исход создания неопределён; известные ID сохранены, если доступны |
| `blocked` / 2 | Prerequisite не выполнен; вкладка не создаётся |

`mode=launch_codex`, `launch_mode=handoff|resume`, `resume_session_id` (UUID
диалога или null), `window_id`, `tab_id`, `session_id`, `profile` и findings возвращаются
без handoff, полных настроек/экрана и stderr внешних команд. `launched` не доказывает
получение поручения, восстановление истории или работу clipboard. `session_id` —
ID терминала iTerm2, не UUID диалога Codex. Для resume ack не нужен: перед заявлением
«диалог восстановлен» навык отдельно наблюдает историю/идентификатор в точной
целевой вкладке read-only. Без этого: «команда resume запущена, восстановление
истории не подтверждено». При неопределённом исходе сначала
осмотрите известные ID: не повторяйте запуск/поручение автоматически, не закрывайте
вкладку и не завершайте процессы пользователя. Новая сессия, handoff и ack остаются
для диагностики. Живая приёмка обоих режимов и копирования — отдельный этап;
[поведенческие проверки](https://github.com/YarikMix/iterm2-utils/blob/main/docs/superpowers/validation/2026-11-01-launch-api-resume/skill-results.md)
используют только вымышленные текстовые сценарии и не доказывают живой запуск.

При ручном запуске CLI сначала выберите функции:

```sh
python3 -m iterm2_utils doctor --json
python3 -m iterm2_utils plan --agent codex --features clipboard,shell --json
python3 -m iterm2_utils install --agent codex --features clipboard,shell --json
python3 -m iterm2_utils doctor --json
```

`--agent codex|claude|both` задаёт агентов, `--features` — явный CSV-список.
Пустой/неизвестный выбор отклоняется без инспекции. Для `shortcuts` обязателен
`--shortcuts ctrl-v-ru,alt-enter,ctrl-q,resume` с нужным подмножеством; `ctrl-q`
может прервать работу/выйти. `--parent-profile NAME` выбирает существующий
родительский профиль (по умолчанию Default). План и `--dry-run` не изменяют
настройки, не открывают GUI, не выполняют shell startup и не меняют hook trust.
Обычная установка меняет реальные выбранные настройки пользователя.

| Функция | Что включается | Зависимости сверх iTerm2/zsh и выбранного агента |
| --- | --- | --- |
| `clipboard` | Cmd+C/Ctrl+C EN/RU, без автокопирования при выделении; только Codex | — |
| `status` | Native working/waiting/done конкретной вкладки; error зависит от источника событий | Python 3.11+, для Codex iTerm2 3.7.6+ с cc-status/it2 |
| `notifications` | Завершение/запрос внимания, переход к своей вкладке | Python 3.11+, terminal-notifier, it2, osascript |
| `restore` | Выбор диалога Codex для продолжения; только Codex | Python, fzf, Codex --no-daemon |
| `mcp` | Доступ выбранного агента к тексту терминала | uvx, серверный Python 3.12+, Python API/разрешение |
| `shell` | Штатные отметки команд и навигация zsh в iTerm2 | — |
| `shortcuts` | Только выбранные сочетания в профиле агента | Проверенная совместимость для Alt+Enter |
| `appearance` | Цвет и составная иконка своей вкладки при старте shell, обычном `cd` и запуске Codex; только Codex | Выбранный Python 3.11+ с SDK `iterm2`, Python API/разрешение |

Зависимости выбранных функций нужно перечислить до установки через существующий
пакетный менеджер. CLI не ставит отсутствующие агенты/Peekaboo автоматически.
Отсутствие Python 3.11+ — prerequisite установщика, а не повод ставить второго
агента. Подробности: [features](skills/iterm2-setup/references/features.md).

Оформление требует совпадения устройства терминала вызывающей shell с `tty`
явно выбранной сессии iTerm2: одного унаследованного UUID недостаточно. Без tty,
при несовпадении или ошибке API пропускаются все изменения, включая snapshot;
успешный API probe подтверждает только доступ. Вложенная интерактивная shell в том
же терминале работает штатно; pipes supervisor этому не мешают. После обновления
нужна свежая shell: уже открытая может вызывать старый runtime без новой защиты.
Старый caller безопасно пропускает оформление только при вызове нового helper без
терминала. Установщик не перезапускает рабочие shell.

Восьмая опция [`appearance`](docs/repo-appearance.md) выбирается явно через
`--features appearance --appearance-config /path/to/rules.json` в plan/install.
Правила задают абсолютный root, `#RRGGBB` и одно из девяти встроенных имён либо свой
PNG: `ios`, `android`, `kotlett`, `ios-mail`, `ios-cloud`, `android-mail`,
`android-cloud`, `chrome-mail`, `chrome-cloud`. В шести сочетаниях платформа крупнее,
а фирменный значок Почты (белая `@` на синем) или Облака (белый контур на синем)
расположен справа снизу; веб-пары используют официальный цветной знак Chrome.
Базовые `ios`, `android`, `kotlett` сохранены. Прозрачные PNG 128×128 и SVG
поставляются офлайн; происхождение и права на брендовые изображения — в
[notices](THIRD_PARTY_NOTICES.md). Исходные JSON/PNG и checkout runtime после установки не нужны. Bootstrap
appearance не включает. Обычный `cd` в зарегистрированный корень или подкаталог
меняет пару, выход из всех корней отключает Tab Color и скрывает custom icon,
учитывая base/light/dark варианты без назначения «дефолтного» RGB. Это обновление
существующего `appearance`, без нового флага или схемы JSON. Перед установкой
проверьте SDK `iterm2` именно в выбранном Python; `ITERM2_UTILS_PYTHON` выбирает
абсолютный путь существующего интерпретатора. `appearance_api` остаётся pending
до успешного read-only reconcile собственной сессии. Новые cd/reset, APS,
темы и читаемость значков требуют отдельной live-приёмки;
API connectivity этого не подтверждает. Полный порядок
plan/install/doctor/update/uninstall и JSON schema — в связанном руководстве.

Новая установка выбранного `status` для Codex использует штатный `cc-status --agent
codex` из проверенного bundle iTerm2 3.7.6+; утилиты приложения не копируются в
runtime. Она даёт native `working`, `waiting`, `done` и штатный переход к `idle`.
В проверенной схеме Codex **0.163.0** ровно 12 событий: `StopFailure`, `Notification`
и `PostToolUseFailure` отсутствуют. Поэтому автоматический `error` при ошибке API
Codex не поддержан; поддержка renderer в iTerm2 этого не доказывает. Для неизвестной
версии doctor сообщает непроверенный источник ошибки (`codex_error_event: limited`).
Это неблокирующее ограничение, независимое от готовности API и файлов.

Штатного готового установщика Codex в меню iTerm2 нет: используйте выбранные
plan/install пакета. Claude по-прежнему настраивается через Install/Reinstall
Claude Code Integration, только API, hooks и Session Status, без Workgroup и
Auto-Enter. Новые hooks могут потребовать новой сессии и подтверждения доверия
человеком. `status` не включает notifications, restore, MCP и другие функции.

Полный внешний набор native Codex hooks переиспользуется без ownership и второго
writer; дополнительные преобразования input/compact нашего adapter для него не
обещаются. Активный внешний legacy plugin по умолчанию остаётся **legacy reused**,
это ещё не cc-status. Его явная миграция — существующий `--adopt-legacy` при
plan/install; принадлежащий пакету beta.1 status мигрирует через update.

`clipboard` задаёт `tui.copy_on_select = "never"` и общую настройку iTerm2
`CopySelection = false`. Только этот выбор отключает автокопирование. Профиль
Codex использует `&codex`, никогда `claude`; профиль Claude hotkeys не содержит
Codex C-bindings. Профили наследуют выбранные цвета/шрифты/keyboard map, не меняют
Default. Cmd+V остаётся штатной вставкой. Большие объёмы текста могут столкнуться
с гонкой завершения копирования; задержка вставки и автофокус не устанавливаются.
Named Codex `[profiles.<name>.tui]` overrides диагностируются отдельно.

MCP — самостоятельная опция: `iterm2-observe` использует ровно
`uvx --with 'mcp<2' mcp-server-iterm2==0.1.1`. Установщику достаточно Python 3.11+,
серверу нужен **3.12+**; uvx при первом запуске может загрузить пакет и Python.
Codex регистрируется в `$CODEX_HOME/config.toml`, Claude — штатным CLI user scope
в `~/.claude.json`. Чужой/несовпадающий сервер не заменяется; совпадающий чужой
сервер не становится собственностью пакета. Live probe проверяет initialize,
allowlist инструментов и list_sessions, не отправляет команды в терминал.
Неизвестный формат вывода/инструмент блокирует готовность. Вывод чужих settings,
MCP env и auth не попадает в публичную диагностику.

После install прочитайте `findings` и `ui`: запись настроек не доказывает работу.
`ready` в plan означает готовность плана; успешный checkpoint означает сохранённые
ресурсы, а живую работу проверяют отдельно. Установка фиксирует доступные функции
отдельно: ошибка одной не отменяет уже завершённую независимую функцию.
Peekaboo пригоден только при наличии подключённого разрешённого инструмента в
текущем агенте; установленный бинарник этого не доказывает. При отсутствии/отказе
нужен ручной шаг, без osascript или обхода разрешений. Системные диалоги и доверие
hooks подтверждает человек. Точную навигацию описывает [UI reference](skills/iterm2-setup/references/ui.md):
Profiles открывает новую вкладку; Session → Edit Session → Use Selected Settings
применяет профиль к существующей. Агент не перезапускает пользовательскую сессию.

После ручного шага выполните `python3 -m iterm2_utils reconcile --step CODE --json`
с кодом из `ui`, затем `doctor --live --json` для выбранных runtime/MCP-проверок.
«Готово» со слов пользователя не снимает pending; неуспешная проверка оставляет его.
Новые hooks/регистрация могут требовать новой сессии, которую запускает пользователь.

Обновление и удаление через тот же CLI:

```sh
python3 -m iterm2_utils update --dry-run --json
python3 -m iterm2_utils update --json
python3 -m iterm2_utils uninstall --features clipboard --dry-run --json
python3 -m iterm2_utils uninstall --features clipboard --json
```

Повторная установка идемпотентна. Update сохраняет выбор из receipt; uninstall
восстанавливает только неизменённые собственные значения, сохраняет общие ресурсы
нужные оставшимся функциям и чужие/изменённые записи. Полный backup поверх конфига
не восстанавливается. Без валидного receipt удаление/обновление не разрешено.
Распознанный legacy можно принять только явным `--adopt-legacy`; конфликт не
даёт разрешения переписать произвольную настройку. См. [troubleshooting](skills/iterm2-setup/references/troubleshooting.md).

Пути учитывают абсолютные `ZDOTDIR`, `CODEX_HOME`, `XDG_CONFIG_HOME`,
`XDG_DATA_HOME`, `XDG_CACHE_HOME`; относительные overrides игнорируются. Claude
settings: `~/.claude/settings.json`. Runtime лежит в versioned data/releases со
стабильным current; receipts/backups отделены от очищаемого cache.
`ITERM2_APP` задаёт проверяемый app bundle; без него проверяются `/Applications/iTerm.app`
и `~/Applications/iTerm.app`. iTerm2 не запускается discovery. Exit codes: `0` —
нет блокеров, `2` — conflict/missing_dependency/unavailable, `3` — pending_ui/new_session.

Совместимость Alt+Enter проверена по исходникам/документации только для Codex
0.163.0 и Claude Code 2.1.308. Другие версии и custom TUI keymap требуют проверки.
Версии и происхождение внешнего кода: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
и [sources.lock.json](sources.lock.json).

Проверено разработчиком: unittest на TemporaryDirectory HOME, fake Runner и
адаптерах — выбор функций, ownership/CAS, update/uninstall, pending/reconcile,
bootstrap и сохранность чужих данных. Структурный validator проверяет skill и
references. Это не живая приёмка и не проверка поведения модели: попытка свежего
изолированного Claude baseline остановилась на отсутствии доступной авторизации.
Не проверены живые GUI/TCC, hook trust, работа в реальных сессиях и полный путь
агента с новым skill. Живые сценарии перечислены как **непроверенные** в [beta-матрице](docs/compatibility.md).

```sh
python3 -m unittest discover -s tests -t . -v
/bin/zsh tests/test_codex_shell.zsh
/bin/zsh tests/test_appearance_shell.zsh
/bin/zsh tests/restore/test_codex.zsh
python3 tools/check_sources.py
python3 tools/check_skill.py
python3 tools/check_export.py
python3 tools/build_release.py --destination dist
```

Beta-архив содержит явный список исходников, runtime, skill, проверок и лицензий;
локальные настройки, fixtures с состоянием, история, receipts и auth не входят.
SHA-256 файл рядом с архивом ссылается только на имя ассета: после скачивания
проверьте `shasum -a 256 -c iterm2-utils-v0.1.0-beta.1.tar.gz.sha256`.
Для запуска распакуйте архив и перейдите в `iterm2-utils-v0.1.0-beta.1`;
команды CLI и bootstrap такие же, как из checkout. Подключённый runtime после
установки не зависит от исходного checkout. Лицензии: [MIT](LICENSE) для кода
пакета и [отдельные условия vendored-компонентов](THIRD_PARTY_NOTICES.md).

Выбор хранится отдельно для каждого агента. Например, после
`install --agent codex --features clipboard,status` можно выполнить
`plan --agent claude --features notifications,mcp --json`, затем такой же `install`:
Codex сохранит только clipboard/status, Claude получит только notifications/MCP.
Повторный install добавляет выбранные функции и hotkeys только указанным агентам.
`selection.agent_features` и `selection.agent_shortcuts` показывают точный выбор;
верхние `features`/`shortcuts` — его объединение. Старый receipt читается с исходным
выбором для всех записанных в нём агентов. Update сохраняет эти пары.
`uninstall --agent claude --features notifications` удаляет только уведомления
Claude; без `--agent` удаление касается указанной функции у всех выбранных агентов.
Общие runtime/profiles/shell сохраняются, пока нужны оставшимся потребителям.

Для hooks и restore требуется проверенный **runtime Python 3.11+**. Если первый
`python3` в PATH слишком старый, задайте абсолютный `ITERM2_UTILS_PYTHON` при plan,
install, update и doctor. Версия проверяется; один выбранный путь записывается в
hooks и оболочку restore. Изменение пути при update заменяет собственные hooks
без дублирования. Clipboard/shell не требуют runtime Python сверх интерпретатора,
которым уже запущен установщик. Уведомления требуют **terminal-notifier, it2 и
osascript**; отсутствие любого транспорта блокирует только зависимые функции.

Обнаруженный сторонний terminal-notifier handler или внешний Codex status plugin
вызывает `foreign_notifications`. Можно оставить существующие уведомления,
не выбирая функцию пакета. Для осознанного сосуществования сначала добавьте
`--coexist-notifications` к plan, затем к install: выбор сохраняется для update только у указанных агентов,
чужие handlers сохраняются, возможны два баннера. Этот флаг не удаляет стороннюю
интеграцию и не заменяет отдельный `--adopt-legacy`.

Doctor читает ресурсы receipt, зависимости, активные hooks и MCP-регистрации.
Отсутствующий или изменённый owned ресурс, сломанный current и несовпадающая
регистрация отражаются отдельными findings без записи файлов. `doctor --live`
проверяет только выбранных потребителей: Codex-only не требует Claude integration,
MCP-only не зависит от Session Status. Без receipt doctor сообщает обнаруженные
возможности; он не предлагает включить невыбранные функции. Чистая offline
диагностика не подтверждает живую доставку уведомлений или API-связь.
`doctor` отдельно сообщает `status_backend`, `native_status_capability` и
`codex_error_event`. `doctor --live` читает только get-status явного UUID и
принимает `""`, `idle`, `working`, `waiting`, `done`, `error`, не печатает детали
и не запускает cc-status. Согласованные TERM_SESSION_ID/ITERM_SESSION_ID обязательны,
если обе переменные заданы; TMUX в этой миграции не поддерживается. Доступный API
не доказывает доставку hooks или наличие источника `error`. Живая приёмка этой
миграции и новый CI-прогон не заявляются: изолированный Mac-контур недоступен.
