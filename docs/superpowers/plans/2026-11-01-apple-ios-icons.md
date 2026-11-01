# Apple iOS Icons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить телефон светлым Apple в трёх iOS-парах, сохранив бейджи и семь пользовательских правил.

**Architecture:** Только заменить готовые SVG/PNG `ios`, `ios-mail`, `ios-cloud` и актуализировать описание/attribution. Registry, оба списка доставки, installer и runtime остаются прежними. После code review контроллер обновляет только appearance с существующим owned JSON.

**Tech Stack:** SVG, готовые PNG128×128, установленный developer renderer `rsvg-convert`, существующие stdlib unittest/zsh gates, официальный iTerm2 SDK для отдельной native-приёмки.

**Spec:** [2026-11-01-apple-ios-icons-design.md](../specs/2026-11-01-apple-ios-icons-design.md), утверждена по макету пользователем.

## Global Constraints

- «Обновить только три PNG/SVG-пары: `ios`, `ios-mail`, `ios-cloud`»; старые имена и размер128×128 RGBA сохраняются.
- Светлый Apple `#E6F4FF`, прозрачный фон, пропорции, лист и выемка различимы; вариант B и существующие бейджи Mail/Облака справа снизу сохраняются.
- «Бейджи, остальные шесть пар, семь правил, их цвета/порядок и логика cd/APS/reset не меняются».
- Девять встроенных имён,18 asset files и135 export paths остаются прежними; новых имён, схем, зависимостей, renderer/startup downloads не добавлять.
- Apple — third-party artwork; фиксировать публичный источник/хеш/преобразование, не приписывать знак MIT или авторству пакета.
- Dev tests только temporary HOME/fake adapters. Реальный selected install/API/GUI — контроллер после code-review gates, только собственные captured sessions, без перезапуска рабочих вкладок.
- Работа в уже изолированном worktree, ветка `feat/apple-ios-icons`, база `a4bbc59`. Без промежуточных product commits/index mutations; snapshots/diffs до итогового scoped commit/push/Draft PR, без merge/release.
- При работе по Superpowers SDD сохраняй обязательные этапы, артефакты, согласования, тестирование и ревью. Ponytail применяй для выбора простейшей реализации, полностью выполняющей согласованную спецификацию. Упрощение не должно сокращать требования или обходить этапы SDD.

## Review Focus

1. В SVG заменён телефон, но PNG осталась старой: rasterize все3, source-byte installed delivery и native icon path/SHA.
2. При замене платформы потерян Cloud-бейдж, как в первом throwaway-макете: сохранить все service subtrees после первого platform element, проверить оба изображения крупно и18/24px.
3. Бейдж перекрыл лист/выемку Apple: сверить утверждённую геометрию и реальную панель, без растяжения/обрезания значимых частей.
4. Изменились чужие иконки/правила:12 не-iOS asset files побайтово равны базе; actual JSON/selection до/после идентичны.
5. Ошибочное MIT-original описание или внешняя SVG-ссылка: актуальные notices и existing self-contained SVG/PNG/export проверки, без изменения исторических результатов.

### Task 1: Три готовые iOS-пары и документация

**Files:** Modify `runtime/assets/appearance/{ios,ios-mail,ios-cloud}.{svg,png}`, `THIRD_PARTY_NOTICES.md`, `CHANGELOG.md`, `docs/repo-appearance.md`, `skills/iterm2-setup/references/features.md`, `docs/compatibility.md`. Другие product files не нужны.

**Interfaces:** Прежние names/paths потребляются существующими `BUILTIN_ICONS`, `APPEARANCE_ASSETS`, `runtime_payload(context, selection)` и export allowlist. Они не меняются. Это графическая замена без новой software logic; существующие asset/delivery tests и визуальная проверка достаточны, искусственный RED или тесты на строку SVG-path не добавлять.

- [ ] **Step 1: Проверить исходник и before evidence.** Apple nav inline SVG с `https://www.apple.com/`, SHA256 extracted SVG `173a4aceb67e416738f3af19eeda9de484cac388914881915dc94e4f6ce77687`; приватный snapshot `apple-upstream.svg` передаёт контроллер. Хеш относится к извлечённому SVG, не к целой HTML-странице. Before snapshot сохраняет старый телефон, все18asset bytes и service subtrees двух составных иконок. Ни реальных settings, ни внутренних источников не читать.
- [ ] **Step 2: Подготовить три SVG по принятому макету.** Standalone `ios`: прежний прозрачный128×128 canvas с Apple path, aspect-preserved `viewBox="0 11 14 18"`, fill `#E6F4FF`. Composite: заменить только первый platform element на nested SVG `x=-6,y=-3,width=110,height=118,viewBox="0 11 14 18"` с тем же Apple path/fill. Service subtrees Mail и Cloud сохранить структурно идентичными базе, включая transform/цвета/размер74×74. Не заменять бейджи новыми рисунками.
- [ ] **Step 3: Подготовить три PNG.** `rsvg-convert --width 128 --height 128 --output NAME.png NAME.svg`; renderer только существующий developer tool. Проверить9pair set, RGBA/transparency/CRC/self-contained XML через `python3 -m unittest tests.test_appearance_rules tests.test_payload tests.test_export -v`. Подтвердить все6 iOS source bytes изменены, остальные12asset bytes равны базе; оба badge subtrees прежние. Контактный лист128/24/18px на тёмном фоне должен показывать Apple и оба сервиса. Это ещё не native acceptance.
- [ ] **Step 4: Актуализировать notices/docs.** Robot/Kotlett остаются MIT-иллюстрациями; Apple и Apple-derived iOS composites — third-party brand artwork с source/extracted hash/crop/recolor/owner Apple Inc. Не объявлять phone/iOS «original unchanged» в актуальных инструкциях. Предыдущие compatibility rows сохранить как historical; новая Apple/full/live строка pending до фактических проверок. `sources.lock.json` программных источников и все shipping lists не менять.
- [ ] **Step 5: Один full gate после source freeze.** `python3 -m unittest discover -v`; `/bin/zsh tests/test_appearance_shell.zsh`; `/bin/zsh tests/test_codex_shell.zsh`; `/bin/zsh tests/restore/test_codex.zsh`; `python3 tools/check_sources.py`; `python3 tools/check_skill.py`; `python3 tools/check_export.py`; `python3 tools/build_release.py --destination dist`; `git diff --check`. Требуются PASS с реальными counts/skips, sources27/skills2/export135,135 unique regular archive entries, exact allowlist/135byte comparisons/basename-only checksum; freeze hashes неизменны. Полный suite не повторять без source change или конкретной ошибки.
- [ ] **Step 6: Закрыть review gates.** Task report с scope, PNG/SVG/unchanged/badge proofs, commands/logs и self-review; task review, затем один whole-branch review. При findings — предусмотренные SDD fix loops/одна общая final fix wave. Controller native/install не выполняются worker; реальные действия ждут clean code review.

## Controller: установка и завершение после review

- [ ] Сохранить hash/копию owned JSON и selection приватно; ожидается семь rules. Matching appearance-only install dry-run, затем install **без** `--appearance-config`, с прежним выбранным SDK Python. JSON/семь triples/order и selection должны совпасть побайтово/семантически; новые PNG/SVG в installed runtime совпадают с reviewed source. Уведомления и broad update не трогать; известный unrelated общий plan blocker не обходить правкой policy, проверять выбранный checkpoint.
- [ ] Предупредить о собственном временном окне; проверить доступность SSD. Проверить обычный cd в два iOS-корня и наружу: прежние цвета, Apple+Mail/Cloud, затем default reset. Standalone ios проверен asset test/контактным листом; новых личных rules ради него не добавлять. ID создания сохранять немедленно, при неизвестном исходе не повторять создание; только own exact-window crop, затем закрыть свои sessions. Остальные12asset bytes и семь rules неизменны.
- [ ] Заполнить фактическую compatibility строку один раз; после docs-only edits повторить export/build/135bytes/checksum/whitespace, не full suite. Privacy/status check; scoped product commit, feature push, Draft PR, результат уже запущенного CI. Не merge/tag/release. Сохранить private evidence/rulings отдельно от публичного архива, worktree оставить для PR. Для старой shell — новая вкладка, не автоматический restart.

## Self-review

Spec покрыта одним атомарным asset/doc task: три пары, Apple/path/fill/геометрия/бейджи, unchanged12, attribution/offline delivery; existing meaningful tests и visual evidence без зеркальных тестов SVG literals. Review Focus1–5 имеют конкретные byte/XML/badge/native проверки. JSON/schema/runtime/export135 не меняются. После review плана исполнение — один батч через ранее выбранный SDD.
