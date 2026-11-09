---
gsd_state_version: '1.0'
status: planning
progress:
  total_phases: 6
  completed_phases: 1
  total_plans: 20
  completed_plans: 4
  percent: 20
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-11-08)

**Core value:** пользователь за одно сообщение с фото получает правдоподобное
видео со своим лицом; путь «фото → оплата → видео → доставка» работает даже
если всё остальное сломается.
**Current focus:** Phase 1 завершена; Phase 2 на паузе.

## Current Position

Phase: 1 of 6 (Сквозной сценарий на заглушках) — Complete
Plan: 4 of 4 in current phase
Status: Phase 1 complete; Phase 2 not started (по решению пользователя)
Last activity: 2026-11-08 — ручной позитивный прогон пройден; зафиксирован
UX-долг «Ещё раз»: нужен каталог и явная оплата вместо мгновенного заказа.

Progress: [██░░░░░░░░] 20%

## Performance Metrics

**Velocity:**
- Total plans completed: 4
- Average duration: 21.25 min
- Total execution time: 1.4 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Сквозной сценарий | 4/4 | 85 min | 21.25 min |

**Recent Trend:**
- Last 5 plans: 15 min, 30 min, 20 min, 20 min
- Trend: Stable

## Accumulated Context

### Decisions

- Phase 1: mock-first — ключей Higgsfield нет, сначала весь путь на заглушках.
- Phase 1 подтверждена ручным позитивным прогоном в Telegram.
- E2E: настоящий `Dispatcher` + `feed_update`, фейковая `BaseSession`, реальная
  PostgreSQL; `session_factory` поверх транзакции теста.
- `request_id` пишется через `on_submit` hook и не теряется при retry:
  следующий запуск продолжает polling, а не submit.
- Повторы: первая попытка + 3 повтора, backoff 2/5/15; `no_credits` и
  `moderated` не повторяются.
- Коды ошибок нормализуются; неизвестный код провайдера → `unknown`, raw
  санитизируется и пишется в `events`.
- Фото удаляется при терминальном статусе, при сбое очереди и по TTL 15 минут.
- Шаблон — upsert по `key`, `is_default` один; `prompt.txt` применяется
  рестартом.
- v1: бесплатного реролла нет; «Ещё раз» создаёт новый оплаченный заказ.
- UX-долг: «Ещё раз» сейчас сразу создаёт заказ и проводит stub-оплату; нужно
  снова показать каталог/шаблон и оплатить только после подтверждения.
  Записано в `ENTRY-V2-01` и todo.
- `no_credits` — `failed` + `error_code=no_credits`, пауза продаж 60 минут.
- `tasks.ps1` сохранён в UTF-8 с BOM; `.\tasks.cmd test` работает.
- OpenSpec переведён в `docs/archive/openspec/`; действующий процесс — GSD.

### Pending Todos

- [2026-11-08] [ux] «Ещё раз»: показывать каталог шаблонов заново, а не сразу
  оплачивать — [todo](.planning/todos/pending/2026-11-08-again-catalog.md) —
  Needs implementation in v2; v1 currently auto-pays.

### Blockers/Concerns

- Phase 2 (живой Higgsfield) не начата по решению пользователя. Для старта
  нужны `HF_KEY_ID`, `HF_KEY_SECRET`, `HF_MODEL`, `templates/default/source.mp4`
  и `prompt.txt`.
- `.planning/codebase/` имеет штамп `8cdc2ab`, HEAD ушёл вперёд — карту нужно
  перештамповать.
- `app/worker/loop.py` — 0% покрытия: `run_pool` и watchdog-loop не тестируются.
- `.\tasks.cmd test` с `--build` падает на TLS-таймауте Docker-зеркала; тесты
  идут на существующем образе без `--build`.

## Deferred Items

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| Billing | Бесплатный реролл (один, после delivered) | v2 | 2026-11-08 | v1.0 |
| UX | «Ещё раз»: каталог заново, затем оплата | v2 | 2026-11-08 | v1.0 |

## Session Continuity

Last session: 2026-11-08 21:10
Stopped at: Phase 1 complete; Phase 2 not started; UX-долг «Ещё раз» записан
Resume file: .planning/todos/pending/2026-11-08-again-catalog.md
