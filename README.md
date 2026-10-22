# iterm2-utils

**v0.1.0-beta.1** — публичная beta для macOS + zsh.
[Матрица совместимости и непроверенные live-сценарии](docs/compatibility.md).

Выборочная настройка iTerm2 для Codex CLI и Claude Code: ручное копирование,
статусы, уведомления, восстановление диалогов, MCP, shell integration и hotkeys.
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
| `status` | Статус конкретной вкладки, Claude через штатный cc-status | Python, поддерживаемый iTerm2 |
| `notifications` | Завершение/запрос внимания, переход к своей вкладке | Python 3.11+, terminal-notifier, it2, osascript |
| `restore` | Выбор диалога Codex для продолжения; только Codex | Python, fzf, Codex --no-daemon |
| `mcp` | Доступ выбранного агента к тексту терминала | uvx, серверный Python 3.12+, Python API/разрешение |
| `shell` | Штатные отметки команд и навигация zsh в iTerm2 | — |
| `shortcuts` | Только выбранные сочетания в профиле агента | Проверенная совместимость для Alt+Enter |

Зависимости выбранных функций нужно перечислить до установки через существующий
пакетный менеджер. CLI не ставит отсутствующие агенты/Peekaboo автоматически.
Отсутствие Python 3.11+ — prerequisite установщика, а не повод ставить второго
агента. Подробности: [features](skills/iterm2-setup/references/features.md).

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
