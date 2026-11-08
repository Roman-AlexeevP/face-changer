# Roadmap: Face Changer

## Overview

Путь от работающего mock-сценария к живому продукту: сначала закрепить
пользовательский путь и денежную логику на заглушках, затем подтвердить
контракт Higgsfield живым заказом, потом довести доставку, эксплуатацию и
реальную оплату. Каждая фаза заканчивается проверяемым поведением, а не
галочкой в задаче.

## Phases

- [x] **Phase 1: Сквозной сценарий на заглушках** — весь путь в Telegram на
  `ENGINE=mock`, E2E-тест, `request_id`/retry/watchdog, матрица ошибок.
- [ ] **Phase 2: Живой Higgsfield** — контракт, probe, один реальный заказ.
- [ ] **Phase 3: Нормализация и доставка** — 720p/H.264/faststart, `file_id`,
  429, лимиты Telegram.
- [ ] **Phase 4: Лимиты и админка** — гейт кредитов, дневной лимит, `/admin*`,
  алерты, `/health`, очистка.
- [ ] **Phase 5: ЮKassa** — реальный платёж, идемпотентность, чеки.
- [ ] **Phase 6: Тесты, CI и документация** — «миграция == модели», CI,
  покрытие, приведение `docs/architecture.md` к коду.

## Phase Details

### Phase 1: Сквозной сценарий на заглушках
**Goal**: пользователь проходит весь путь в Telegram на `ENGINE=mock` и
`PAYMENT_PROVIDER=stub`; движок готов к живому подключению: `request_id`
переживает рестарт, повторы и сторож работают, ошибки доведены до ledger.
**Mode**: mvp
**Depends on**: Nothing (first phase)
**Requirements**: ENTRY-01, ENTRY-02, ENTRY-03, ENTRY-04, ENTRY-05, ENTRY-06, ENTRY-07, ENTRY-08, ENTRY-09, TMPL-01, TMPL-02, TMPL-03, TMPL-04, GEN-01, GEN-02, GEN-03, GEN-04, GEN-05, GEN-06, GEN-07, GEN-08, GEN-09, GEN-10, GEN-11, BILL-01, BILL-02, BILL-03, BILL-04, BILL-05, BILL-06, BILL-08, BILL-09, BILL-10, PRIV-01, PRIV-02, PRIV-03, PRIV-05, PRIV-06, QA-01, QA-03, QA-06
**Success Criteria** (what must be TRUE):
  1. Пользователь в Telegram проходит `/start → согласие → stub-оплата → фото
     → mock-видео → delivered`; фото удалено, ledger сходится.
  2. E2E-тест через aiogram test-client проходит в Docker на `ENGINE=mock`,
     `PAYMENT_PROVIDER=stub`.
  3. `request_id`/resume, retry 2/5/15, timeout, watchdog и ровно один refund
     покрыты тестами с фейковым движком.
  4. Матрица ошибок работает: `rejected` → refund, `no_credits` → refund +
     пауза продаж, `failed`/`timeout` → refund; пользователь видит текст без
     кодов.
  5. `.\tasks.cmd test` зелёный, ruff чистый, PII в логах нет.
**Plans**: 4 plans

Plans:
- [x] 01-01: E2E на заглушках в Telegram и aiogram test-client
- [x] 01-02: `request_id`, resume, retry и watchdog
- [x] 01-03: матрица ошибок, ledger и удаление фото
- [x] 01-04: проверка, docs, коммит

### Phase 2: Живой Higgsfield
**Goal**: контракт Higgsfield подтверждён живыми запросами; один реальный
заказ доходит до `sendVideo`, `request_id` переживает рестарт.
**Mode**: mvp
**Depends on**: Phase 1
**Requirements**: TMPL-06, GEN-12
**Success Criteria** (what must be TRUE):
  1. Live-probe подтверждает auth, upload, submit, `status_url`, имена
     статусов, `video.url` и форму ошибок.
  2. Один реальный заказ доставлен в Telegram, фото удалено, ledger сходится.
  3. Повторный submit не создаётся; после рестарта polling продолжается по
     `request_id`.
  4. `docs/higgsfield-contract.md` не содержит неподтверждённых полей в
     используемом пути.
**Plans**: 3 plans

Plans:
- [ ] 02-01: live-probe и фиксация контракта
- [ ] 02-02: правки движка по фактическому контракту
- [ ] 02-03: живой E2E-заказ и проверка БД

### Phase 3: Нормализация и доставка
**Goal**: результат приводится к параметрам Telegram и доставляется
идемпотентно, с `file_id` и обработкой лимитов.
**Mode**: mvp
**Depends on**: Phase 2
**Requirements**: TMPL-05, DELIV-01, DELIV-02, DELIV-03, DELIV-04, DELIV-05, DELIV-06, DELIV-07, PRIV-08
**Success Criteria** (what must be TRUE):
  1. Видео нормализуется в 720p/H.264/AAC/faststart и отправляется как видео.
  2. Файл больше лимита нормализуется, затем отправляется документом.
  3. 429 обрабатывается с `retry_after`, заказ не падает.
  4. `file_id` сохранён; повторная доставка не перегенерирует видео.
  5. Локальная копия удалена после успешной отправки.
**Plans**: 3 plans

Plans:
- [ ] 03-01: ffmpeg-нормализация и проверка размера
- [ ] 03-02: `file_id`, 429 и идемпотентная доставка
- [ ] 03-03: проверка на реальном видео

### Phase 4: Лимиты и админка
**Goal**: сервис защищён от слива кредитов и управляется без SQL.
**Mode**: mvp
**Depends on**: Phase 3
**Requirements**: PRIV-04, PRIV-07, OPS-01, OPS-02, OPS-03, OPS-04, OPS-05, OPS-06, OPS-07, OPS-08, OPS-09
**Success Criteria** (what must be TRUE):
  1. Дневной лимит и гейт кредитов не создают заказ при исчерпании.
  2. `/admin stats|balance|sales|ban|order` работают только для админов.
  3. Алерты `low_credits`, `job_stale`, `no_credits` и рост ошибок приходят.
  4. `/health` отдаёт 200/503 по состоянию БД.
  5. `STORAGE_DIR` чистится при старте; удаление по запросу работает.
**Plans**: 4 plans

Plans:
- [ ] 04-01: гейт кредитов и дневной лимит
- [ ] 04-02: админ-команды и аудит
- [ ] 04-03: алерты и `/health`
- [ ] 04-04: очистка хранилища и удаление данных

### Phase 5: ЮKassa
**Goal**: реальная оплата заменяет stub без изменения хендлеров.
**Mode**: mvp
**Depends on**: Phase 4
**Requirements**: BILL-07, PAY-01, PAY-02, PAY-03, PAY-04, PAY-05, PAY-06, PAY-07
**Success Criteria** (what must be TRUE):
  1. `PAYMENT_PROVIDER=yookassa` создаёт счёт и подтверждает оплату.
  2. Повторное уведомление с тем же `payment_id` не меняет баланс.
  3. На успехе создаются `topup` и `order_paid`, заказ переходит в `paid`.
  4. Stub не используется в проде.
  5. Чеки/фискализация самозанятого соответствуют требованиям ЮKassa.
**Plans**: 3 plans

Plans:
- [ ] 05-01: провайдер, счёт и конфигурация
- [ ] 05-02: подтверждение, ledger и идемпотентность
- [ ] 05-03: чеки, секреты и проверка

### Phase 6: Тесты, CI и документация
**Goal**: регресс ловится автоматически, схема БД и документация не расходятся
с кодом.
**Mode**: mvp
**Depends on**: Phase 5
**Requirements**: QA-02, QA-04, QA-05, QA-07
**Success Criteria** (what must be TRUE):
  1. Тест «миграция == модели» проходит на пустой БД.
  2. CI на каждый пуш гоняет ruff, pytest и покрытие.
  3. Порог покрытия не ниже 62% и не падает.
  4. `docs/architecture.md` соответствует `VideoEngine`, статусам job и
     отсутствию FastAPI.
**Plans**: 3 plans

Plans:
- [ ] 06-01: «миграция == модели» и тесты пайплайна
- [ ] 06-02: CI и порог покрытия
- [ ] 06-03: docs alignment

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Сквозной сценарий на заглушках | 4/4 | Complete | 2026-11-08 |
| 2. Живой Higgsfield | 0/3 | Not started | - |
| 3. Нормализация и доставка | 0/3 | Not started | - |
| 4. Лимиты и админка | 0/4 | Not started | - |
| 5. ЮKassa | 0/3 | Not started | - |
| 6. Тесты, CI и документация | 0/3 | Not started | - |

## Backlog / v2

- [ ] **«Ещё раз»: каталог заново, затем оплата** — сейчас кнопка сразу
  создаёт заказ и проводит stub-оплату; нужно показать каталог/шаблон,
  превью и цену, и только потом создавать заказ и оплачивать. См.
  [`.planning/todos/pending/2026-11-08-again-catalog.md`](.planning/todos/pending/2026-11-08-again-catalog.md)
  и `ENTRY-V2-01`. Phase 2 не начинать до отдельного решения.
