# Directory-driven tab appearance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Обычный `cd` назначает цвет и иконку текущего репозитория, а выход наружу возвращает стандартный вид без кастомной иконки.

**Architecture:** Добавить один штатный zsh `chpwd` hook к существующему `appearance.zsh`; он вызывает прежний ограниченный helper с фазой `shell` и физическим cwd. Расширить runtime сбросом сессионного оформления при отсутствии правила в этой фазе. Общий dispatcher, APS-защита запуска/возврата Codex и installer/CAS остаются основой решения.

**Tech Stack:** macOS, zsh, Python 3.11+, stdlib unittest, существующий официальный `iterm2` SDK.

**Spec:** [2026-11-01-appearance-cwd-design.md](../specs/2026-11-01-appearance-cwd-design.md), утверждена 01.11.2026. Её явные изменения поведения имеют приоритет над старой launch-only спецификацией.

## Global Constraints

- «Это новое поведение уже включённой функции `appearance`, без отдельного режима, CLI-флага или изменения схемы JSON».
- «Меняются только сессионные свойства цвета и иконки; профиль, фон, заголовок и глобальный Default остаются под управлением iTerm2».
- «Назначение и сброс учитывают base/light/dark варианты цвета»; дефолтный RGB не задавать.
- «Хук регистрируется один раз штатным механизмом zsh, не подменяет чужие `chpwd` и не дублируется при повторном source».
- «API-ошибка не отменяет успешный `cd`; постоянный наблюдатель, демон и polling не добавляются».
- «Не расширять поддержку tmux, других shell/агентов или поздних APS-переходов».
- Прежние физические rules, вложенность/симлинки/APFS aliases, выбранный SDK Python, явный UUID, hard/API/watch бюджеты 2.8/2.2/1.5 секунды сохраняются.
- Никаких реальных settings/API/GUI в dev-тестах; только hermetic HOME/fake adapters. Локальное включение — отдельная разрешённая CLI-приёмка после review.
- Работа в существующем изолированном worktree, ветка `feat/appearance-cwd`, база `237b151`; main checkout не менять. Старое SDD workspace другого плана не использовать.
- Во время SDD сохранять task-scoped snapshots/diffs и отчёты без промежуточных коммитов; итоговый commit/push/PR после проверок и review.
- При работе по Superpowers SDD сохраняй обязательные этапы, артефакты, согласования, тестирование и ревью. Ponytail применяй для выбора простейшей реализации, полностью выполняющей согласованную спецификацию. Упрощение не должно сокращать требования или обходить этапы SDD.

## Review Focus

1. Быстрые `cd` project A → B → outside во время старого helper/return observer: итог только outside, без поздней записи и живого старого worker (Task 2).
2. Унаследованный hook в `(cd ...)`/command substitution/noninteractive subprocess не меняет родительскую вкладку; свежая вложенная interactive shell регистрирует собственного владельца (Task 2).
3. Default после проекта с light/dark цветами скрывает custom icon и отключает все use-color варианты, не окрашивая Default/фон/заголовок (Task 1).
4. Выход по `cd` и последующий Codex с APS/restore не воскрешают цвет покинутого проекта или старый snapshot (Tasks 1–2).
5. Повторный source, обновление без checkout и частичный uninstall сохраняют чужие hooks/функции и других потребителей runtime (Tasks 2–3).

## Карта файлов и решений

- `runtime/appearance.py`, `tests/test_appearance_runtime.py`: стандартная цель без правила, SDK reset и строгие прежние session/deadline границы.
- `runtime/appearance.zsh`, `tests/test_appearance_shell.zsh`: idempotent `chpwd`, владелец hook, существующая отмена/EOF fence и реальные zsh fixture-сценарии.
- `tests/test_payload.py`: установленный helper/hook после source removal; существующие `tests/test_appearance_feature.py` и `tests/test_shell.py` проверяют lifecycle/частичный uninstall.
- `README.md`, `CHANGELOG.md`, `docs/repo-appearance.md`, `docs/compatibility.md`, `skills/iterm2-setup/{SKILL.md,references/features.md,references/troubleshooting.md,references/ui.md}`: актуальная семантика и честная матрица.
- `iterm2_utils/features/shell.py`, `runtime/codex.zsh`, rules schema и assets уже подходят; менять только при доказанном пробеле. `sources.lock.json` не трогать, если pinned source bytes не изменились. Новые production-файлы не нужны.

### Task 1: Стандартное оформление при отсутствии правила

**Files:** Modify `runtime/appearance.py`; Test `tests/test_appearance_runtime.py`.

**Interfaces:** сохраняются `apply(config: Path, cwd: Path, phase: str, *, environment: dict[str,str], ready_fd: int | None = None, launch_id: str | None = None) -> str`, CLI-фазы `shell/launch/return`, `load_rules/select_rule`. Добавляется `_API.reset(session) -> None`. Для отсутствующего правила в `shell` внутренний request несёт `reset=True` без фиктивных `color/icon`; для `launch/return` сохраняется текущая APS-preservation ветка. После нового `cd` она защищает уже сброшенный default.

- [ ] **Step 1: Добавить/изменить failing behavior tests.** Заменить `AppearanceEntrypointTests.test_no_match_does_not_connect` тестом `test_no_match_shell_requests_default_reset`: валидный explicit UUID, cwd вне правил → `_operate` получает `reset=True`, phase `shell`, status `applied`. `AppearanceOperationTests.test_default_reset_uses_only_explicit_session` требует `api.reset(session)` один раз, без `api.write`/observer; missing session/TMUX/invalid config не разрешают произвольный сброс.
- [ ] **Step 2: Добавить SDK boundary regression.** `NativeAdapterTests.test_reset_disables_all_color_variants_and_custom_icon`: одна session profile-properties запись с `Use Tab Color`, `Use Tab Color (Light)`, `Use Tab Color (Dark)` = false, `Icon` = 0 (`IconMode.NONE`), `Custom Icon Path` = empty string; нет RGB, Name, фоновых или глобальных свойств.
- [ ] **Step 3: Run RED.** `python3 -m unittest tests.test_appearance_runtime -v` — новые assertions FAIL на прежнем early ignored/отсутствующем reset, а не из-за сломанной fixture.
- [ ] **Step 4: Implement reset и routing.** В `_run_request` только отсутствие совпадения `shell` становится reset; ошибки JSON/asset/API остаются ошибками, без маскировки под успешное применение. В `_operate` общий локальный write выбирает reset либо существующее назначение/сохранение; `applied` только после await native API. Не добавлять фазу `cwd`, IPC-протокол, snapshot family или генератор ассетов.
- [ ] **Step 5: Закрепить APS default regression.** `test_default_survives_no_match_codex_aps_and_return`: default после shell-reset → no-match launch, fake профиль Codex, возврат → три use-color false, Icon=0, пустой path; существующие same-launch transactional restore/clear и cancellation tests остаются зелёными. Механизм ручного snapshot при запуске Codex не переписывать ради hook.
- [ ] **Step 6: Run GREEN.** `python3 -m unittest tests.test_appearance_runtime tests.test_appearance_rules -v` — OK, platform-specific skip явно записан.
- [ ] **Step 7: Сохранить scoped diff, RED/GREEN и self-review для независимого task review.** Без git add/commit между задачами.

### Task 2: Штатный chpwd и порядок обновлений

**Files:** Modify `runtime/appearance.zsh`; Test `tests/test_appearance_shell.zsh`.

**Interfaces:** прежняя `_iterm2_utils_appearance phase cwd` не меняется. Новый `_iterm2_utils_appearance_chpwd` вызывает её с `shell` и `builtin pwd -P`; регистрируется через `autoload -Uz add-zsh-hook` / `add-zsh-hook chpwd`. `_iterm2_utils_appearance_hook_owner` — неэкспортируемый actual source-shell PID из `zsh/system`, чтобы унаследованный hook в forked subshell не срабатывал. Нет нового public option.

- [ ] **Step 1: Заменить старый launch-only shell test.** `test_startup_once_source_twice_and_cd_applies_physical_cwd`: первый source даёт одну `shell`, второй не дублирует действие/hook, успешный `cd` даёт ровно одну новую `shell` с физическим cwd. Дополнить переходами outside → A → A/subdir → B → outside; helper args соответствуют каждому реальному cwd, вывод пустой.
- [ ] **Step 2: Добавить isolation/failure tests.** `test_chpwd_preserves_foreign_function_hooks_and_cd_status` проверяет существующие `function chpwd` и другую chpwd_functions entry, по одному выполнению, сохранённый stdout/status; helper failure не отменяет cd. `test_inherited_chpwd_does_not_recolor_parent_from_subprocess` проверяет `(cd ...)`, command substitution и noninteractive zsh без новых helper starts. Новая interactive zsh с source создаёт свой hook/owner; другой terminal/TMUX остаются исключены.
- [ ] **Step 3: Run RED.** `/bin/zsh tests/test_appearance_shell.zsh` — новые cwd/registration/ownership assertions FAIL на отсутствии hook.
- [ ] **Step 4: Implement hook и idempotent setup.** Добавить функцию и native registration в interactive iTerm bootstrap. Hook проверяет owner PID, использует прежний helper с `shell` и возвращает 0. Повторный source не добавляет дубль и не удаляет чужие entries/function. Внешние команды/скрипты и forked subshell не получают самостоятельного права на перекраску.
- [ ] **Step 5: Добавить order regression и довести GREEN.** `test_rapid_cd_and_return_observer_leave_only_latest_writer`: fixture удерживает прежний helper, быстрые A → B → outside/return → cd; старый end/cleanup предшествует новому start, последний cwd outside, нет поздних записей, helper PID отсутствует при ещё живой zsh. Переиспользовать lifetime FD/CLOEXEC/TERM+EOF fence и существующие tests signals, quiet jobs и options; не заменить на `&!` или периодический timer.
- [ ] **Step 6: Адаптировать restore boundary assertion осмысленно.** `test_restore_picker_reaches_dispatcher_and_keeps_status` теперь учитывает `shell` событие от реального `builtin cd` picker; argv `--no-daemon resume UUID`, register/finish, stderr и exit42 сохраняются. Не ослаблять проверку порядка до «есть любой launch».
- [ ] **Step 7: Run GREEN.** `/bin/zsh tests/test_appearance_shell.zsh`; `/bin/zsh tests/test_codex_shell.zsh`; `/bin/zsh tests/restore/test_codex.zsh` — OK/dispatcher passed/pass37 fail0, фактические counts записать. Scoped diff/report → независимый task review, без промежуточного commit.

### Task 3: Доставка, документация и приёмка

**Files:** Modify `tests/test_payload.py` и перечисленные в карте docs; существующие lifecycle/shell/export tests расширять только при выявленном конкретном пробеле, manifest — только если добавлен необходимый файл.

**Interfaces:** используются прежние `runtime_payload(context, selection)`, installed `current/appearance.zsh` и `appearance.json`, plan/install/CAS/receipts. Task 1 даёт reset для phase `shell`; Task 2 устанавливает hook тем же source.

- [ ] **Step 1: Добавить delivery assertions.** Расширить `AppearancePayloadTests.test_installed_icons_selected_after_all_sources_removed`: после удаления checkout/исходных JSON/PNG helper выбирает installed builtin/custom icon, а outside выдаёт reset, без исходного файла. Добавить `test_installed_chpwd_hook_survives_source_removal`: source установленного zsh-файла, переходы A → outside вызывают installed helper с phase shell и физическими cwd через fake executable boundary, без author settings/API.
- [ ] **Step 2: Проверить новые behavior assertions на предыдущих task snapshots и финальном дереве.** До Tasks1/2 они выявляют отсутствие reset/hook; использовать TemporaryDirectory, не checkout/restore поверх чужих правок. Затем `python3 -m unittest tests.test_payload tests.test_appearance_feature tests.test_shell tests.test_export -v` — OK. Существующие partial-uninstall tests должны сохранять чужой shell текст/других потребителей и исключать appearance source из нового generated startup; для сохранённого поведения RED не требуется. Уже работающие пользовательские shell удалённо не менять.
- [ ] **Step 3: Обновить публичные docs.** Удалить текущие утверждения «обычный cd не меняет»/«нет chpwd» из пользовательских инструкций; описать reset, hooks ownership и новое поведение существующего appearance. В compatibility сохранить старые результаты как исторические, добавить новую fixture/live матрицу с фактическими counts и ограничениями. Исторические утверждённые spec/plan не переписывать задним числом. Личных корней и локального SDK path в public docs/archive нет.
- [ ] **Step 4: Один полный final gate после source freeze.** `python3 -m unittest discover -v`; все три zsh-команды Task 2; `python3 tools/check_sources.py`; `python3 tools/check_skill.py`; `python3 tools/check_export.py`; `python3 tools/build_release.py --destination dist`; `git diff --check`. Требуется OK/pass, неизменённые27 pinned sources при отсутствии locked edits, обе skills structural valid, точный allowlist/archive byte comparison и checksum. Результаты fixture/structural не выдавать за live/model behavior.
- [ ] **Step 5: Закрыть независимые reviews до локального install.** Task reviews и предусмотренное SDD whole-branch review с одной общей финальной fix wave/scoped re-review; не добавлять параллельный второй review workflow. Контроллер проверяет binding spec, не только план.
- [ ] **Step 6: Разрешённое локальное включение — контроллер.** Read-only plan/matching `install --agent codex --features appearance --dry-run --json`, затем тот же install без dry-run, выбранный SDK Python и сохранённый owned JSON. Остальные selection/foreign edits сохраняются; широкий update других функций не выполнять. Pending `appearance_api` проверять штатным reconcile, при отказе не сбрасывать permissions/не обещать ready.
- [ ] **Step 7: Native acceptance — контроллер.** Предупредить о собственном временном окне. В свежей shell из общей папки выполнить обычный cd по5 локальным зарегистрированным корням, подкаталогу и наружу: точные color/icon, затем base/light/dark use-color=false, Icon=0/path empty. Проверить быстрые A → B → outside и запуск/автовыход fake native codex под реальным APS в проекте и после выхода; безопасно дождаться shell marker, без реального модельного prompt/Ctrl-C угадывания. Сверить readable tabbar, закрыть только captured own session IDs, записать фактические результаты/непроверенное; рабочий SSD не отключать для теста.
- [ ] **Step 8: Finish.** Final source/privacy/working-tree check, итоговый scoped commit, feature push и PR в YarikMix/iterm2-utils; main не мерджить и release/tag не публиковать. Сохранить приватные артефакты отдельно от публичных файлов, сообщить установленные изменения и ограничения.

## Self-review плана

Покрытие spec: назначения/default/light-dark → Task1; physical rules/unavailable targets → прежние rules tests + Task1; интерактивность/собственный PID/чужие hooks/idempotence/rapid updates → Task2; Codex/APS/restore → Tasks1–2 и native Task3; install/CAS/source removal/docs/export/privacy → Task3. Все5 пунктов Review Focus имеют named regression. Публичные интерфейсы и CLI-фазы сохраняются; единственный новый SDK метод — reset, единственный hook — chpwd. Кэш совпадений, daemon и отдельные config/installer/API сервисы не добавлены. Задачи выполняются последовательно; выполнение — ранее выбранный пользователем subagent-driven-development после review этого плана.
