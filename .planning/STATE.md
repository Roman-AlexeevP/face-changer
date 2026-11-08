---
gsd_state_version: '1.0'
status: executing
progress:
  total_phases: 6
  completed_phases: 0
  total_plans: 20
  completed_plans: 3
  percent: 15
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-11-08)

**Core value:** пользователь за одно сообщение с фото получает правдоподобное
видео со своим лицом; путь «фото → оплата → видео → доставка» работает даже
если всё остальное сломается.
**Current focus:** Phase 1 — Сквозной сценарий на заглушках.

## Current Position

Phase: 1 of 6 (Сквозной сценарий на заглушках)
Plan: 3 of 4 in current phase
Status: In progress
Last activity: 2026-11-08 — 01-03 завершён: матрица ошибок, raw, удаление
фото; 246 тестов, покрытие 81%, lint чистый.

Progress: [██░░░░░░░░] 15%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: 21.7 min
- Total execution time: 1.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Сквозной сценарий | 3/4 | 65 min | 21.7 min |

**Recent Trend:**
- Last 5 plans: 15 min, 30 min, 20 min
- Trend: Stable

## Accumulated Context

### Decisions

- Phase 1: mock-first — ключей Higgsfield нет, сначала весь путь на заглушках.
- E2E: настоящий `Dispatcher` + `feed_update`, фейковая `BaseSession`, реальная
  PostgreSQL; `session_factory` поверх транзакции теста.
- `request_id` пишется через `on_submit` hook и не теряется при retry:
  следующий запуск продолжает polling, а не submit.
- Повторы: первая попытка + 3 повтора, backoff 2/5/15; `no_credits` и
  `moderated` не повторяются.
- Коды ошибок нормализуются; неизвестный код провайдера → `unknown`, raw
  санитизируется и пишется в `events`.
- Фото удаляется при терминальном статусе, при сбое очереди и по TTL 15 минут.
- v1: бесплатного реролла нет; «Ещё раз» создаёт новый оплаченный заказ.
- `no_credits` — `failed` + `error_code=no_credits`, пауза продаж 60 минут.
- `tasks.ps1` сохранён в UTF-8 с BOM; `.\tasks.cmd test` работает.
- OpenSpec переведён в `docs/archive/openspec/`; действующий процесс — GSD.

### Pending Todos

- 01-04: TMPL-01…04, PRIV-06, QA-06, финальная проверка и docs.

### Blockers/Concerns

- Phase 2 (живой Higgsfield) заблокирована: `HF_KEY_ID`, `HF_KEY_SECRET`,
  `HF_MODEL` пусты; нет `templates/default/source.mp4` и `prompt.txt`.
- `.planning/codebase/` имеет штамп `8cdc2ab`, HEAD ушёл вперёд — карту нужно
  перештамповать после фазы 1.
- `app/worker/loop.py` — 0% покрытия: `run_pool` и watchdog-loop не тестируются.
- `.\tasks.cmd test` с `--build` падает на TLS-таймауте Docker-зеркала; тесты
  идут на существующем образе без `--build`.

## Deferred Items

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| Billing | Бесплатный реролл (один, после delivered) | v2 | 2026-11-08 | v1.0 |

## Session Continuity

Last session: 2026-11-08 20:45
Stopped at: Phase 1 plan 01-03 complete; next — 01-04
Resume file: .planning/phases/FC-01-skvoznoy-stsenariy-na-zaglushkah/01-03-SUMMARY.md
