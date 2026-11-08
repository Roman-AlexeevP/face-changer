---
phase: 01-skvoznoy-stsenariy-na-zaglushkah
plan: 03
subsystem: worker
tags: [errors, refund, photo-retention, privacy, watchdog]

requires:
  - phase: 01-02
    provides: retry/watchdog и request_id
provides:
  - нормализация кодов ошибок и тексты для пользователя
  - санитизированный raw в events для unknown
  - удаление фото при провале постановки в очередь
  - TTL-очистка фото старше 15 минут
affects: [phase-01-04, phase-02]

actuals:
  tokens: 8000
  tasks: 3
  commits: 1

tech-stack:
  added: []
  patterns: [error normalization, raw sanitization, photo TTL cleanup]

key-files:
  created: [app/worker/errors.py, tests/test_errors.py]
  modified: [app/worker/pipeline.py, app/worker/job_state.py, app/worker/outcomes.py, app/worker/watchdog.py, app/bot/handlers/upload.py, app/bot/texts.py, tests/test_pipeline_retry.py, tests/test_e2e_mock.py, tests/test_watchdog.py]

key-decisions:
  - "Публичные коды: timeout, moderated, no_credits, engine_5xx, network, bad_input, engine_failed, unknown"
  - "Неизвестный код провайдера становится unknown, а не уходит в БД как есть"
  - "raw сохраняется в events только для unknown и после редакции url/photo/token"
  - "Фото удаляется и при провале queue_order, и по TTL 15 минут"

requirements-completed: [GEN-07, GEN-08, GEN-09, GEN-10, PRIV-02, PRIV-03]

coverage:
  - id: D1
    description: "Коды ошибок нормализованы в публичный набор"
    requirement: GEN-09
    verification:
      - kind: unit
        ref: "tests/test_errors.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "moderated и no_credits не повторяются"
    requirement: GEN-07
    verification:
      - kind: integration
        ref: "tests/test_pipeline_retry.py#test_moderated_is_not_retried"
        status: pass
      - kind: integration
        ref: "tests/test_pipeline_retry.py#test_no_credits_is_not_retried"
        status: pass
    human_judgment: false
  - id: D3
    description: "unknown сохраняет санитизированный raw в events"
    requirement: GEN-10
    verification:
      - kind: integration
        ref: "tests/test_pipeline_retry.py#test_unknown_provider_code_is_sanitized"
        status: pass
    human_judgment: false
  - id: D4
    description: "Провал постановки в очередь удаляет сохранённое фото"
    requirement: PRIV-02
    verification:
      - kind: e2e
        ref: "tests/test_e2e_mock.py#test_queue_failure_deletes_photo"
        status: pass
    human_judgment: false
  - id: D5
    description: "Фото старше 15 минут удаляются watchdog-очисткой"
    requirement: PRIV-03
    verification:
      - kind: unit
        ref: "tests/test_watchdog.py#test_cleanup_old_photos_removes_only_expired"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-11-08
status: complete
---

# Phase 1: Сквозной сценарий на заглушках Summary

**Матрица ошибок нормализована, unknown-raw санитизирован, фото удаляется при
провале очереди и по TTL; 246 тестов, покрытие 81%.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-11-08T20:25:00+03:00
- **Completed:** 2026-11-08T20:45:00+03:00
- **Tasks:** 3
- **Files modified:** 9 + 2 новых

## Accomplishments

- `app/worker/errors.py`: публичные коды, внутренние коды и алиасы
  `unknown_status`/`bad_response`; неизвестный код провайдера → `unknown`.
- `pipeline` нормализует код до retry/fail; `unknown` сохраняет
  санитизированный `raw` в `events.engine_unknown`.
- `texts.FAILURE_TEXTS` получил `timeout`, `network`, `engine_5xx`, `bad_input`.
- `accept_photo` удаляет фото, если `queue_order` упал с `LookupError` или
  `IntegrityError`; пользователь получает `STORAGE_ERROR`.
- `watchdog.cleanup_old_photos` удаляет `photo-*.jpg` старше
  `STORAGE_URL_TTL_MIN` (15 минут) и вызывается в цикле сторожа.
- Полный прогон: **246 passed**, coverage **81%**, lint чистый.

## Task Commits

1. **Task 1-3: ошибки, raw, фото** — `feat(worker): матрица ошибок и удаление
   фото` (этот коммит)

## Files Created/Modified

- `app/worker/errors.py` — `normalize_error_code`.
- `app/worker/outcomes.py` — `raw` в `Outcome`, `sanitize_raw`.
- `app/worker/job_state.py` — `record_engine_raw`.
- `app/worker/pipeline.py` — нормализация, запись raw, retry/fail.
- `app/worker/watchdog.py` — `cleanup_old_photos`.
- `app/bot/handlers/upload.py` — удаление фото при сбое очереди.
- `app/bot/texts.py` — тексты новых кодов.
- `tests/test_errors.py`, `tests/test_pipeline_retry.py`, `tests/test_e2e_mock.py`, `tests/test_watchdog.py`.

## Decisions Made

- `unknown` — единственный код для неразобранного ответа; он не повторяется.
- `engine_failed` остаётся повторяемым; `unknown` — нет.
- Raw хранится только для `unknown`, чтобы не раздувать `events`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Privacy] Raw мог содержать подписанные URL**
- **Found during:** Task 1
- **Issue:** `EngineResult.raw` сохранялся бы как есть.
- **Fix:** `sanitize_raw` редактирует ключи url/photo/image/signed/download/token/secret.
- **Verification:** `test_unknown_provider_code_is_sanitized`.
- **Committed in:** этот коммит.

---

**Total deviations:** 1 auto-fixed (privacy)
**Impact on plan:** без расширения объёма.

## Issues Encountered

- `.\tasks.cmd test` с `--build` падает на TLS-таймауте Docker-зеркала;
  использован существующий образ: `docker compose --profile test run --rm tests`.
- `app/worker/loop.py` по-прежнему 0% покрытия (`run_pool`/watchdog-loop).

## User Setup Required

None.

## Next Phase Readiness

- 01-04: шаблон как данные (`TMPL-01…04`), consent evidence (`PRIV-06`),
  архитектурный тест (`QA-06`), финальная проверка и docs.

---
*Phase: 01-сквозной-сценарий-на-заглушках*
*Completed: 2026-11-08*
