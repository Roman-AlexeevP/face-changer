# Phase 1: Сквозной сценарий на заглушках - Context

**Gathered:** 2026-11-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Фаза 1 доводит до зелёного и проверяемого сквозной путь в Telegram на
`ENGINE=mock` и `PAYMENT_PROVIDER=stub`: `/start → согласие → оплата → фото →
видео → delivered`. Параллельно движок готовится к живому подключению:
`request_id` переживает рестарт, повторы и сторож работают, ошибки движка
доведены до заказа и ledger.

Вне фазы: живой Higgsfield (фаза 2), нормализация и `file_id` (фаза 3),
лимиты/админка (фаза 4), ЮKassa (фаза 5), CI (фаза 6). Бесплатный реролл —
v2, в v1 его нет.

</domain>

<decisions>
## Implementation Decisions

### E2E и проверка
- **D-01:** Сквозной тест идёт через настоящий `Dispatcher` и `feed_update`, а
  не через прямой вызов хендлеров. Telegram заменяется фейковой сессией
  aiogram, которая записывает `send_message`/`send_video` и отдаёт байты фото.
- **D-02:** Тест использует настоящую PostgreSQL-фикстуру `session` и
  `async_sessionmaker` поверх той же транзакции; коммиты приложения
  превращаются в savepoint и откатываются.
- **D-03:** `MockVideoEngine` и `LocalStorage` работают в `tmp_path`; ffmpeg
  доступен в тестовом образе. Никаких фиксированных путей.
- **D-04:** Троттлинг в тесте не отключается: время `monotonic` подменяется
  монотонно растущим, чтобы апдейты не резались.

### request_id и повторы
- **D-05:** `JobSpec` получает `request_id`; `VideoEngine.generate` получает
  keyword-only hook `on_submit`, который движок зовёт сразу после submit.
  Pipeline пишет `jobs.request_id` короткой транзакцией. При наличии
  `request_id` движок продолжает polling, а не делает новый submit.
- **D-06:** Статусы job остаются `new/running/done/failed`; `submitted` и
  `polling` — внутренние состояния движка, в БД не пишутся. Это фиксируется в
  `docs/architecture.md`.
- **D-07:** Политика повторов — чистая функция: не более 3 попыток, backoff
  2/5/15 с, повторяются только `network`, `engine_5xx`, `engine_failed`.
  Каждая попытка увеличивает `attempt`, меняет `idempotency_key` на
  `<order_id>:<attempt>` и ставит `next_attempt_at`. Для повтора заказ
  переходит `running → queued`.
- **D-08:** Сторож: `running` старше `JOB_STALE_MINUTES` возвращается в `new`
  с инкрементом `attempt`; заказ — `running → queued`. Таймаут генерации —
  `JOB_TIMEOUT_MIN`, код `timeout`, без повтора.

### Ошибки и деньги
- **D-09:** `nsfw` → `rejected` + refund, без повтора. HTTP 402 → `failed` с
  кодом `no_credits`, refund, пауза продаж на 60 минут, алерт админу.
  Технические ошибки → `failed` + refund после исчерпания повторов.
- **D-10:** Коды нормализуются в `timeout`, `moderated`, `no_credits`,
  `engine_5xx`, `network`, `bad_input`, `unknown`; `engine_auth`,
  `engine_bad_config`, `rate_limited` — внутренние. Наружу только текст.
- **D-11:** Ledger не меняет модель: `topup` + `order_paid` при оплате,
  `refund` ровно один раз для `failed`/`rejected`. Прямых апдейтов баланса нет.
- **D-12:** Один активный заказ обеспечивается частичным уникальным индексом
  на `orders(user_id)` для `paid/queued/running`; гонка двух фото обрабатывается
  как «фото уже принято», без `IntegrityError` наружу.
- **D-13:** Бесплатного реролла нет. «Ещё раз» — новый оплаченный заказ и новое
  фото; поведение фиксируется тестом, а не новым кодом.

### Границы кода
- **D-14:** Не добавлять новых зависимостей. Фейковая сессия — на
  `aiogram.client.session.base.BaseSession`; тест — на pytest.
- **D-15:** Новые функции соблюдают лимиты: ≤ 25 строк, ≤ 3 позиционных
  аргумента, модуль ≤ 300 строк; в `app/domain/` без инфраструктурных импортов.
- **D-16:** Коммиты делает только оркестратор после проверки; субагенты не
  коммитят. Секреты не печатаются и не коммитятся.

### Claude's Discretion
- Точная форма фейковой сессии и вспомогательных фабрик сообщений.
- Разбиение теста на helper-функции и выбор имён.
- Нужно ли выносить `request_id` hook в отдельный протокол или оставить
  keyword-only параметром `generate`.
- Формат `SUMMARY.md` и порядок проверок.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Проект и требования
- `.planning/PROJECT.md` — контекст, границы, ограничения.
- `.planning/REQUIREMENTS.md` — 75 требований v1, матрица ошибок, ledger,
  приватность.
- `.planning/ROADMAP.md` — фаза 1, критерии, трассировка.
- `.planning/STATE.md` — текущая позиция и блокеры.
- `AGENTS.md` — стиль, лимиты, запреты.

### Архитектура и контракты
- `docs/architecture.md` — слои, потоки, стейт-машина (расходится с кодом,
  исправлять по факту).
- `docs/higgsfield-contract.md` — предположения движка; в фазе 1 не трогаем
  живой контракт.
- `.planning/codebase/ARCHITECTURE.md` — фактическая карта на `8cdc2ab`.
- `.planning/codebase/TESTING.md` — как устроены тесты и фикстуры.
- `.planning/codebase/CONVENTIONS.md` — функциональный стиль и лимиты.

### Код
- `app/bot/handlers/start.py`, `checkout.py`, `upload.py` — путь пользователя.
- `app/bot/photo.py` — скачивание фото.
- `app/worker/pipeline.py` — выдача, fail/reject, refund, cleanup.
- `app/worker/loop.py` — claim и слоты.
- `app/engine base.py`, `app/engines/mock.py` — порт и заглушка.
- `app/db/repo.py`, `app/db/models.py` — очередь, статусы, ledger.
- `app/domain/order_service.py`, `ledger.py`, `moderation.py` — чистое ядро.
- `tests/conftest.py` — схема на воркера и транзакция с откатом.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `build_dispatcher(services)` — регистрирует реальные роутеры и middleware.
- `BotServices` / `WorkerServices` — готовые frozen-контейнеры зависимостей.
- `StubPaymentProvider` — мгновенная оплата.
- `MockVideoEngine` — локальный mp4 через ffmpeg.
- `LocalStorage` — файлы в `STORAGE_DIR`.
- Фикстура `session` — транзакция с откатом; `db_schema` — схема на воркера.

### Established Patterns
- Ошибки домена — `Result`; оболочка разворачивает `match`/`isinstance`.
- Время — параметр `now`; в тестах фиксированные `datetime` с UTC.
- Порты — `Protocol`; фейки в тестах.
- Тесты — функции, без классов; `pytest.mark.integration` для БД.
- Никаких фиксированных путей: только `tmp_path`.

### Integration Points
- `Dispatcher.feed_update` → handlers → `repo` → PostgreSQL.
- `handle_photo` → `download_photo` → `moderation.validate_photo` →
  `LocalStorage.save_photo` → `repo.create_job`.
- `process_job` → `engine.generate` → `bot.send_video` → `mark_delivered` →
  `cleanup`.

</code_context>

<specifics>
## Specific Ideas

- E2E должен проверять не только «видео отправлено», но и:
  - `orders.status = delivered`;
  - `jobs.status = done`;
  - ledger: `topup` + `order_paid`, без `refund`, сумма 0;
  - фото удалено с диска;
  - `send_video` вызван ровно один раз;
  - событие `order_delivered` есть в `events`.
- Фейковая сессия должна отдавать `Message` на `SendMessage`/`SendVideo` и
  `True` на `AnswerCallbackQuery`.
- Для фото использовать настоящий JPEG, сгенерированный Pillow.

</specifics>

<deferred>
## Deferred Ideas

- Бесплатный реролл — v2, после данных по качеству и экономике.
- Живой Higgsfield, нормализация, `file_id`, админка, ЮKassa, CI — следующие
  фазы.

</deferred>

---

*Phase: 1-Сквозной сценарий на заглушках*
*Context gathered: 2026-11-08*
