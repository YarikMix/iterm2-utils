# iterm2-utils

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
| `notifications` | Завершение/запрос внимания, переход к своей вкладке | Python, terminal-notifier |
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
агента с новым skill. Матрица живой приёмки остаётся отдельной проверкой.

```sh
python3 -m unittest discover -v
python3 tools/check_skill.py
```
