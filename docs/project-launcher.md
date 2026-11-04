# Панель проектов

Явно выбранная функция `project-launcher` добавляет кнопки в нативную нижнюю
Status Bar iTerm2. Кнопка открывает **новую активную вкладку в том же окне**:
обычная login shell в папке проекта. Повторный клик создаёт ещё одну вкладку.
Команды в текущую сессию не вводятся; агент автоматически не запускается.
Операции со списком проектов описаны в отдельном публичном навыке
[iterm2-projects](https://github.com/YarikMix/iterm2-utils/tree/main/skills/iterm2-projects).
[Статический вымышленный пример](examples/project-launcher.html).

Нужны macOS, zsh, **iTerm2 3.7.6** и выбранный существующий Python **3.11+** с
официальным модулем `iterm2`. Выберите его через `ITERM2_UTILS_PYTHON`, если
обычный Python не подходит; SDK должен импортироваться именно этим Python.
В iTerm2 включите Settings → General → Magic → Enable Python API и подтвердите
его запрос доступа вручную. CLI не устанавливает SDK, не запускает приложение
и не выдаёт разрешения. Неизвестная версия, недоступный API, неоднозначные
профили или непроверяемые session overrides блокируют установку до записей.

Создайте **свой локальный** JSON вне публичного репозитория. Имена, папки и
состав ваших проектов приватны; пример ниже содержит только вымышленные данные.
Папки должны уже существовать; CLI их не создаёт и ничего не клонирует.

```json
{
  "profiles": ["Default"],
  "projects": [
    {"id": "project-a", "name": "Проект A", "path": "/path/to/project-a"},
    {"id": "project-b", "name": "Проект B", "path": "/path/to/project-b"}
  ]
}
```

`profiles` — непустой список уникальных имён **существующих** профилей, в которых
нужна панель. Профили Codex/Claude включайте только явно и после их создания.
Одинаковые имена в inventory iTerm2 считаются конфликтом. `--parent-profile`
выбирает существующий обычный shell-профиль для наследования проектных профилей;
его custom command явно переопределяется login shell. Default profile не меняется.

`projects` сохраняет порядок кнопок. Непустой уникальный `id` задаёт стабильный
GUID: переименование и смена папки при прежнем id его сохраняют. `name` —
непустое уникальное имя кнопки и профиля без управляющих символов. `path` —
абсолютная существующая папка, не shell-команда. Неизвестные/повторные JSON-поля,
неправильные типы и повторные id/имена отвергаются без печати содержимого файла.

```sh
python3 -m iterm2_utils plan --agent codex --features project-launcher --parent-profile Default --project-launcher-config /path/to/projects.json --json
python3 -m iterm2_utils install --agent codex --features project-launcher --parent-profile Default --project-launcher-config /path/to/projects.json --dry-run --json
python3 -m iterm2_utils install --agent codex --features project-launcher --parent-profile Default --project-launcher-config /path/to/projects.json --json
python3 -m iterm2_utils update --json
python3 -m iterm2_utils doctor --json
python3 -m iterm2_utils uninstall --features project-launcher --dry-run --json
python3 -m iterm2_utils uninstall --features project-launcher --json
```

`--agent codex|claude|both` задаёт владельцев по общей модели пакета; кнопки
открывают shell. Флаг конфигурации без выбранной feature отвергается до discovery.
Bootstrap не выбирает эту функцию. `plan` и `--dry-run` читают и планируют без
записей. Чтобы **добавить ещё один проект**, отредактируйте локальный JSON и снова
выполните `plan`/`install` с этим флагом; отдельная CRUD-команда не нужна.
Сохраняйте id существующих проектов и ранее записанный parent profile.

Установка сохраняет нормализованный собственный конфиг с режимом `0600` в
`~/.config/iterm2-utils/iterm2-utils-project-launcher.json` и отдельный Dynamic
Profiles файл `iterm2-utils-project-launcher.json` в штатной папке iTerm2.
После установки исходный JSON можно удалить: повтор и update используют
собственную копию. Для изменения передайте новый локальный файл через флаг;
не редактируйте installed config/Dynamic Profiles файл напрямую. Оба защищены
whole-file CAS. Ресурсы и before/installed значения учитываются существующими
receipts и журналом транзакций; новые фоновые процессы не устанавливаются.

Панель сохраняет foreign components, их порядок и advanced layout settings,
добавляя собственные кнопки в порядке JSON. В исходных профилях меняются только
`Show Status Bar` и `Status Bar Layout`, учитываемые одним typed ресурсом;
глобальное положение становится Bottom. Остальные настройки и вкладки не
перезапускаются. Удаление одного agent consumer сохраняет панель другого:
`uninstall --agent codex --features project-launcher`.

При конфликте сохраните пользовательские правки и сравните их с собственным
receipt/backup локально. Верните только конфликтующее owned значение к
подтверждённому installed состоянию либо сохраните его и отложите удаление;
CLI не предлагает force overwrite. Поздняя правка любого из двух полей панели
блокирует весь launcher checkpoint при uninstall. Перед удалением GUID свежий
inventory проверяет все persistent profiles и live/buried sessions, включая
скрытые ссылки и прямую привязку. Закройте нужные вкладки самостоятельно либо
устраните свои внешние ссылки и повторите команду. Неизвестное покрытие сохраняет
ресурс и receipt. CLI не закрывает процессы и не удаляет foreign components.

Timeout после отправки native write означает неопределённый результат: durable
intent остаётся для recovery при следующей изменяющей команде. Не повторяйте
native write вручную вслепую. Recovery выполняется до планирования и проверки
receipt. После отката прерванной первой установки update/uninstall могут сообщить
об отсутствии receipt; для установки повторите install с исходным JSON.
Plan, dry-run и doctor восстановление не запускают. Native readback обязателен, но не доказывает
визуальную приёмку. Гонка после последнего inventory остаётся возможной.

Если папка стала недоступна **после установки**, штатный iTerm2 предупреждает и
открывает home; фоновой проверки доступности нет. Для нового plan/update
папка в новом конфиге должна существовать; прежний путь можно заменить либо
убрать проект из JSON. Узкое окно может скрывать компоненты: меню
**Profiles** остаётся запасным входом. Браузер и localhost установленной панели
не нужны.

Разработка проверяется только на TemporaryDirectory/fake SDK, включая отдельный
child protocol. Историческая ручная проверка native панели на 3.7.6 относится
к формату, а не к этому установщику. **Live install/update/uninstall нового CLI,
видимость кнопок и клики на реальном состоянии пользователя не проверены.**
[Матрица совместимости](compatibility.md).
