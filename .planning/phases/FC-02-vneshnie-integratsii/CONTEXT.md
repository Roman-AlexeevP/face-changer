# Phase 2 Context: Внешние интеграции

## Intent

Сначала подтвердить две вещи, без которых дальнейшие продуктовые фазы не имеют
смысла:

1. Higgsfield действительно принимает входные данные и возвращает пригодное
   видео по фактическому контракту.
2. Для проекта существует минимальный доступный платёжный путь, который можно
   безопасно связать с заказом и ledger.

Это discovery-to-implementation фаза: сначала live facts, затем минимальные
правки адаптеров, а не реализация по предположениям из документации.

## Existing baseline

Исторический mock/stub vertical slice завершён и сохранён в
`.planning/archive/2026-11-09-pre-reset/`. Его тесты должны оставаться зелёными
и служат регрессией, но не определяют новые milestones.

## Repository showcase artifacts

Before M2.1, complete the supporting requirements:

- `REPO-01`: GitHub Actions runs lint and the full Docker test suite;
- `REPO-02`: `docs/agent-workflow.md` explains the repeatable agent loop;
- `REPO-03`: `tasks.cmd demo` runs the mock E2E path without live secrets.

These artifacts make the phase reproducible for a new agent or reviewer and do
not change the external integration scope.

## Milestone sequence

### M2.1 — Access and decision

**Question:** к каким внешним системам реально есть доступ и какой платёжный
маршрут минимален?

**Evidence:** credentials checklist, sandbox/production-safe режим, callback
модель, ограничения по РФ, стоимость доступа.

**Decision:** выбран провайдер оплаты и способ подтверждения либо записан blocker.

### M2.2 — Higgsfield probe

**Question:** соответствует ли реальный API предположениям в
`docs/higgsfield-contract.md`?

**Evidence:** auth, submit, upload/public URLs, request/status fields, terminal
statuses, result URL, error payloads, latency and cost.

**Decision:** `go` на адаптер и один тестовый заказ либо `stop` с причиной.

### M2.3 — Payment probe

**Question:** можно ли провести минимальный платёж и получить надёжное событие
подтверждения?

**Evidence:** invoice/payment creation, amount, idempotency, success/cancel/
repeat event, receipt/fiscalization constraints.

**Decision:** `go` на `PaymentProvider` либо fallback/stop.

### M2.4 — Adapters and vertical check

После подтверждения внешних форматов:

- исправить Higgsfield adapter только по фактическим ответам;
- реализовать выбранный payment adapter;
- прогнать один vertical scenario;
- проверить order transition, ledger, `request_id` и duplicate safety.

### M2.5 — Gate review

Зафиксировать:

- реальные контракты;
- секреты и environment checklist;
- стоимость и задержки;
- известные failure modes;
- решение о следующем roadmap.

## Open decisions

- Telegram Payments или прямой API провайдера — решается по доступности и
  требованиям проекта, не заранее.
- Sandbox или production-safe платёж — зависит от возможностей выбранного
  провайдера.
- Нужен ли upload Higgsfield — проверяется probe с публичными URL до multipart.
- Какой минимальный template/source допустим для первого реального заказа.

## Non-goals

На этой фазе не расширяем каталог, не строим админку, не внедряем S3/Redis,
не делаем полноценную платёжную бухгалтерию и не планируем следующие фазы до
получения evidence по обоим гейтам.

## Exit artifact

После M2.5 должен существовать decision record с `go`/`stop` по каждому гейту и
основанием в измеренных данных. Только после этого создаётся следующий активный
roadmap.
