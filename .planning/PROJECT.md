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

### Validated baseline

- ✓ Сквозной путь `/start → согласие → stub-оплата → фото → mock-движок →
  sendVideo` — проверен в Telegram.
- ✓ Mock/stub baseline: `request_id`/resume, retry 2/5/15, watchdog, матрица
  ошибок, ledger и удаление фото; 248 тестов, покрытие 81% в Docker.
- ✓ Домен, PostgreSQL queue через `FOR UPDATE SKIP LOCKED`, два процесса
  bot/worker, типизированные порты и миграции готовы как база интеграции.
- ✓ Higgsfield adapter и stub payment provider существуют, но live-контракты
  ещё не подтверждены.

### Active

- [ ] **Phase 2**: два внешних гейта — live-probe Higgsfield и минимально
  доступная интеграция оплаты. Сначала доступ и выбор провайдера, затем
  адаптеры и один вертикальный тестовый сценарий.
- [ ] Следующие фазы намеренно не определены до результатов обоих гейтов.

Детали активной работы находятся в `.planning/ROADMAP.md` и
`.planning/phases/FC-02-vneshnie-integratsii/CONTEXT.md`.

### Out of Scope

- **Бесплатный реролл в v1** — решение продукта: «Ещё раз» создаёт новый
  оплаченный заказ; вернуться после данных. Перенесено в v2.
- **Выбор шаблона пользователем** — один `default`; каталог как UI позже.
- **Показ каталога при «Ещё раз»** — в v1 кнопка сразу создаёт заказ и
  проводит оплату; показ каталога перед новым заказом вынесен в
  `ENTRY-V2-01`.
- **Telegram WebApp, история заказов, личный кабинет** — не нужны для проверки
  гипотезы.
- **Пользовательские промпты** — промпт только из шаблона.
- **Подписки и рекуррентные платежи** — вне MVP.
- **S3/CDN, Redis, Celery, внешняя аналитика** — локальный диск и PostgreSQL.
- **Мультиязычность, реферальная программа** — вне MVP.
- **Детекция лиц и модерация «одно лицо»** — снято с объёма решением продукта.
- **Автоматические денежные возвраты** — только кредиты; деньги вручную.

## Context

- Brownfield: код и документация уже есть; mock/stub baseline сохранён в
  `.planning/archive/2026-11-09-pre-reset/`.
- Карта `.planning/codebase/` имеет старый штамп и используется только как
  справочный материал; источником истины для текущей работы являются код,
  `AGENTS.md` и новые planning-документы.
- Контракт Higgsfield не подтверждён живым запросом: предположения перечислены
  в `docs/higgsfield-contract.md`.
- Ключей HF и файлов `templates/default/source.mp4`, `prompt.txt` в репозитории
  нет. Для обычной разработки остаются `ENGINE=mock` и
  `PAYMENT_PROVIDER=stub`.
- Платёжный маршрут не фиксируем заранее: сначала проверяем доступность
  ЮKassa, Telegram Payments или другого реально доступного варианта, затем
  выбираем минимальный безопасный путь.
- UX-долг «Ещё раз» и прочие будущие продуктовые улучшения отложены до
  подтверждения двух внешних гейтов.
- Исторические требования OpenSpec сохранены в `docs/archive/openspec/`, а
  предыдущие GSD-планы — в `.planning/archive/2026-11-09-pre-reset/`.

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
- **Market**: РФ, самозанятый, 18+; платёжный маршрут и требования к чекам
  подтверждаются на текущем внешнем гейте.
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
| Polling для bot/worker baseline | не нужен публичный HTTPS до внешнего интеграционного гейта | ✓ Baseline |
| Заглушка оплаты как провайдер | проверяет путь без внешнего платёжного API | ✓ Baseline |
| Локальное хранилище | фото живёт минуты, S3 не нужен | — Pending |
| Шаблон как данные, один default | контент меняется без релиза | ✓ Good |
| Бесплатный реролл не входит в v1 | проще MVP; «Ещё раз» = новый заказ | — Pending |
| «Ещё раз» должен вести в каталог, не в автооплату | сейчас кнопка сразу создаёт заказ и проводит stub-оплату; UX-долг | — Pending |
| `no_credits` = `failed` + код, пауза продаж 60 мин | не расширять стейт-машину; автопауза | — Pending |
| Job-статусы `new/running/done/failed`, `request_id` в БД | честно отражает код; resume по `request_id` | — Pending |
| Mock-first до живых ключей | проверить UX и деньги без расходов | ✓ Baseline |
| Два внешних гейта до нового roadmap | не планировать downstream-фазы на
  неподтверждённых контрактах | — Active |
| Платёжный маршрут выбирается по доступности | сначала сравнить реально
  доступные API, sandbox и требования РФ | — Active |

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
*Last updated: 2026-11-09 after planning reset*
