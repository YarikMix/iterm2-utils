# Live migration prerequisites — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax for tracking.

**Goal:** Устранить подтверждённые препятствия применения согласованной native-миграции.

**Architecture:** Сохранить pure builders/receipts/CAS. Исправить только сканирование
TOML keys, read-only version probe и узкий список проверенных notification versions.
Controller применяет CLI отдельно от разработки после полного review.

**Tech Stack:** Python 3.11+, stdlib, unittest, macOS + zsh.

**Spec:** docs/superpowers/specs/2026-10-24-live-migration-prerequisites.md

## Global Constraints

- Не читать/менять реальные настройки в workers; только TemporaryDirectory/fake runner.
- Сохранять foreign settings и исходный текст всех нетронутых statements.
- Не разрешать настоящие dotted/inline edits; quoted single-component key допустим.
- terminal-notifier probe: `-version`, без отправки баннеров.
- Только Codex 0.163.0 и 0.164.0 получают approval-notifications capability.
- Никаких новых событий hooks, Alt+Enter versions или error guarantees.
- Не менять foreign-notifications guard, vendor hashes, runtime status budgets.

## Review Focus

1. Quoted имя с точкой не превращается в dotted path; проверяет Task1.
2. Quoted/multiline соседнее значение остаётся побайтно тем же; Task1.
3. Отсутствующий/неработающий terminal-notifier остаётся missing; Task1.
4. 0.165.0/unknown не получают capabilities по сравнению версии; Task1.
5. Approval-only policy обратима и не меняет чужие настройки; Task1.

## Task 1: Narrow migration prerequisites

**Files:** Modify `iterm2_utils/config/tomlfile.py`, `iterm2_utils/discovery.py`,
`iterm2_utils/features/notifications.py` (только актуальность сообщения),
`tests/test_config.py`, `tests/test_discovery.py`, `tests/test_notifications_feature.py`,
`docs/compatibility.md` (добавить source-level evidence, не выдумывать live/CI).

**Interfaces:** Существующие `_spans(content)`, `patch(content,pointer,value,remove=False)`,
`discover(paths,runner,agents=...)` и `notifications.build(context,selection)` без новых API.

- [ ] **Step 1: RED.** Добавить meaningful regressions: quoted basic/literal keys,
  quoted replacement roundtrip, dot-inside-name, multiline preservation; dotted/inline
  negative cases; notifier runner rejecting --version but accepting -version;
  0.164.0 approval capability/reversible policy and 0.165.0/unknown blocked.
- [ ] **Step 2:** Run `python3 -m unittest tests.test_config tests.test_discovery tests.test_notifications_feature -v`; зафиксировать expected failures без production edits.
- [ ] **Step 3:** Минимальные fixes строго по spec. Для keys использовать tomllib
  разбор реального key token, не split по точке и не вывод значения в diagnostics.
- [ ] **Step 4:** Run focused suites GREEN; self-review preservation и narrow version gates.
- [ ] **Step 5:** Run один полный `python3 -m unittest discover -s tests -t . -v`, оба zsh
  набора, check_sources/check_skill/check_export; новые broad reruns только при failure.
- [ ] **Step 6:** Path-scoped commit fixes/tests/docs с `fix: unblock native migration for current Codex settings`.

## После task/final gates — controller

Preview status+restore --adopt-legacy вне sandbox (macOS notifier probe требует окружения).
Применить штатным CLI, затем preview/install notifications. Проверить прежние clipboard/
профиль/MCP/Claude и новые receipt/runtime/hooks без raw secrets. Отдельно сообщить
pending trust/new-session и реальную границу live-verification. Публикация исправлений
и merge main не входят в текущий запрос применения миграции.
