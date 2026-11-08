# Face Changer

## What This Is

Telegram-бот для рынка РФ: пользователь присылает одно фото, бот подставляет
лицо в заранее подготовленный видео-шаблон через Higgsfield (модель Genjutsu)
и возвращает готовое видео. Оператор — самозанятый, оплата — ЮKassa; в MVP
работает заглушка оплаты.

## Core Value

Пользователь за одно сообщение с фото получает правдоподобное видео со своим
лицом и платит за результат, а не за настройку сервисов. Если всё остальное
сломается, должен работать путь «фото → оплата → видео → доставка».

## Business Context

- **Customer**: пользователи Telegram в РФ, 18+.
- **Revenue model**: разовая оплата заказа; цена и стоимость в кредитах
  фиксируются в шаблоне (по умолчанию 299 ₽ и 1 кредит).
- **Success metric**: доля оплаченных заказов, доведённых до видео; маржа =
  цена − стоимость кредитов Higgsfield.
- **Strategy notes**: MVP, один шаблон, ручной контроль первых заказов;
  сначала проверка на заглушках, затем живой Higgsfield.

## Requirements

### Validated

- ✓ Сквозной путь `/start → согласие → stub-оплата → фото → mock-движок →
  sendVideo` — проверен в Telegram.
- ✓ Домен: стейт-машина заказа, ledger, pricing, moderation, result — 98–100%
  тестов.
- ✓ БД: `users`, `templates`, `orders`, `jobs`, `ledger`, `events`,
  `service_flags`; миграции `0001_initial`, `0002_service_flags`.
- ✓ Очередь на PostgreSQL `FOR UPDATE SKIP LOCKED`; два процесса bot/worker.
- ✓ Higgsfield-движок: upload → submit → poll, 3 повтора, типизированные
  ошибки; 13 тестов на `httpx.MockTransport` (контракт не подтверждён живым
  запросом).
- ✓ Docker compose, тесты в контейнере с `postgres-test` и схемой на
  xdist-воркер; 206 тестов, покрытие 62%, ruff чист.
- ✓ Карта кодовой базы `.planning/codebase/` (штамп `8cdc2ab`).

### Active

- [ ] **Phase 1**: сквозной сценарий на заглушках после текущих изменений +
  E2E-тест + `request_id`/retry/watchdog/матрица ошибок.
- [ ] **Phase 2**: живой контракт Higgsfield и один реальный заказ.
- [ ] **Phase 3**: нормализация результата, `file_id`, 429, доставка.
- [ ] **Phase 4**: дневной лимит, гейт кредитов, админка, алерты, `/health`,
  очистка и удаление данных.
- [ ] **Phase 5**: ЮKassa.
- [ ] **Phase 6**: CI, «миграция == модели», покрытие, docs alignment.

### Out of Scope

- **Бесплатный реролл в v1** — решение продукта: «Ещё раз» создаёт новый
  оплаченный заказ; вернуться после данных. Перенесено в v2.
- **Выбор шаблона пользователем** — один `default`; каталог как UI позже.
- **Telegram WebApp, история заказов, личный кабинет** — не нужны для проверки
  гипотезы.
- **Пользовательские промпты** — промпт только из шаблона.
- **Подписки и рекуррентные платежи** — вне MVP.
- **S3/CDN, Redis, Celery, внешняя аналитика** — локальный диск и PostgreSQL.
- **Мультиязычность, реферальная программа** — вне MVP.
- **Детекция лиц и модерация «одно лицо»** — снято с объёма решением продукта.
- **Автоматические денежные возвраты** — только кредиты; деньги вручную.

## Context

- Brownfield: код и документация уже есть. `.planning/codebase/` — срез на
  `8cdc2ab`, HEAD `38518a3`; последний коммит добавил `outcomes.py`,
  `sales.py`, `no_credits`/`rejected`, общий том медиа.
- Документация расходится с кодом: `docs/architecture.md` описывает
  `VideoEngine.ensure_asset/submit/poll/cancel`, а порт — один `generate`;
  статусы job в документе `submitted/polling`, в коде `new/running/done/failed`.
- Контракт Higgsfield не подтверждён: 8 предположений в
  `docs/higgsfield-contract.md`.
- Ключей HF и файлов `templates/default/source.mp4`, `prompt.txt` пока нет.
  Сначала прогоняем весь сценарий на `ENGINE=mock`, `PAYMENT_PROVIDER=stub`.
- Известные баги: `paid` без фото блокирует пользователя; остановка воркера
  оставляет `running`; фото остаётся при провале постановки в очередь; гонка
  двух фото; возможен возврат после уже отправленного видео.
- `.\tasks.cmd test` починен (UTF-8 BOM в `tasks.ps1`); до этого падал парсер
  Windows PowerShell 5.1.
- Исторические требования OpenSpec сохранены в `docs/archive/openspec/`.

## Constraints

- **Tech stack**: Python 3.12, aiogram 3, PostgreSQL 16, SQLAlchemy 2 async +
  Alembic, pydantic-settings, httpx, Pillow, ffmpeg; FastAPI не используется
  (решение по транспорту ЮKassa — отдельно).
- **Architecture**: два процесса bot/worker, обмен только через таблицы;
  Docker compose; функциональное ядро / императивная оболочка.
- **Domain purity**: в `app/domain/` нельзя `aiogram`, `sqlalchemy`, `httpx`,
  `os`, `time`, `random`, `uuid`; функция ≤ 25 строк, ≤ 3 позиционных
  аргумента, модуль ≤ 300 строк.
- **Money**: только целые копейки; кредиты — целые; никаких float.
- **Time**: UTC, `timestamptz`; локальное время только в текстах.
- **Statuses**: только через `order_service.transition`; прямых записей
  статуса нет.
- **Privacy**: фото удаляется при терминальном статусе; PII не логируется;
  секреты только в `.env`.
- **Market**: РФ, самозанятый, 18+, ЮKassa, чеки/фискализация по требованиям.
- **Engine**: Higgsfield Genjutsu — единственный живой движок; `mock` для
  разработки.
- **Tests**: Docker, xdist, схема на воркера; фиксированные пути запрещены.
- **Git**: осмысленные коммиты; субагенты не коммитят; секреты не коммитятся.

## Key Decisions

| Decision | Rationale | Outcome |
|---|---|---|
| Очередь на PostgreSQL, без брокера | один компонент, транзакционность, отладка SQL | ✓ Good |
| Два процесса bot/worker | рестарт бота не убивает генерации | ✓ Good |
| Статусы только через домен | деньги и возвраты в одном месте | ✓ Good |
| Polling, не webhook | не нужен публичный HTTPS на этапе проверки | ✓ Good |
| Заглушка оплаты как провайдер | проверяет весь путь до ЮKassa | ✓ Good |
| Локальное хранилище | фото живёт минуты, S3 не нужен | — Pending |
| Шаблон как данные, один default | контент меняется без релиза | ✓ Good |
| Бесплатный реролл не входит в v1 | проще MVP; «Ещё раз» = новый заказ | — Pending |
| `no_credits` = `failed` + код, пауза продаж 60 мин | не расширять стейт-машину; автопауза | — Pending |
| Job-статусы `new/running/done/failed`, `request_id` в БД | честно отражает код; resume по `request_id` | — Pending |
| Mock-first до живых ключей | проверить UX и деньги без расходов | — Pending |
| Транспорт ЮKassa: webhook или Telegram Payments | зависит от требований ЮKassa и наличия HTTPS | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via GSD transition):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone**:
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-11-08 after GSD initialization*
