# Оформление вкладки по репозиторию

`appearance` — восьмая opt-in функция, только для Codex в macOS/zsh. Она назначает
цвет и одну составную иконку своей сессии iTerm2 при старте интерактивной shell и
интерактивном запуске Codex, включая resume/fork и restore. Используется физическая
папка вызывающей shell, а не аргумент `--cd` или текст разговора. Обычный `cd` и
служебные команды (`--help`, exec, review, login) оформление не меняют. Без
совпадения или при недоступном внешнем диске сохраняется текущая пара. Ошибка API
не отменяет запуск Codex и не меняет его код выхода.

Создайте локальный JSON (не добавляйте личные пути в публичный checkout):

```json
{"projects": [{"root": "/path/to/repo", "color": "#65A85A", "icon": "android-mail"}]}
```

Корневое поле только `projects`, список непустой. Каждое правило содержит ровно
три строки: абсолютный `root`, `color` вида `#RRGGBB`, `icon` — встроенное имя либо
абсолютный путь к своему `.png`. Семь встроенных имён: `ios`, `android`, `kotlett`,
`ios-mail`, `ios-cloud`, `android-mail`, `android-cloud`. Это оригинальные условные
символы телефона, робота, котлеты, почты и облака, а не официальные логотипы.
Прозрачная PNG объединяет два символа в единственном custom icon iTerm2; SVG и
[MIT attribution](../THIRD_PARTY_NOTICES.md) поставляются вместе с ней.

Корень совпадает с собой и подкаталогами; похожие соседние имена не совпадают.
Для вложенных правил выигрывает самый длинный физический корень. Симлинки
нормализуются; доступные корни и предки сравниваются по device/inode, поэтому
регистровые алиасы case-insensitive APFS совпадают, а дубли физического корня
отклоняются. Case-sensitive тома сохраняют различие имён. Недоступный target не
создаётся и не сканируется. Свой PNG должен быть доступен при install: до 16 MiB,
до 4096 пикселей по каждой стороне, до 128 MiB decoded scanlines; структура и
пиксельный поток проверяются до записи. SVG/URL вместо своего PNG не принимаются.

Выберите существующий Python **3.11+ с модулем `iterm2` именно в нём**. Для
нестандартного интерпретатора задайте абсолютный `ITERM2_UTILS_PYTHON` на всех
CLI-командах настройки. Discovery проверяет импорт SDK, но не открывает API.
Пакет не выполняет pip и не загружает картинки при старте shell.

```sh
python3 -m iterm2_utils plan --agent codex --features appearance --appearance-config /path/to/rules.json --json
python3 -m iterm2_utils install --agent codex --features appearance --appearance-config /path/to/rules.json --dry-run --json
python3 -m iterm2_utils install --agent codex --features appearance --appearance-config /path/to/rules.json --json
python3 -m iterm2_utils doctor --json
```

Plan/dry-run ничего не пишут, не запускают API, GUI или shell startup. Install
копирует нормализованные правила в config `appearance.json`, свои PNG — в data
`appearance/icons/<sha256>.png`, встроенные — в `data/current/assets/appearance`.
Исходные JSON/PNG и checkout после установки runtime не нужны. Путь исходного
JSON в receipt не сохраняется. Bootstrap skill не выбирает функции.

`appearance_api` остаётся pending после записи файлов. В iTerm2 Settings →
General → Magic включите Enable Python API и подтвердите запрос авторизации
человеком. Затем из обычной собственной сессии iTerm2 выполните:

```sh
python3 -m iterm2_utils doctor --live --json
python3 -m iterm2_utils reconcile --step appearance_api --json
```

Это ограниченная read-only проверка API для явного UUID сессии; doctor не снимает
pending, reconcile снимает его только после успешной проверки. Проверка не
доказывает визуальное применение или переходы Automatic Profile Switching (APS).
Противоречащие ID и tmux отклоняются; активная вкладка не используется как запасной
вариант. Разрешения/TCC остаются действиями человека; отказ не обходится.

Обновление использует установленный набор, без исходного JSON/PNG. Для CLI
maintenance нужен новый checkout/release пакета:

```sh
python3 -m iterm2_utils update --dry-run --json
python3 -m iterm2_utils update --json
python3 -m iterm2_utils uninstall --agent codex --features appearance --dry-run --json
python3 -m iterm2_utils uninstall --agent codex --features appearance --json
```

Повторный install без `--appearance-config` использует установленные правила;
первый без них завершается conflict до записи. Новый JSON при plan/install
явно заменяет собственный набор. Изменённые пользователем owned файлы и чужие
поля сохраняются с conflict. Старые hash-копии своих PNG остаются owned до
uninstall. Удаление убирает только неизменённые owned ресурсы appearance, общие
shell/runtime сохраняются для других функций; generic JSON engine может оставить
пустой `{}`. Уже открытые вкладки не сбрасываются и не перезапускаются.

Helper меняет только сессионные Tab Color/use color и Custom Icon Path/mode,
сохраняя профиль, Default и заголовок. Короткоживущий observer отслеживает job/profile
для APS на старте и возврате Codex, имеет жёсткую границу 2.8 секунды. Перед стартом
Codex shell ждёт готовности подписок; без совпадения helper сначала снимает только
текущие цвет/иконку, включая light/dark варианты и ручные изменения. Снимок хранится
в переменной собственной native-сессии, привязан к этому запуску и удаляется при
возврате. Он восстанавливается после APS; обычный `cd` ничего не назначает. Ошибка
или deadline освобождают запуск без изменения его аргументов и кода выхода;
при недоступном API защитить оформление от стороннего APS нельзя. Нет демона,
chpwd hooks, постоянного наблюдателя, MCP или agent hooks. Это оставляет поздние
APS-переходы вне окна непроверенным ограничением. Пять сочетаний, читаемость
значков и сохранение пары при штатном APS проверены в живых временных вкладках;
темы, picker restore и отключённый SSD отдельно отмечены как не проверенные live
в [фактической матрице](compatibility.md). Fixture-тесты эту приёмку не заменяют.
