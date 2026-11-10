---
gsd_state_version: '1.0'
status: planning
progress:
  total_phases: 2
  completed_phases: 1
  total_plans: 0
  completed_plans: 0
  percent: 50
---

# Project State

## Project Reference

See: `.planning/PROJECT.md`.

**Core value:** пользователь за одно сообщение с фото получает правдоподобное
видео со своим лицом; продукт имеет смысл только если реальная генерация и
минимально доступная оплата подтверждены внешними системами.

**Current focus:** Phase 2 — внешние интеграции Higgsfield и оплаты.

## Current Position

Phase: 2 — Внешние интеграции — not started
Plan: детальный план ещё не создан; сначала требуется подтвердить доступ и
выбрать минимальный платёжный маршрут.
Status: discovery and integration gate

Progress: [█████░░░░░] 50% overall, historical baseline complete

## Active Milestones

0. `REPO-01…REPO-03` — CI, agent workflow guide и secret-free demo.
1. `M2.1` — доступы и выбор платёжного провайдера.
2. `M2.2` — live-probe Higgsfield.
3. `M2.3` — live-probe оплаты.
4. `M2.4` — адаптеры и вертикальная проверка.
5. `M2.5` — gate review и решение следующего roadmap.

## Accumulated Context

### Decisions

- Mock/stub baseline сохранён как регрессионная база, но старый активный
  roadmap больше не используется.
- Следующая и единственная активная фаза — Phase 2.
- Внешний платёжный маршрут не предопределён: сначала проверяется фактическая
  доступность API, sandbox/production режима и требований РФ.
- Higgsfield contract считается неподтверждённым до live-probe.
- Live credentials и медиафайлы не коммитятся; обычные тесты не зависят от них.
- Будущие фазы не планируются до результатов двух внешних гейтов.
- Agent-workflow tooling не меняет продуктовый scope: CI, guide и demo нужны для
  воспроизводимой работы без live credentials.

### Pending Inputs

- `HF_KEY_ID`, `HF_KEY_SECRET`, `HF_MODEL` и при необходимости `HF_UPLOAD_URL`;
- `templates/default/source.mp4` и `templates/default/prompt.txt`;
- доступ к выбранному платёжному провайдеру и способу подтверждения платежей;
- решение, нужен ли sandbox или допустим production-safe минимальный платёж.

### Archived Context

Старые требования, планы Phase 1, старый roadmap и UX todo сохранены в
`.planning/archive/2026-11-09-pre-reset/`.

## Blockers / Concerns

- Без Higgsfield credentials нельзя подтвердить контракт и стоимость.
- Без доступного платёжного API нельзя выбрать реализацию `PaymentProvider`.
- `app/worker/loop.py` имеет слабое покрытие; это проверяется после появления
  реального вертикального сценария.
- `.planning/codebase/` содержит карту старого среза и не является источником
  истины для текущей фазы.

## Session Continuity

Last session: 2026-11-09 — roadmap reset initiated.
Stopped at: active Phase 2 documents created; repository agent tooling is next.
Resume file: `.planning/phases/FC-02-vneshnie-integratsii/CONTEXT.md`.
