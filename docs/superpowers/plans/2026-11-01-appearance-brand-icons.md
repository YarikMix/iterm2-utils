# Branded tab icons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Поставить выбранные фирменные бейджи Mail/Облака, добавить Chrome-пары и локально получить семь правил оформления.

**Architecture:** Обновить четыре готовые пары и добавить две Chrome-пары в существующий runtime. Расширить только registry и два явных списка доставки; локальные правила обновить штатным appearance-only install после review. Логика выбора каталога, shell и API сохраняется.

**Tech Stack:** Python 3.11+/stdlib unittest, SVG, готовые PNG 128×128, установленный у разработчика `rsvg-convert` только для подготовки ассетов, zsh и официальный SDK iTerm2 для отдельной приёмки.

**Spec:** [2026-11-01-appearance-brand-icons-design.md](../specs/2026-11-01-appearance-brand-icons-design.md), утверждена пользователем вместе с вариантом B и цветами 01.11.2026.

## Global Constraints

- «Визуальный вариант B: платформа крупнее, квадратный значок сервиса расположен справа снизу».
- «Почта — белая `@` на синем; Облако — фирменный белый контур на синем; Chrome — официальный цветной знак».
- «Обновить готовые пары `ios-mail`, `ios-cloud`, `android-mail`, `android-cloud`, сохранив их имена в существующих правилах».
- «Добавить `chrome-mail` и `chrome-cloud`: всего девять встроенных имён»; отдельный `chrome` не добавлять.
- «Базовые `ios`, `android` и `kotlett` сохраняются»; их PNG/SVG должны остаться побайтово прежними.
- «Поставлять согласованные SVG-исходники и готовые прозрачные PNG 128×128».
- «Содержимое внутренних репозиториев в публичный пакет не переносить»; личные корни/JSON/screenshots остаются приватными.
- «Новый генератор, зависимости установщика, схема JSON, настройка layout и загрузка картинок во время startup не нужны».
- Runtime выбора каталога, chpwd/APS/ownership/default reset из PR #5 не переписывать. Dev-проверки только с temporary HOME/fake adapters; реальные install/API/GUI выполняет контроллер после review.
- Пять прежних цветов/корней сохранить; веб Облака `chrome-cloud/#D16D8A`, веб Почты `chrome-mail/#8B8FDC`. Конечный личный набор — семь правил.
- Работа в существующем isolated worktree, ветка `feat/appearance-brand-icons`, база `e90b332`; основной checkout не менять. Во время SDD — scoped snapshots/diffs без промежуточных коммитов; один итоговый product commit/push/PR, без merge/release.
- При работе по Superpowers SDD сохраняй обязательные этапы, артефакты, согласования, тестирование и ревью. Ponytail применяй для выбора простейшей реализации, полностью выполняющей согласованную спецификацию. Упрощение не должно сокращать требования или обходить этапы SDD.

## Review Focus

1. Registry распознаёт Chrome, но installer/export забывает файлы: exact nine-pair assertions в assets/payload/export и установленный helper после удаления checkout (Task 1).
2. Старое встроенное имя продолжает показывать прежний envelope/cloud: сравнить установленную PNG с новым source и изменением release/fingerprint; визуально проверить все шесть пар (Tasks 1–2/controller).
3. Добавление двух правил стирает прежние цвета/других consumers: fixture install пяти → explicit replacement семью → update без источника, точные rules/selection и foreign shell text (Task 1).
4. Составной SVG тянет внешнюю картинку/текстовый wordmark вместо знака: самостоятельные SVG, валидные RGBA 128×128, отсутствие внешних href; native-sized визуальная проверка (Task 1/controller).
5. Чужая графика становится «original MIT», внутренние пути попадают в архив: проверенные public artwork URLs/hashes в notices; exact allowlist/bytes/privacy и отдельный приватный JSON (Tasks 1–2).

## Карта изменений и исходники

- `runtime/assets/appearance/{ios-mail,ios-cloud,android-mail,android-cloud}.{svg,png}`: обновить бейджи. Создать `{chrome-mail,chrome-cloud}.{svg,png}` там же. Другие production assets не добавлять.
- `runtime/appearance.py`: только `BUILTIN_ICONS`. `iterm2_utils/features/shell.py`: только `APPEARANCE_ASSETS` и утративший актуальность комментарий об original drawings. `tools/check_export.py`: четыре новых явных пути.
- `tests/test_appearance_rules.py`, `tests/test_payload.py`, `tests/test_appearance_feature.py`, `tests/test_export.py`: расширить существующие проверки, без новой подсистемы тестов.
- `THIRD_PARTY_NOTICES.md`: различить собственные рисунки и брендовую графику. `README.md`, `CHANGELOG.md`, `docs/{repo-appearance,compatibility}.md`, `skills/iterm2-setup/references/features.md`: девять имён, новый вид, фактическая матрица.

Публичные SVG проверены при подготовке плана. Перед использованием сверить SHA256 исходных bytes; snapshots доступны в приватных design-артефактах. Несовпадение не разрешает подменить источник внутренним файлом.

| Знак | Публичный источник | SHA256 исходника |
| --- | --- | --- |
| Mail `@` | `https://cloud.imgsmail.ru/cloud.mail.ru/hashes/img/portal-header/38ee4afd7a08350c7d70.svg` | `8797246440d02769af6ae58cf3fdd90f9ce56858f02098a0dee5a8b659129897` |
| Облако | `https://cloud.imgsmail.ru/cloud.mail.ru/hashes/img/54cbc3d30f0b1da1d208.svg` | `71706ae50083d481d84e172308b858abba2979b2f90dff08d6d2ee0da0ffb333` |
| Chrome | `https://www.google.com/chrome/static/images/chrome-logo-m100.svg` | `1357dd965397a99cbc937ddd2345a9897d527f7229c8b0f2aeebac97680cc66d` |

Источник Mail — wordmark 135×30: использовать только отдельный path `@` в области 0..30, без текста. Знак сделать белым на квадрате `#0077FF` со скруглением, как в выбранном макете; это описанное преобразование публичного оригинала. Облако и Chrome масштабировать с сохранением пропорций. URL, upstream SHA256, преобразования и владельцев брендов записать в notices; не приписывать графике MIT. Existing `sources.lock.json` для 27 программных источников менять не требуется.

### Task 1: Готовые брендовые пары, registry и полная доставка

**Files:** Все assets, registry/lists, notices и четыре test-файла из карты; пользовательские docs — Task 2.

**Interfaces:** `BUILTIN_ICONS` остаётся frozenset, `APPEARANCE_ASSETS` — явным tuple относительных PNG/SVG paths. `load_rules(path: Path) -> list[dict[str,str]]`, `runtime_payload(context, selection) -> ChangeSet`, schema и CLI не меняются. После задачи доступны девять готовых пар и прежний lifecycle.

- [ ] **Step 1: Расширить failing asset/rules assertions.** В `AppearanceAssetsTests` переименовать `test_all_builtin_icons_have_rgba_png_and_original_svg` без обещания original; exact expected = прежние семь + `chrome-mail`, `chrome-cloud`, set PNG/SVG stems равен ему. Сохранить RGBA `(128,128,8,6)`, CRC, scanlines и transparent top-left. Добавить XML parse/self-contained assertions: ни одного внешнего href/stylesheet/script. `AppearanceRulesTests.test_seven_project_pairs_select_and_outside_does_not` выбирает семь icons из личного набора через generic temporary roots, у Chrome утверждённые цвета, подкаталог выбирает ту же пару, outside возвращает None.
- [ ] **Step 2: Расширить failing delivery assertions.** Existing `test_known_assets_and_helpers_are_installed_without_arbitrary_images` и `test_appearance_delivery_contract` требуют exact nine-pair set; чужой PNG по-прежнему исключён. В `test_installed_icons_selected_after_all_sources_removed` проверять шесть branded pairs + Kotlett + custom через установленный helper после удаления checkout/исходного JSON/PNG: builtin path и bytes соответствуют сохранённым до удаления source bytes, custom content-addressed, outside shell requests reset. Существующий release/fingerprint test направить на изменяемую `android-mail.png`, чтобы проверять именно обновление стабильного имени.
- [ ] **Step 3: Run RED.** `python3 -m unittest tests.test_appearance_rules tests.test_payload tests.test_export -v`. Зафиксировать конкретные отсутствующие Chrome registry/assets/delivery assertions; не считать fixture/import errors полезным RED.
- [ ] **Step 4: Реализовать готовые ассеты.** Использовать подтверждённые public SVG bytes и прежние phone/Android; нарисовать только композицию B, без новых generic logos. Brand badge примерно 58% квадрата справа снизу, платформа примерно 86% ширины и 92% высоты, как в макете. Inline SVG paths/gradients без внешних файлов. Подготовить каждый из шести PNG командой `rsvg-convert --width 128 --height 128 --output NAME.png NAME.svg`; renderer остаётся developer tool, не dependency пакета. Проверить увеличенный и небольшой контактный лист; три base-pairs побайтово равны базе.
- [ ] **Step 5: Расширить прежние registry/lists и notices.** Добавить два имени, четыре пути в export и те же четыре в runtime payload. Никакого glob/autodiscovery вместо allowlist. Notices содержат public URLs/upstream hashes/преобразования, принадлежность Mail и Google, разделение artwork и собственного MIT-кода. Никаких внутренних assets/путей или новых lock/provenance механизмов.
- [ ] **Step 6: Добавить lifecycle regression.** `AppearanceTests.test_web_rules_preserve_existing_five_pairs_and_other_consumers`: install пяти builtin rules вместе с restore/status и foreign shell text; explicit replacement семью с двумя Chrome rules; assert прежние пять triples равны, новые цвета точны, selection/foreign text сохранены. Удалить source config, `appearance_config=None`, existing update сохраняет семь rules и новые PNG. Сохранённое поведение не требует искусственного RED; наличие новых имён обязано зависеть от Step 5.
- [ ] **Step 7: Run GREEN.** `python3 -m unittest tests.test_appearance_rules tests.test_payload tests.test_appearance_feature tests.test_export -v`; `python3 tools/check_export.py`. Все PASS, platform skips записаны; export135 при ровно четырёх добавленных файлах. Scoped snapshot/diff, public-source evidence, exact RED/GREEN и self-review → независимый task review. Без промежуточного commit.

### Task 2: Документация, финальный gate и поставка

**Files:** Пользовательские docs из карты; private reports и later controller acceptance. Product code Task 1 не переписывать без конкретного найденного дефекта.

**Interfaces:** Task 1 предоставляет готовые девять PNG/SVG pairs, installed delivery и notices. Контроллер использует прежние `plan/install --agent codex --features appearance --appearance-config ABS_JSON`, выбранный SDK Python и локальный private mapping.

- [ ] **Step 1: Обновить docs.** Девять встроенных имён и фирменный вариант B; больше не обещать семь исключительно original generic drawings. Старые spec/plan/verification rows не переписывать задним числом. Новые full/live результаты пока pending; не публиковать локальные roots/JSON/screenshots. Для docs искусственный RED не нужен.
- [ ] **Step 2: Один full gate после source freeze.** `python3 -m unittest discover -v`; `/bin/zsh tests/test_appearance_shell.zsh`; `/bin/zsh tests/test_codex_shell.zsh`; `/bin/zsh tests/restore/test_codex.zsh`; `python3 tools/check_sources.py`; `python3 tools/check_skill.py`; `python3 tools/check_export.py`; `python3 tools/build_release.py --destination dist`; `git diff --check`. Требуются PASS с фактическими counts/skip, 27 pinned software sources, skills2, archive135 unique regular files, exact allowlist и 135 byte comparisons, basename-only checksum. Не повторять полный suite без новых source changes или конкретного сомнения.
- [ ] **Step 3: Review gates.** Независимый task review; затем один whole-branch review по binding spec, при findings — одна общая final fix wave и один scoped re-review. Все review notes и решения сохраняются в workspace этого плана. Реальная установка до закрытия code-review gates запрещена.
- [ ] **Step 4: Контроллер готовит локальный JSON.** Read current owned rules через discovery, сохранить before hash/копию приватно. Проверить, что в наличии именно пять ожидаемых rules; сохранить их triples/order, добавить только два web rules из приватного mapping. Если набор уже содержит новые rules, сверить exact значения и не дублировать. Целевые каталоги существуют; недостающие не создавать. Source JSON вне Git, без ручного редактирования installed owned файла.
- [ ] **Step 5: Контроллер делает selected rollout.** Проверить SDK import, выполнить matching plan и install dry-run с одним ABS_JSON; сверить selection и отсутствие конфликтов. Затем matching install. Broad update/уведомления не трогать. Проверить installed config = ожидаемые семь rules, runtime PNG bytes и исходные пять triples/остальные consumers сохранены. Pending API снимать только штатным reconcile после фактического доступа.
- [ ] **Step 6: Контроллер проводит native acceptance.** Предупредить о собственном временном окне; проверить доступность SSD, не отключать его. Сохранять созданные exact IDs немедленно; при неопределённом исходе не повторять создание вслепую. Обычный cd по семи корням/подкаталогам/outside: цвета, шесть новых branded icons, прежний Kotlett и default reset. Exact-window tabbar crop на обычном масштабе подтверждает узнаваемость знаков. Закрыть только свои captured sessions; рабочие tabs не перезапускать. Если native проверка недоступна, отметить конкретный непроверенный пункт.
- [ ] **Step 7: Зафиксировать факты и завершить.** Заполнить compatibility full/live evidence один раз; после docs-only edits повторить только export/build/byte/checksum/whitespace. Privacy/source/status check, один scoped product commit, feature push и Draft PR; дождаться существующего CI. Main не merge, release/tag не publish. Приватные исходники проверки/JSON/снимки и все ledger rulings сохранить отдельно от публичного архива. Старым shell нужна fresh tab или явный exec zsh; автоматически их не менять.

## Self-review плана

Spec покрыта: B/бренды/сохранённые имена/9pairs/PNG128/transparency/public provenance → Task 1; checkout removal/allowlists/lifecycle7/foreign consumers → Task 1; docs/fullgate/privacy и локальный selected rollout/native-sized проверка → Task 2/controller. Все пять Review Focus имеют named tests либо явно native визуальную проверку. Новый runtime API, schema, daemon, generator и зависимости не появляются. План продолжает ранее выбранный пользователем subagent-driven-development; реализация начинается после review этого плана пользователем.
