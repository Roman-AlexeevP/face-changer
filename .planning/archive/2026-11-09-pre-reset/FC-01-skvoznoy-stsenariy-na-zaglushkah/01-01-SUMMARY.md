---
phase: 01-skvoznoy-stsenariy-na-zaglushkah
plan: 01
subsystem: testing
tags: [aiogram, postgres, pytest, mock-engine, e2e]

requires:
  - phase: none
    provides: existing bot/worker skeleton
provides:
  - E2E-тест на заглушках через настоящий Dispatcher
  - фикстура session_factory поверх транзакции теста
  - проверка ledger и удаления фото в одном сценарии
affects: [phase-01-02, phase-01-03, phase-02]

actuals:
  tokens: 3000
  tasks: 3
  commits: 1

tech-stack:
  added: []
  patterns: [fake aiogram session, feed_update E2E, savepoint session factory]

key-files:
  created: [tests/test_e2e_mock.py]
  modified: [tests/conftest.py]

key-decisions:
  - "Telegram заменён RecordingSession(BaseSession), а не прямым вызовом хендлеров"
  - "session_factory поверх session.bind с create_savepoint"
  - "Троттлинг не отключается: monotonic подменён растущим счётчиком"

requirements-completed: [ENTRY-01, ENTRY-02, ENTRY-03, ENTRY-04, ENTRY-05, ENTRY-06, ENTRY-07, ENTRY-08, ENTRY-09, BILL-01, BILL-02, BILL-03, BILL-04, BILL-05, BILL-06, BILL-08, BILL-09, BILL-10, PRIV-01, PRIV-02, PRIV-05, QA-01]

coverage:
  - id: D1
    description: "Пользователь проходит /start → согласие → stub-оплата → фото → mock-видео → delivered"
    requirement: QA-01
    verification:
      - kind: e2e
        ref: "tests/test_e2e_mock.py#test_mock_scenario_end_to_end"
        status: pass
    human_judgment: false
  - id: D2
    description: "Ledger после оплаты: topup + order_paid, без refund, сумма 0"
    requirement: BILL-03
    verification:
      - kind: integration
        ref: "tests/test_e2e_mock.py#test_mock_scenario_end_to_end"
        status: pass
    human_judgment: false
  - id: D3
    description: "Исходное фото удалено после delivered"
    requirement: PRIV-01
    verification:
      - kind: integration
        ref: "tests/test_e2e_mock.py#test_mock_scenario_end_to_end"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-11-08
status: complete
---

# Phase 1: Сквозной сценарий на заглушках Summary

**E2E на заглушках: `/start → согласие → stub-оплата → фото → mock-видео →
delivered`, с проверкой ledger и удаления фото.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-11-08T20:07:00+03:00
- **Completed:** 2026-11-08T20:20:00+03:00
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- Добавлен `tests/test_e2e_mock.py`: настоящий `Dispatcher`, `feed_update`,
  фейковая Telegram-сессия, PostgreSQL и `MockVideoEngine`.
- Добавлена фикстура `session_factory` — приложение работает в той же
  транзакции, что и тест; коммиты становятся savepoint и откатываются.
- Проверено: заказ `delivered`, job `done`, `send_video` один раз, фото
  удалено, ledger `topup` + `order_paid` без `refund`, событие
  `order_delivered`.
- Покрытие выросло с 62% до **76%**; полный прогон — **207 passed**.

## Task Commits

1. **Task 1-3: E2E, фикстура и проверки** — `8c365d7` (test)

**Plan metadata:** `docs(01): контекст, план и итог 01-01` (этот коммит)

## Files Created/Modified

- `tests/test_e2e_mock.py` — фейковая сессия, бот, хелперы и E2E-сценарий.
- `tests/conftest.py` — фикстура `session_factory`.

## Decisions Made

- Фейковая сессия на `BaseSession`, а не monkeypatch хендлеров: тест проходит
  через реальный `Dispatcher` и middleware.
- `session_factory` поверх `session.bind` с `create_savepoint`: изоляция теста
  сохраняется, приложение видит свои коммиты.
- Троттлинг не отключается; `monotonic` подменён растущим счётчиком.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Style] Ruff ASYNC109/B009 в тесте**
- **Found during:** Task 3 (линт)
- **Issue:** `timeout` в сигнатуре `make_request` и `getattr(method, "chat_id")`.
- **Fix:** `**kwargs` вместо `timeout`; прямое `method.chat_id`.
- **Files modified:** `tests/test_e2e_mock.py`
- **Verification:** `.\tasks.cmd lint` — All checks passed.
- **Committed in:** `8c365d7`

---

**Total deviations:** 1 auto-fixed (style)
**Impact on plan:** Без изменений поведения; продакшн-код не менялся.

## Issues Encountered

- `MockVideoEngine` не возвращает `request_id`; resume и повторы проверяются
  в плане 01-02 с фейковым движком, а не в этом E2E.
- Полный прогон в Docker: 207 passed, coverage 76%, 26.68s.

## User Setup Required

None — внешние сервисы не нужны, всё на заглушках.

## Next Phase Readiness

- Готово к 01-02: `request_id`, resume, retry 2/5/15, timeout, watchdog.
- Затем 01-03: матрица ошибок, ledger и удаление фото в ветках отказа.
- 01-04: полная проверка и docs.

---
*Phase: 01-сквозной-сценарий-на-заглушках*
*Completed: 2026-11-08*
