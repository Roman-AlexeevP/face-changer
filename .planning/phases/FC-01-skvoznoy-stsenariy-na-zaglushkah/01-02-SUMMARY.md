---
phase: 01-skvoznoy-stsenariy-na-zaglushkah
plan: 02
subsystem: worker
tags: [retry, request-id, watchdog, postgres, aiogram, higgsfield]

requires:
  - phase: 01-01
    provides: E2E на заглушках и фикстура session_factory
provides:
  - request_id в JobSpec и jobs, resume без повторного submit
  - политика повторов 2/5/15 и возврат заказа в queued
  - watchdog зависших running-заданий
  - коды network/engine_5xx/rate_limited в транспорте
affects: [phase-01-03, phase-02]

actuals:
  tokens: 12000
  tasks: 3
  commits: 1

tech-stack:
  added: []
  patterns: [submit hook, requeue order, watchdog loop, queue module split]

key-files:
  created: [app/worker/retry.py, app/worker/job_state.py, app/worker/notify.py, app/worker/watchdog.py, app/db/job_queue.py, tests/test_retry.py, tests/test_pipeline_retry.py, tests/test_watchdog.py]
  modified: [app/engines/base.py, app/engines/higgsfield.py, app/engines/mock.py, app/engines/transport.py, app/domain/order_service.py, app/db/repo.py, app/worker/pipeline.py, app/worker/loop.py, tests/test_higgsfield_engine.py, tests/test_repo_integration.py, tests/test_e2e_mock.py]

key-decisions:
  - "request_id сохраняется через keyword-only on_submit hook"
  - "3 повтора после первой попытки: 2/5/15 секунд, всего 4 попытки"
  - "request_id сохраняется при retry/reschedule: следующий запуск продолжает polling, а не submit"
  - "очередь заданий вынесена в job_queue.py, чтобы repo остался < 300 строк"

requirements-completed: [GEN-01, GEN-02, GEN-03, GEN-04, GEN-05, GEN-06, GEN-11, QA-03]

coverage:
  - id: D1
    description: "request_id сохраняется после submit и переживает рестарт"
    requirement: GEN-03
    verification:
      - kind: unit
        ref: "tests/test_higgsfield_engine.py#test_submit_hook_receives_request_id"
        status: pass
      - kind: unit
        ref: "tests/test_higgsfield_engine.py#test_resume_polls_request_without_submit"
        status: pass
    human_judgment: false
  - id: D2
    description: "Повторяемая ошибка возвращает заказ в queued, job в new/attempt+1 без refund"
    requirement: GEN-06
    verification:
      - kind: integration
        ref: "tests/test_pipeline_retry.py#test_retryable_error_reschedules_job"
        status: pass
      - kind: unit
        ref: "tests/test_retry.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "После исчерпания повторов заказ refunded, ровно один refund"
    requirement: GEN-06
    verification:
      - kind: integration
        ref: "tests/test_pipeline_retry.py#test_exhausted_retries_fail_and_refund_once"
        status: pass
    human_judgment: false
  - id: D4
    description: "Watchdog возвращает зависший running в new/attempt+1"
    requirement: GEN-11
    verification:
      - kind: integration
        ref: "tests/test_watchdog.py#test_stale_running_is_requeued"
        status: pass
    human_judgment: false
  - id: D5
    description: "no_credits и moderated не повторяются"
    requirement: GEN-08
    verification:
      - kind: integration
        ref: "tests/test_pipeline_retry.py#test_no_credits_is_not_retried"
        status: pass
      - kind: integration
        ref: "tests/test_pipeline_retry.py#test_moderated_is_not_retried"
        status: pass
    human_judgment: false

duration: 30min
completed: 2026-11-08
status: complete
---

# Phase 1: Сквозной сценарий на заглушках Summary

**request_id/resume, 3 повтора с backoff 2/5/15 и watchdog; 226 тестов,
покрытие 80%.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-11-08T20:20:00+03:00
- **Completed:** 2026-11-08T20:45:00+03:00
- **Tasks:** 3
- **Files modified:** 11 + 8 новых

## Accomplishments

- `JobSpec.request_id` и keyword-only `on_submit`: движок пишет `jobs.request_id`
  сразу после submit; при рестарте polling продолжается без нового submit.
- `EngineFailed` получил instance-код; транспорт различает `network`,
  `engine_5xx`, `rate_limited`.
- `app/worker/retry.py`: 3 повтора, backoff 2/5/15, повторяемые коды.
- `retry_job`: заказ `running → queued`, job `new` с `attempt+1`, новый
  `idempotency_key`, событие `job_retry`, без refund.
- `watchdog`: `running` старше `JOB_STALE_MINUTES` возвращается в `new` с
  `attempt+1`; `run_pool` запускает watchdog раз в 60 секунд.
- Полный прогон: **226 passed**, coverage **80%**, lint чистый.

## Task Commits

1. **Task 1-3: request_id, retry, watchdog** — `feat(worker): request_id,
   resume, retry и watchdog` (этот коммит)

## Files Created/Modified

- `app/engines/base.py` — `JobSpec.request_id`, `SubmitHook`, `EngineFailed.code`.
- `app/engines/higgsfield.py` — resume polling, `status_url_for`.
- `app/engines/transport.py` — коды `network`/`engine_5xx`/`rate_limited`.
- `app/domain/order_service.py` — `requeue`, переход `running → queued`.
- `app/db/job_queue.py` — очередь, claim, finish, reschedule, stale.
- `app/db/repo.py` — только заказы, пользователи, ledger, события.
- `app/worker/retry.py` — чистая политика повторов.
- `app/worker/job_state.py` — сохранение request_id и retry.
- `app/worker/notify.py` — уведомления пользователю.
- `app/worker/watchdog.py` — возврат зависших задач.
- `app/worker/pipeline.py` — hook, retry-ветки, split на модули.
- `app/worker/loop.py` — запуск watchdog.
- `tests/test_retry.py`, `tests/test_pipeline_retry.py`, `tests/test_watchdog.py` — новые тесты.
- `tests/test_higgsfield_engine.py` — hook, resume, код 5xx.

## Decisions Made

- 4 попытки = первая + 3 повтора; это соответствует backoff 2/5/15.
- `request_id` не сбрасывается при retry: если submit уже был, следующий запуск
  продолжает polling. Это лучше плана, где стояло `request_id=None`.
- Очередь вынесена в `app/db/job_queue.py`, уведомления — в `notify.py`, чтобы
  `repo.py` и `pipeline.py` остались в пределах 300 строк.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Architecture] Модули превысили 300 строк**
- **Found during:** Task 1-2
- **Issue:** `repo.py` вырос до 347, `pipeline.py` — до 304.
- **Fix:** вынесены `job_queue.py`, `job_state.py`, `notify.py`.
- **Verification:** `repo.py` 214, `pipeline.py` 279; lint и тесты зелёные.
- **Committed in:** этот коммит.

**2. [Rule 3 - Correctness] request_id терялся при retry**
- **Found during:** Task 2
- **Issue:** `reschedule_job` сбрасывал `request_id`, что приводило к повторному
  submit после уже принятой генерации.
- **Fix:** `request_id` сохраняется; resume polling вместо submit.
- **Verification:** `test_resume_polls_request_without_submit`.
- **Committed in:** этот коммит.

---

**Total deviations:** 2 auto-fixed (architecture, correctness)
**Impact on plan:** без расширения объёма; качество и лимиты соблюдены.

## Issues Encountered

- `.\tasks.cmd test` с `--build` один раз упал на TLS-таймауте зеркала Docker
  при pull `python:3.12-slim`. Тесты прогнаны на существующем образе:
  `docker compose --profile test run --rm tests` — 226 passed.
- `app/worker/loop.py` остаётся 0% покрытия: `run_pool`/watchdog-loop не
  тестируются, только `requeue_stale`. Это задача следующих тестов.

## User Setup Required

None — живые ключи Higgsfield не нужны.

## Next Phase Readiness

- 01-03: матрица ошибок, ledger и удаление фото в ветках отказа.
- После 01-03 — 01-04: финальная проверка и docs.

---
*Phase: 01-сквозной-сценарий-на-заглушках*
*Completed: 2026-11-08*
