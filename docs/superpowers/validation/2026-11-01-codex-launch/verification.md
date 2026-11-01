# Codex launch: фактическая проверка

Дата: 2026-11-01. База Task 6: `d7e031a`; рабочая ветка `feat/codex-launch`.
Проверяется исходный код после Tasks 1–5 и изменения Task 6, до финального
коммита документации. macOS Darwin 25.6.0 arm64, Python 3.13.7, zsh 5.9.
Новый CI-прогон, поведенческий PASS и живая приёмка не заявляются.

## TDD поставки

- RED: `python3 -m unittest tests.test_export -v` — 8 тестов, 3 failures.
  Оба новых теста падают на `ImportError: cannot import name 'launch'` из
  распакованного release, существующий archive CLI smoke — на отсутствующих
  launch-модулях/skill. Лог: `.superpowers/sdd/2026-11-01-codex-launch/task-6-red.log`.
- GREEN после дополнения allowlist: та же команда — 8 тестов, OK, 9.509 s.
  Лог: `.superpowers/sdd/2026-11-01-codex-launch/task-6-green.log`.
  Финальный прогон ниже включает последующее усиление удаления source/archive
  и validator/export assertions.

## Финальный обязательный прогон

Весь набор запущен один раз после стабилизации кода Task 6. Все команды из
task worktree; test HOME/Paths и adapters изолированы. Полные stdout/stderr и
exit codes сохранены в `.superpowers/sdd/2026-11-01-codex-launch/`:

| Точная команда | Фактический результат | Полный лог |
| --- | --- | --- |
| `python3 -m unittest discover -v` | 467 tests, 90.028 s, OK; exit 0 | `task-6-unittest.log` |
| `/bin/zsh tests/test_codex_shell.zsh` | `Codex dispatcher tests passed`; exit 0 | `task-6-codex-shell.log` |
| `/bin/zsh tests/restore/test_codex.zsh` | `pass=37 fail=0`, OK; exit 0 | `task-6-restore-shell.log` |
| `python3 tools/check_sources.py` | 27 pinned sources verified; exit 0 | `task-6-sources.log` |
| `python3 tools/check_skill.py` | `2 skills structurally valid (not a behavioral evaluation).`; exit 0 | `task-6-skills.log` |
| `python3 tools/check_export.py` | 109 allowlisted files; provenance/licenses/private-reference checks passed; exit 0 | `task-6-export.log` |
| `python3 tools/build_release.py --destination dist` | `dist/iterm2-utils-v0.1.0-beta.1.tar.gz` + checksum built; exit 0 | `task-6-build.log` |
| `git diff --check` | Нет whitespace ошибок; exit 0 | `task-6-diff.log` |

467 — число unittest tests в итоговом runner, не сумма с вложенными smoke suites:
в том числе 75 `tests.restore.*`, 14 `tests.test_launch`, 12
`tests.test_launch_checks`, 16 `tests.test_skill_install` и 8 `tests.test_export`.
Zsh restore 37 считается отдельно; shell dispatcher не печатает численного
счётчика. Результаты ранее запускались в других сочетаниях: объединять их
с текущим числом или выдавать за дополнительные тесты нельзя.

Итоговая матрица совместимости обновлена после этого прогона только результатами
и числами. Повторные export/build/whitespace после этого изменения фиксируются
в `task-6-docs-export.log`, `task-6-docs-build.log`, `task-6-docs-diff.log`;
все три завершились exit 0: 109 файлов проверены, архив/checksum пересобраны,
whitespace ошибок нет. Полный unittest/zsh набор без изменений кода не повторяется.

## Что проверяют новые fixtures

`test_extracted_release_launch_without_restore_install` импортирует модули
только из распакованного релиза в изолированном subprocess HOME/PYTHONPATH.
Preflight адаптирован; реальный bundled `LaunchITerm`/`ITerm._run` вызывает
исполняемый fake `it2`: новая вкладка ровно одна, явные window/profile/command,
однозначные session IDs, `CODEX_RESTORE_NO_AUTO=1`, без restore receipt,
`--no-alt-screen` и утечки handoff. Fake не исполняет команду Codex и не доказывает
live запуск. Оба варианта bootstrap копируют точные bytes публичных references.
Default validator обнаруживает повреждённый launch skill; явный setup directory
по-прежнему проходит независимо от него.

`test_launch_and_standalone_restore_after_source_removed` повторяет архивный
launch, удаляет fixture checkout и сжатый архив, устанавливает только restore
через существующий lifecycle fixture и удаляет весь извлечённый source.
Установленный subprocess wrapper проходит help и существующий NUL protocol
list/open/cancel lifecycle. Подменён только путь wrapper; исполняется установленный
runtime, а не ранее импортированный source в родительском Python.

## Границы доказательств

Source-контракты Codex rust-v0.166.0 и iTerm2 v3.7.6:
[source-contracts.md](source-contracts.md). Config probe выполняет login startup,
initialize/initialized/config/read и может создавать штатные state/log/recovery
SQLite; это не filesystem-read-only операция. Identity guard не блокирует
изменение config contents между probe и запуском. Материализованный preference
snapshot не доказывает текущие runtime bindings; устаревший внешний plist с теми
же name/GUID и конкурентное изменение профиля остаются ограничениями.

Поведенческие held-out RED/GREEN: **BLOCKED**, не запускались — отсутствует
разрешённый изолированный inference endpoint/auth; см. [skill-results.md](skill-results.md).
Никакие модели или чужие API не вызывались для получения behavioural PASS.

Live launch/ack/clipboard ABC+RU и соседняя сессия: **live-unverified**.
Изолированный Mac account/VM не предоставлен. Реальные настройки/HOME, auth,
GUI, разрешения и рабочие сессии разработчика для приёмки не использовались.
Структурный validator и fixture transport не заменяют живую проверку.

## Final-review fix wave (после bf7c55f)

Предыдущие 467 PASS и shell результаты выше относятся к Task 6. После I1/M1
выполнены только затронутые проверки; полный набор не повторялся.

- RED: `python3 -m unittest tests.test_launch.LaunchTests.test_helper_or_incomplete_command_line_is_not_launched -v`
  — 1 test, 6 expected failures: helper/missing/wrong command observations давали launched.
- RED с задержанными fake processes: `python3 -m unittest tests.test_launch.LaunchTests.test_delayed_helpers_guard_refusal_and_actual_tui -v`
  — 1 test, 10 expected failures (7 version-before-guard-refusal + 3 restore help);
  7 целевых запусков в той же матрице уже проходили. Полный лог: `final-fix-red.log`
  в plan scratch directory. Ранний вариант test harness с Unix socket был недоступен
  в sandbox (`Operation not permitted`); заменён обычными pipes, это не RED продукта.
- GREEN: `python3 -m unittest tests.test_launch tests.test_launch_checks tests.test_cli tests.test_export -v`
  — **57 tests, 20.183 s, OK**; полный лог `final-fix-tests.log`.
- После усиления проверки точного числа `--no-daemon` и добавления restore→passthrough
  повторён только тест задержанных процессов: **1 test, OK**, 20 фаз в 8 chains.
  Полный лог `final-fix-chains.log`.
- `python3 tools/check_skill.py` — **2 skills structurally valid (not a behavioral evaluation)**.
- `python3 tools/check_export.py` — **109 allowlisted files verified; provenance/licenses/private-reference checks passed**.
- `git diff --check` — exit 0, без вывода.

Pipes останавливают синтетический codex на точном argv, а fake-it2 воспроизводит
pinned iTerm processTitle/commandLine; это не запуск настоящего Codex/iTerm2.
Guard rejection не выполняет TUI, задержанные version/help остаются unverified;
целевой вызов подтверждается без ack. Покрыты direct, passthrough, simple,
dispatcher и каждый из четырёх под restore; 0/1/2 no-daemon, malformed/missing
observations, пути с пробелами/кавычками/кириллицей/newline и отсутствие повторной
мутации. Archive smoke обновлён под новый контракт и пройден.

Изменений vendored runtime нет; provenance не изменялся. Behavioral BLOCKED и
live-unverified сохраняются. Реальные настройки, GUI, auth и model API не
использовались. Обновление установленного skill после этого коммита выполняет
контроллер штатным bootstrap и проверяет hashes отдельно от этих fixtures.
