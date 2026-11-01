# Надёжный launch-codex с handoff и resume — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Execution:** Завершено 02.11.2026; [фактические результаты и ограничения](../validation/2026-11-01-launch-api-resume/acceptance.md).

**Goal:** Исправить запуск Codex через настоящий custom command iTerm2 и добавить восстановление точного диалога без нового поручения.

**Architecture:** Сохранить существующие preflight, shell builder и read-only наблюдение. Изолировать ленивый официальный SDK в одном адаптере создания вкладки; CLI выбирает handoff/resume, общий verifier проверяет argv выбранного режима. Скилл отдельно подтверждает получение handoff либо восстановление истории.

**Tech Stack:** macOS, zsh, Python 3.11+, unittest, asyncio, официальный Python SDK iterm2, bundled it2 для наблюдения; Codex 0.166.0.

**Spec:** [2026-11-01-launch-api-resume-design.md](../specs/2026-11-01-launch-api-resume-design.md). Выбор режимов согласован; вызов writing-plans подтверждает переход к плану. Историческая launch-спецификация заменена в части транспорта и ограничения resume.

## Global Constraints

- Работать в текущем worktree `fix/launch-api-resume`; не менять основной checkout. До реализации получить review плана и выбор способа исполнения.
- Общие `--window`, `--profile`, `--cwd` обязательны; ровно один из `--handoff FILE` / `--resume UUID`. Сохранить прежний handoff-вызов.
- Сохранить shell function, identity guard, model/endpoint/config и разрешённые wrappers; `CODEX_RESTORE_NO_AUTO=1` до login shell. Никаких `--no-alt-screen`, отключения защит или overrides.
- SDK нужен только launch-codex, в его Python; никакого поиска чужих окружений, автоустановки, смены разрешений или fallback. Legacy `ITerm.new_tab`, restore/picker не переделывать.
- Подключение/preflight — до 10 секунд на операцию; создание и подтверждение — общий бюджет 30 секунд. Handoff ack — отдельные 120 секунд.
- Ровно один SDK create, никаких send/run/send_text, автоматических повторов, закрытий или убийств процессов при неопределённом результате. Только явные IDs.
- JSON сохраняет `mode=launch_codex`, прежние поля/status и exit 0/2/3; добавляет `launch_mode` и `resume_session_id`. Диагностика не раскрывает argv, handoff, настройки или stderr.
- Разработка: TemporaryDirectory, fake Runner/SDK, без реальных настроек и GUI. Живая приёмка и bootstrap — отдельный финальный этап по согласованной спецификации.
- Публичные файлы/релиз не содержат личных путей, UUID пользовательских диалогов или материалов чата. Чужие файлы сохраняются через штатные receipts/CAS.
- При SDD сохранять обязательные этапы, артефакты, согласования, тесты и ревью; Ponytail определяет простейшую реализацию, но не сокращает процесс.

## Review Focus

1. API принял запрос и оборвал соединение: одна попытка, `unknown`/3, без ложного `blocked` или cleanup — Task 2, `test_disconnect_after_create_never_retries`.
2. Совпадающие UUID в двух журналах, symlink наружу или FIFO: bounded проверка, `blocked`, посторонняя история не читается — Task 1, `test_resume_ambiguous_or_unsafe_transcript_blocks`.
3. Смена активной вкладки/профиля между preflight и create: явное окно, повторная сверка GUID, никаких чужих вкладок — Task 2, `test_target_changes_before_create`.
4. Верный job/title, но другой UUID/cwd или лишний prompt: не `launched`; допустимые wrappers сохраняются — Task 3, `test_resume_requires_exact_argv`.
5. Уже открытый диалог или недоступная история: агент не создаёт дубль без просьбы и не заявляет восстановление только по argv — Task 4, held-out `resume-existing` / `resume-unobserved`.

---

## Карта файлов и ответственности

| Файлы | Ответственность |
|---|---|
| `iterm2_utils/cli.py`, `iterm2_utils/launch_checks.py` | Режимы, входная валидация, точный lookup в effective CODEX_HOME, preflight |
| `iterm2_utils/launch_api.py` (новый) | Ленивый SDK, явное окно/профиль, одно создание, классификация неопределённого результата |
| `iterm2_utils/launch.py` | Shell argv, интеграция адаптера, общий deadline, наблюдение и публичный результат |
| `tests/test_cli.py`, `tests/test_launch_checks.py`, `tests/test_launch_api.py` (новый), `tests/test_launch.py` | Изолированные проверки режимов, SDK, quoting и наблюдений |
| `skills/iterm2-launch/SKILL.md`, `references/handoff.md`, новый `references/resume.md` в том же каталоге | Инструкция обоих режимов и отдельные критерии результата |
| `README.md`, `docs/compatibility.md`, `tools/check_skill.py` | Публичный контракт, prerequisite/версия SDK, реальные границы проверок |
| `tools/check_export.py`, `tests/test_export.py`, `tests/test_skill_install.py` | Allowlist, распакованный релиз и обновление всех references через CAS |
| `docs/superpowers/validation/2026-11-01-launch-api-resume/{skill-cases,skill-results,acceptance}.md` (новые) | Вымышленные поведенческие кейсы, результаты и обезличенная матрица приёмки |

Переиспользовать без изменения `runtime/codex_restore/codexlib/transcripts.py` (`normalize_uuid`, `validate`), `tools/build_release.py` и существующие shell suites. Не вводить общий реестр/менеджер сессий или второй SDK framework.

### Task 1: Два режима и безопасная проверка resume

**Files:** Modify `iterm2_utils/{cli,launch_checks,launch}.py`; Test `tests/{test_cli,test_launch_checks,test_launch}.py`.

**Interfaces:**
- Сохранить первые четыре позиции `LaunchRequest(window_id: str, profile: str, cwd: Path, handoff: Path | None = None)`; добавить `resume_session_id: str | None = None` и property `launch_mode: str` (`handoff`/`resume`).
- Сохранить `validate_request(request: LaunchRequest) -> None`, `inspect_launch(paths: Paths, request: LaunchRequest, runner: Runner) -> tuple[LaunchInspection | None, list[Finding]]` и `_codex_arguments(request: LaunchRequest) -> list[str]`.
- Добавить в launch_checks `validate_resume(request: LaunchRequest, identity: LaunchIdentity) -> None`: ValueError с фиксированным кодом при отсутствии единственного валидного журнала. Использовать `identity.codex_home`, `transcripts.normalize_uuid(value: str) -> str`, `transcripts.validate(path, session_id, codex_home, cwd) -> Session | None`.

- [x] Написать `test_launch_modes_are_exclusive`: оба/ни один режим → `assert exit_code == 2`, `assert create_calls == []`; прежний handoff разбирается. Добавить `test_resume_uses_effective_home`: lowercase нормализованный UUID, только header нужного интерактивного transcript; `assert argv == ['resume', uuid, '-C', str(cwd)]`, нет prompt, явно другой существующий cwd допустим.
- [x] Написать `test_resume_ambiguous_or_unsafe_transcript_blocks`: два валидных совпадения, неизвестный UUID, неверный header/source/originator, symlink наружу и FIFO → blocked до create, bounded время; spy подтверждает отсутствие чтения остальных текстов. Сохранить негативные проверки cwd, symlink/FIFO handoff и добавить невалидный UUID для прямого LaunchRequest.
- [x] RED: `python3 -m unittest tests.test_cli tests.test_launch_checks tests.test_launch -v`; новые проверки падают на отсутствии resume-контракта.
- [x] Добавить required mutually exclusive argparse group; нормализовать UUID на входе CLI и при построении argv/result для прямого вызова. В validate_request проверить XOR и paths. После effective identity искать только кандидаты точного UUID внутри sessions, перед validate отвергать специальные файлы и небезопасные пути. Ограничить lookup/header-read 10 секундами, включая зависший ввод; не читать тела журналов и не менять legacy validator глобально. Добавить resume argv, сохранив handoff prompt буквально. В результате обоих режимов заполнить новые поля, включая blocked; CLI ошибки argparse сохраняют прежний формат.
- [x] GREEN: повторить команду RED; ожидается OK. Проверить `launch-codex --help`: обязательные общие флаги и `( --handoff | --resume )`.
- [x] Commit только перечисленных файлов: `feat: add exact Codex resume launch mode`.

### Task 2: Изолированный SDK transport с одним create

**Files:** Create `iterm2_utils/launch_api.py`, `tests/test_launch_api.py`; Modify `tools/check_export.py` (allowlist новых файлов).

**Interfaces:**
- Новый frozen dataclass `LaunchCreation(status: str, window_id: str | None, tab_id: str | None, session_id: str | None, deadline: float | None, findings: tuple[Finding, ...])`. Status: `blocked`, `unknown`, `created_unverified`; deadline — monotonic deadline создания/наблюдения, None до отправки.
- `async create_tab(window_id: str, profile: str, profile_guid: str, command: str) -> LaunchCreation`. SDK импортируется внутри вызова; соединение закрывается в finally. После известного успешного create возвращается `created_unverified`: окончательный `launched` принадлежит verifier Task 3.

- [x] Написать `test_custom_command_overrides_profile_at_creation`: fake профиль сам запускает codex; `assert create_calls == [(explicit_window, profile, command)]`, `assert send_calls == []`, настройки профиля не изменены. Fake SDK моделирует результат с отдельными window/tab/session IDs, не подменяет наблюдение готовым успехом.
- [x] Написать `test_missing_sdk_api_or_permission_blocks`: ошибка импорта, connect/preflight timeout/denial → `assert result.status == 'blocked'`, `assert create_calls == []`; импорт launch_api и bootstrap без SDK работают. `test_target_changes_before_create`: active window сменилось — используется прежний ID; выбранное окно исчезло или profile/GUID изменился — blocked.
- [x] Написать `test_disconnect_after_create_never_retries` и `test_partial_create_preserves_ids`: после отправки timeout/disconnect/malformed reply → unknown либо created_unverified с уже известными IDs; `assert len(create_calls) == 1`, `assert cleanup_tab_calls == []`. Fake clock проверяет `assert result.deadline == create_started + 30`; каждая preflight операция ограничена 10 секундами.
- [x] RED: `python3 -m unittest tests.test_launch_api -v`; ожидается отсутствие нового модуля/контракта.
- [x] Реализовать адаптер через официальный SDK: connect, async_get_app, точное окно, повторная проверка unique profile/GUID, затем один `Window.async_create_tab(profile=profile, command=command, select=True)`. Установить deadline перед отправкой, ограничить await оставшимся бюджетом; извлекать IDs последовательно, сохранять полученные даже при следующей ошибке. Ошибки до отправки отделить от ошибок после неё; выдавать только фиксированные findings. Cancellation не доказывает отсутствие вкладки. Не вызывать it2 и не отправлять ввод.
- [x] GREEN: `python3 -m unittest tests.test_launch_api tests.test_export -v`; ожидается OK, SDK не требуется тестовому Python.
- [x] Commit только адаптера, теста и allowlist: `fix: create Codex tabs through the iTerm2 SDK`.

### Task 3: Подтверждение точного запуска и регрессии поставки

**Files:** Modify `iterm2_utils/{launch,launch_checks}.py`, `tests/{test_launch,test_launch_checks,test_export,test_cli}.py`.

**Interfaces:**
- Consumes: `create_tab(...) -> LaunchCreation` из Task 2, LaunchRequest/argv из Task 1.
- Preserves: `launch(request: LaunchRequest, paths: Paths, runner: Runner) -> tuple[int, dict]`, `build_command(request, inspection, paths) -> str`, LaunchITerm только как read-only наблюдатель.
- Produces: прежний JSON плюс `launch_mode: 'handoff' | 'resume'`, `resume_session_id: str | None`; launched/0 только после полного наблюдения, blocked/2 до create, unknown или created_unverified/3 после неопределённого create.

- [x] Адаптировать launch fixtures к fake SDK; добавить `test_launch_never_uses_legacy_creation`: `assert it2_mutations == []`, handoff и resume проходят SDK. `test_creation_and_verification_share_deadline`: create потребил часть 30 секунд, все subprocess получают остаток, по исчерпании exit 3; известные IDs сохраняются при любой ошибке наблюдения. Preflight `runner.codex_config` также ограничить 10 вместо текущих 15 секунд.
- [x] Добавить `test_resume_requires_exact_argv`: title `codex` и полный commandLine проходят с 0/1/2 `--no-daemon` только перед mode argv; bare codex, helpers, чужой UUID/cwd, дополнительный prompt, флаг в другом месте и >2 флагов дают exit 3. Сохранить аналогичные handoff проверки. Подмены окна/tab/session, несколько сессий, имя/GUID профиля и неполные variables не проходят; UUID iTerm нормализуются, bundled it2 получает uppercase.
- [x] Расширить исполняемые zsh fixtures обоими режимами: fake Codex записывает argv и CODEX_RESTORE_NO_AUTO. `assert captured_argv == expected_argv`, `assert restore_auto == '1'`, `assert sentinel.exists() is False` для пробелов, кириллицы, кавычек, переводов строк, `$()` и backticks в путях. Сохранить guard отказа при изменении identity и сохранение shell после выхода; handoff содержимое не выполняется.
- [x] RED: `python3 -m unittest tests.test_launch tests.test_launch_checks tests.test_export tests.test_cli -v`; новые проверки выявляют legacy create/старый deadline.
- [x] В launch вызвать адаптер через asyncio.run, удалить требование `it2 tab new --help` из inspect_launch. Использовать deadline результата для всех read-only проверок; сверять ровно SDK IDs и единственную сессию, не выводить IDs из активной/недавней вкладки. Перенести существующую проверку полного argv на оба режима, сохранив ограничения wrappers и редактирование диагностики. Удалить только устаревшие launch-specific тесты угадывания legacy key, не тесты standalone restore.
- [x] Обновить `test_extracted_release_launch_without_restore_install` и `test_launch_and_standalone_restore_after_source_removed`: оба режима через fake SDK из извлечённого архива после удаления исходника, standalone restore прежний. GREEN: повторить RED, затем `zsh tests/test_codex_shell.zsh`, `zsh tests/test_appearance_shell.zsh`, `zsh tests/restore/test_codex.zsh`; ожидается успех всех команд.
- [x] Commit перечисленных файлов: `fix: verify API launch identity within one bounded attempt`.

### Task 4: Инструкция скилла и доказательство его поведения

**Files:** Modify `skills/iterm2-launch/{SKILL.md,references/handoff.md}`, `README.md`, `docs/compatibility.md`, `tools/{check_skill,check_export}.py`, `tests/test_skill_install.py`; Create `skills/iterm2-launch/references/resume.md` и validation `skill-cases.md`, `skill-results.md` из карты файлов.

**Interfaces:**
- Consumes: CLI/JSON Tasks 1–3; `bootstrap-skill --skill iterm2-launch --agent codex [--dry-run] --json` без изменения установочного API.
- Produces: две документированные ветки скилла; handoff ack по существующему формату, resume без prompt/ack и с отдельным read-only доказательством восстановленной истории.

- [x] Зафиксировать held-out вымышленные задания и fake tool responses в skill-cases: новый агент; resume с найденным cwd; уже открытый диалог; resume без доступной истории; неизвестный исход; shell-команда видна в prompt. Не включать ожидаемые ответы в задания агенту. В отдельной рубрике: `assert create_count <= 1`, `assert terminal_input == []`, запрет fallback; точные UUID/cwd и различение launched/ack/history. Добавить структурный пример допустимого processTitle+argv и недопустимого bare codex; не выдавать эту проверку за behavioral.
- [x] RED: прогнать текущую инструкцию свежим Codex в изолированном окружении с fake tools и вымышленными данными; записать фактические нарушения/пробелы в skill-results. Запуск не должен давать агенту реальные terminal tools, настройки или сеть для тестовых действий. Если доступен только текстовый сценарий — прямо отметить это ограничение. Добавить `test_launch_update_copies_resume_reference_preserving_foreign_changes`: новый reference копируется через owned update, чужой файл → conflict и сохранение. Запустить `python3 -m unittest tests.test_skill_install -v`, ожидается отказ нового теста до добавления reference.
- [x] Обновить скилл/reference: поиск точного диалога по относящейся истории, cwd из подтверждённого transcript, другой cwd только по просьбе; известную открытую вкладку сообщать, дубль только по явной просьбе. SDK prerequisite в выбранном Python, один CLI вызов, отсутствие ввода и fallback. Исправить формулировку processTitle/commandLine; сохранить безопасное bounded ack-чтение/120 сек. Для resume без read-only истории сообщать: «команда resume запущена, восстановление истории не подтверждено».
- [x] Обновить README/compatibility и allowlist для resume reference: примеры обоих режимов, таймауты/status/IDs, lazy SDK без автоматической установки. Поддержанную SDK версию записывать только по фактической проверке Task 5; до этого пометка pending. Исторические документы не переписывать.
- [x] GREEN: `python3 -m unittest tests.test_skill_install tests.test_export -v` и `python3 tools/check_skill.py` → OK / 2 skills structurally valid. Повторить held-out проверки свежим Codex с новой инструкцией; сохранить действия, оценку по рубрике и ограничения. Прогон с реальными вкладками не заменяет и не входит в behavioral тест.
- [x] Commit только скилла, публичной документации, allowlist/validator, теста и обезличенных behavioral артефактов: `docs: teach safe Codex launch and exact resume`.

### Task 5: Итоговая проверка, установка скилла и отдельная живая приёмка

**Files:** Create validation `acceptance.md`; Modify `docs/compatibility.md`, validation `skill-results.md` только по фактическим итогам. Продуктовый код здесь не добавлять; обнаруженный дефект возвращается в owning task с regression test.

**Interfaces:**
- Consumes: CLI/skill Tasks 1–4, штатные bootstrap receipts/CAS и `tools/build_release.py --destination DIR`.
- Produces: обезличенная матрица automated/behavioral/live/bootstrap с фактическими версиями и результатами. Приватные handoff/ack/UUID хранятся только в собственном временном каталоге, вне публичного репозитория/архива.

- [x] Запустить обязательные `python3 -m unittest discover -v`, `python3 tools/check_skill.py`, `python3 tools/check_export.py`, `git diff --check`. Ожидается OK, 2 валидных skills, успешные export/diff checks. Сопоставить с baseline **577 tests, OK, skipped=1**; известный skip — case-insensitive filesystem. Собрать архив `python3 tools/build_release.py --destination /private/tmp/iterm2-launch-api-resume-release`; не публиковать. Если после этого код менялся, повторить затронутые и обязательные проверки.
- [x] Выполнить предусмотренное выбранным методом независимое ревью всей ветки и исправить findings до live/bootstrap. Зафиксировать результат и реальные ограничения, не считать fixture/structural тесты доказательством UI/поведения.
- [x] Объявить пользователю начало отдельной живой приёмки, разрешённой спецификацией. В уже выбранном совместимом Python проверить импорт и версию SDK; не искать произвольные окружения и не устанавливать зависимости. Выбрать явные окно/profile и собственный приватный временный cwd; permission dialog или prerequisite failure → остановить live с точным статусом, не обходить.
- [x] Создать первую собственную вкладку новой CLI с безвредным handoff: записать ack и ждать. Проверить реальные argv/cwd/IDs, профиль, ack и отсутствие вставленной команды. После штатного выхода этого тестового Codex создать вторую вкладку с resume его точного UUID без prompt; read-only подтвердить историю, argv и IDs. Не использовать рабочие диалоги пользователя. Закрыть только эти собственные успешные тестовые вкладки; при unknown/неполной проверке сохранить их и артефакты, не повторять. EN/RU clipboard отметить отдельно как непроверенный, если фактически не проверялся.
- [x] Обновить установленный скилл из проверенного worktree: сначала `python3 -m iterm2_utils bootstrap-skill --skill iterm2-launch --agent codex --dry-run --json`, затем тот же вызов без `--dry-run`. Проверить receipt и совпадение установленных SKILL.md/references с исходником. При CAS conflict не перезаписывать чужие изменения; зафиксировать блокер. Bootstrap не меняет настройки/features и не требует SDK; системное разрешение на запись вне writable roots запрашивается штатно при необходимости.
- [x] Заполнить acceptance/compatibility фактической SDK версией, исходами двух запусков, behavioral и bootstrap; никаких личных путей/UUID. `python3 tools/check_export.py`, `python3 tools/check_skill.py`, `git diff --check` → успех. Commit только результатов: `docs: record API launch and resume acceptance`. В итоговом сообщении разделить исправление кода, обновление установленного скилла и выполненную/незавершённую live-приёмку.

## Самостоятельная сверка плана

Спецификация покрыта: интерфейс/lookup — Task 1; SDK/lazy prerequisite/one-shot/ошибки — Task 2; shell/identity/deadline/argv/JSON/релиз — Task 3; инструкция/ack/history/behavioral — Task 4; обязательные проверки, версии, bootstrap/CAS и отдельная live-приёмка — Task 5. Все пять Review Focus имеют owning test/case. Типы LaunchRequest, LaunchCreation и публичный launch согласованы между задачами; legacy restore и установочный API сохраняются. План задаёт контракты и проверки, не тела реализации. Открытых продуктовых решений не осталось; способ исполнения выбирает пользователь после review плана.
