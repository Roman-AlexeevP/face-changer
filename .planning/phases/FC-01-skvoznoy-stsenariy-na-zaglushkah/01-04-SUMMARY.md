---
phase: 01-skvoznoy-stsenariy-na-zaglushkah
plan: 04
subsystem: database
tags: [template, seed, migration, consent, docs]

requires:
  - phase: 01-03
    provides: ошибки и удаление фото
provides:
  - is_default и миграция 0003
  - upsert prompt.txt при старте
  - E2E-проверка consent_version/consent_at
  - docs/architecture.md по фактическому VideoEngine и job-статусам
affects: [phase-02]

actuals:
  tokens: 7000
  tasks: 3
  commits: 1

tech-stack:
  added: []
  patterns: [template upsert, default template, migration 0003]

key-files:
  created: [app/db/migrations/versions/0003_template_default.py]
  modified: [app/db/models.py, app/db/seed.py, app/db/repo.py, docs/architecture.md, tests/test_models.py, tests/test_seed.py, tests/test_e2e_mock.py]

key-decisions:
  - "is_default — колонка templates; ровно один default, два — ConfigError"
  - "seed делает upsert по key, поэтому prompt.txt применяется рестартом"
  - "config.yaml не вводим: промпт живёт в prompt.txt, остальное — в БД/настройках"

requirements-completed: [TMPL-01, TMPL-02, TMPL-03, TMPL-04, PRIV-06, QA-06, QA-07]

coverage:
  - id: D1
    description: "Шаблон upsert-ится по key, prompt.txt применяется рестартом"
    requirement: TMPL-02
    verification:
      - kind: integration
        ref: "tests/test_seed.py#test_seed_upserts_prompt_and_keeps_one_default"
        status: pass
    human_judgment: false
  - id: D2
    description: "Ровно один is_default; два default — ConfigError"
    requirement: TMPL-03
    verification:
      - kind: integration
        ref: "tests/test_seed.py#test_two_defaults_are_config_error"
        status: pass
    human_judgment: false
  - id: D3
    description: "Схема содержит is_default"
    requirement: TMPL-01
    verification:
      - kind: unit
        ref: "tests/test_models.py#test_columns_match_architecture"
        status: pass
    human_judgment: false
  - id: D4
    description: "Согласие сохраняет версию и время"
    requirement: PRIV-06
    verification:
      - kind: e2e
        ref: "tests/test_e2e_mock.py#test_mock_scenario_end_to_end"
        status: pass
    human_judgment: false
  - id: D5
    description: "Архитектурный тест чистоты domain"
    requirement: QA-06
    verification:
      - kind: unit
        ref: "tests/test_architecture.py#test_domain_imports_only_pure_modules"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-11-08
status: complete
---

# Phase 1: Сквозной сценарий на заглушках Summary

**Шаблон upsert-ится с is_default, миграция 0003 применена, бот снова в
polling; 248 тестов, покрытие 81%.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-11-08T20:45:00+03:00
- **Completed:** 2026-11-08T21:05:00+03:00
- **Tasks:** 3
- **Files modified:** 7 + 1 новый

## Accomplishments

- `templates.is_default` + миграция `0003_template_default`; старый default
  помечен true.
- `seed_default_template` — upsert по `key`, обновляет prompt/title/цены;
  два default → `ConfigError`.
- `get_default_template` фильтрует `is_active` + `is_default`.
- E2E проверяет `consent_version='v1'` и `consent_at=NOW`.
- `docs/architecture.md` обновлён: `VideoEngine.generate` + `on_submit`,
  `request_id`, job-статусы `new/running/done/failed`, `is_default`,
  `running → queued`.
- Smoke-старт: bot `Start polling`, worker `worker started`,
  `templates.default.is_default=true`.
- Полный прогон: **248 passed**, coverage **81%**, lint чистый.

## Task Commits

1. **Task 1-3: шаблон, docs, smoke** — `feat(db): шаблон is_default и upsert`
   (этот коммит)

## Files Created/Modified

- `app/db/models.py` — `is_default`.
- `app/db/migrations/versions/0003_template_default.py` — миграция.
- `app/db/seed.py` — upsert и проверка одного default.
- `app/db/repo.py` — `get_template_by_key`, `count_default_templates`.
- `docs/architecture.md` — контракты и состояния.
- `tests/test_models.py`, `tests/test_seed.py`, `tests/test_e2e_mock.py`.

## Decisions Made

- `config.yaml` не вводим: проект уже использует `prompt.txt`; этого
  достаточно для «контент без релиза».
- `is_default` — единственный признак default; `get_default_template` не
  угадывает по `id`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Старый migrate-образ не содержал 0003**
- **Found during:** Task 3
- **Issue:** `docker compose --profile tools run --rm migrate` использовал
  старый образ без новой ревизии; `alembic upgrade head` не применил 0003.
- **Fix:** применил `docker compose run --rm bot alembic upgrade head` из
  свежего образа; перезапустил bot/worker.
- **Verification:** `templates.is_default` существует, bot `Start polling`.
- **Impact:** в обычном `tasks.cmd up` migrate собирается заново, поэтому
  проблема относится только к ручному запуску старого образа.

---

**Total deviations:** 1 auto-fixed (blocking)
**Impact on plan:** без изменения кода.

## Issues Encountered

- `.\tasks.cmd test` с `--build` падает на TLS-таймауте Docker-зеркала;
  полный прогон шёл на существующем образе.
- Ручной Telegram smoke-test не выполнен: нужен пользователь.

## User Setup Required

Пользователю: открыть бота и пройти `/start → согласие → оплата → фото →
видео`. Бот уже запущен на `ENGINE=mock`, `PAYMENT_PROVIDER=stub`.

## Next Phase Readiness

- Фаза 1 готова к ручному подтверждению.
- После подтверждения — phase 2 (живой Higgsfield), нужны ключи HF,
  `source.mp4`, `prompt.txt`.

---
*Phase: 01-сквозной-сценарий-на-заглушках*
*Completed: 2026-11-08*
