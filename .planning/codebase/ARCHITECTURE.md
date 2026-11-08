---
last_mapped_commit: 8cdc2abb49b272f3240a75e55c06f62b162fc586
last_mapped_at: 2026-11-08
---
<!-- refreshed: 2026-11-08 -->
# Архитектура

**Дата анализа:** 2026-11-08

## Обзор системы

```text
┌───────────────────────────────────────────────────────────────────────────────────┐
│ Telegram Bot API — long polling; вебхука нет                                      │
│ бот: sendMessage / getFile      worker: sendVideo / sendMessage                   │
└───────────────────────────────────────────────────────────────────────────────────┘
                  │                                           │
                  ▼                                           ▼
┌────────────────────────────────────┐   ┌──────────────────────────────────────────┐
│ Процесс `bot`                      │   │ Процесс `worker`                         │
│ `app/main_bot.py`                  │   │ `app/main_worker.py`                     │      ┌──────────────────────────────────────────┐
│ Dispatcher + start_polling         │   │ run_pool: N слотов run_slot              │      │ Higgsfield API (Genjutsu)                │
│ middleware: dedupe, throttle       │   │ pipeline.process_job                     │ ──▶  │ upload -> submit -> poll                 │
│ handlers: start/checkout/upload    │   │ worker_concurrency (по умолчанию 2)      │      │ `app/engines/higgsfield.py`              │
│ PaymentProvider: stub              │   │ VideoEngine: mock | higgsfield           │      └──────────────────────────────────────────┘
│ Storage: local                     │   │ Storage: local                           │
└─────────────────┬──────────────────┘   └────────────────────┬─────────────────────┘
                  │                                           │
                  ▼                                           ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│ PostgreSQL 16 — единственная точка обмена между процессами                        │
│ users · templates · orders · jobs · ledger · events                               │
│ схема и индексы — `app/db/models.py`                                              │
└───────────────────────────────────────────────────────────────────────────────────┘
```

Два процесса, одна кодовая база, одна БД, никаких брокеров. Бот и воркер
не вызывают друг друга: всё общение идёт через строки таблиц `orders` и `jobs`.

## Ответственность компонентов

| Компонент | Ответственность | Файл |
|---|---|---|
| Точка сборки бота | роутеры, middleware, сервисы, polling, сид шаблона | `app/main_bot.py` |
| Точка сборки воркера | движок, хранилище, сигналы остановки, пул слотов | `app/main_worker.py` |
| Дедупликация апдейтов | отбрасывание повторных `update_id` | `app/bot/middlewares/dedupe.py` |
| Троттлинг | минимальный интервал между апдейтами одного `tg_id` | `app/bot/middlewares/throttle.py` |
| Вход и согласие | `/start`, экран правил, запись `consent_version`/`consent_at` | `app/bot/handlers/start.py` |
| Оформление заказа | создание заказа, инвойс, `pay`, записи `ledger` | `app/bot/handlers/checkout.py` |
| Приём фото | валидация, сохранение, `queued` + `job(new)` | `app/bot/handlers/upload.py` |
| Загрузка фото из Telegram | выбор вложения, скачивание в память | `app/bot/photo.py` |
| Тексты | все пользовательские строки и `failure_text` | `app/bot/texts.py` |
| Клавиатуры | `callback_data` и инлайн-кнопки | `app/bot/keyboards.py` |
| Стейт-машина заказа | таблица `TRANSITIONS`, чистые переходы | `app/domain/order_service.py` |
| Ledger | записи `topup`/`order_paid`/`refund`, баланс | `app/domain/ledger.py` |
| Цена заказа | снимок тарифа в заказе | `app/domain/pricing.py` |
| Приём фото (ядро) | лимиты, формат, перекодирование без EXIF | `app/domain/moderation.py` |
| Результат как значение | `Ok`/`Err`/`Result` | `app/domain/result.py` |
| Контракт движка | `EngineStatus`, `JobSpec`, `EngineResult`, `VideoEngine` | `app/engines/base.py` |
| Сборка движка | выбор `mock`/`higgsfield` по `ENGINE` | `app/engines/factory.py` |
| Заглушка движка | локальный mp4 через ffmpeg/lavfi | `app/engines/mock.py` |
| Реальный движок | upload → submit → poll до терминального статуса | `app/engines/higgsfield.py` |
| HTTP-транспорт | авторизация, таймауты, повторы, маппинг кодов | `app/engines/transport.py` |
| Контракт оплаты | `PaymentProvider`, `Invoice`, `PaymentEvent` | `app/payments/base.py` |
| Заглушка оплаты | мгновенный успех, детерминированный `payment_id` | `app/payments/stub.py` |
| Сборка оплаты | `stub` либо `ConfigError` для `yookassa` | `app/payments/factory.py` |
| Контракт хранилища | `Storage` (фото и временные файлы) | `app/storage/base.py` |
| Локальное хранилище | файлы в `STORAGE_DIR`, без публичных ссылок | `app/storage/local.py` |
| Пул воркера | N слотов, claim, пауза при простое | `app/worker/loop.py` |
| Пайплайн задания | генерация, выдача, компенсация | `app/worker/pipeline.py` |
| Зависимости воркера | `WorkerServices` | `app/worker/services.py` |
| Зависимости бота | `BotServices`, сборка боевых сервисов | `app/bot/services.py` |
| Доступ к данным | тонкие запросы и запись, без правил | `app/db/repo.py` |
| Схема БД | шесть таблиц, индексы, конвенция имён | `app/db/models.py` |
| Движок и фабрика сессий | `create_async_engine`, `async_sessionmaker` | `app/db/session.py` |
| Сид шаблона | дефолтный шаблон, если таблица пуста | `app/db/seed.py` |
| Миграции | `upgrade/downgrade` начальной схемы | `app/db/migrations/versions/0001_initial.py` |
| Настройки | типизированный env, `ConfigError` | `app/config.py` |
| Часы | единственное чтение текущего времени в оболочке | `app/clock.py` |
| Логи | JSON-строки в stdout, редакция PII | `app/obs/logs.py` |

## Обзор паттерна

**Общее:** функциональное ядро и императивная оболочка поверх одного
PostgreSQL-очереди. Ядро — чистые функции над `dataclass(frozen=True)`,
ошибки — значения `Ok`/`Err`. Оболочка — тонкие функции, которые читают,
зовут ядро, сохраняют и уведомляют.

**Ключевые характеристики:**

- Направление зависимостей одностороннее: `bot`/`worker` → `domain` + порты;
  `domain` не импортирует инфраструктуру и проверяется тестом
  `tests/test_architecture.py`.
- Никаких глобальных синглтонов: зависимости приходят аргументом
  (`BotServices`, `WorkerServices`) и собираются в `app/main_bot.py` /
  `app/main_worker.py`.
- Полиморфизм — только `Protocol` (`VideoEngine`, `PaymentProvider`,
  `Storage`), наследования нет; реализации выбираются фабрикой или прямо
  в точке сборки.
- Время — параметр: `WorkerServices.now` / `BotServices.now`
  (`Callable[[], datetime]`, по умолчанию `app/clock.py:utc_now`), движок
  получает `now`/`sleep` полями `HiggsfieldVideoEngine`.
- Состояние заказа меняется только через `order_service.transition`
  (`app/domain/order_service.py:93`); прямая запись `row.status` в
  `app/db/repo.py:160` происходит лишь после чистого перехода.
- Обмен между процессами — строки таблиц, а не вызовы; очередь на
  `FOR UPDATE SKIP LOCKED`.

## Слои

**Чистое ядро (`app/domain/`):**
- Назначение: бизнес-правила без I/O.
- Расположение: `app/domain/`
- Содержит: `OrderStatus`, `Order`, `TRANSITIONS`, `transition/pay/enqueue/
  start/deliver/fail/reject/mark_refunded/purge`, `LedgerEntry`, `Tariff`,
  `PreparedPhoto`, типизированные ошибки, `Result`.
- Зависит от: стандартной библиотеки, `Pillow` (только `moderation.py`),
  других модулей `app/domain/`.
- Используется: `app/bot/handlers/*`, `app/worker/pipeline.py`,
  `app/db/repo.py` (преобразование строк и `quote`).

**Порты (`app/engines/base.py`, `app/payments/base.py`, `app/storage/base.py`):**
- Назначение: контракты границ, за которыми начинается внешний мир.
- Содержит: `VideoEngine.generate`, `PaymentProvider.create_invoice/refund`,
  `Storage.photo_path/save_photo/delete_photo/delete_file`, а также типы
  заданий, результатов и ошибок.
- Зависит от: `app/domain/order_service.py` (только тип `Order`).
- Используется: фабриками и оболочкой; в тестах подменяется фейками.

**Адаптеры (`app/engines/{mock,higgsfield,transport}.py`,
`app/payments/stub.py`, `app/storage/local.py`):**
- Назначение: реализация портов.
- Содержит: HTTP-клиент Higgsfield, ffmpeg-рендер заглушки, файловые операции.
- Зависит от: портов, `httpx`, `asyncio`, файловой системы.
- Используется: точками сборки `app/engines/factory.py`,
  `app/payments/factory.py`, `app/bot/services.py`, `app/main_worker.py`.

**Оболочка Telegram (`app/bot/`):**
- Назначение: диалог, тексты, клавиатуры, порядок шагов воронки.
- Расположение: `app/bot/handlers/`, `app/bot/middlewares/`, `app/bot/photo.py`
- Содержит: хендлеры и их `build_router()`, middleware, загрузку вложения.
- Зависит от: `app/domain/`, `app/db/repo.py`, портов `Storage` и
  `PaymentProvider`.
- Используется: `app/main_bot.py:build_dispatcher`.

**Оболочка воркера (`app/worker/`):**
- Назначение: оркестрация одного заказа и пула слотов.
- Содержит: `run_pool`, `run_slot`, `claim_next`, `process_job` и шаги
  пайплайна.
- Зависит от: `app/domain/`, `app/db/repo.py`, портов `VideoEngine` и
  `Storage`, `aiogram.Bot` для отправки.
- Используется: `app/main_worker.py:run_worker`.

**Инфраструктура (`app/db/`, `app/obs/`, `app/config.py`, `app/clock.py`):**
- Назначение: БД, логи, настройки, время.
- Содержит: модели, репозиторий, сессии, миграции, сид, JSON-логи.
- Зависит от: `SQLAlchemy`, `alembic`, `pydantic-settings`.
- Используется: обеими точками сборки и обеими оболочками.

**Композиция (`app/main_bot.py`, `app/main_worker.py`):**
- Назначение: единственное место, где выбираются реализации и создаются
  долгоживущие объекты (`Bot`, `AsyncEngine`, движок, хранилище, провайдер).
- Содержит: `run_bot`, `run_worker`, `build_dispatcher`, `install_signal_handlers`.
- Зависит от: всех слоёв.
- Используется: `python -m app.main_bot` / `python -m app.main_worker`.

## Поток данных

### Вход: `/start` и согласие

1. `Dispatcher` принимает апдейт; срабатывают `DedupeMiddleware`
   (`app/bot/middlewares/dedupe.py:18`) и `ThrottleMiddleware`
   (`app/bot/middlewares/throttle.py:29`) — оба на уровне `update`.
2. `handle_start` (`app/bot/handlers/start.py:23`) находит или создаёт
   пользователя (`repo.get_or_create_user`, `app/db/repo.py:90`).
3. Если `consent_version is None` — экран правил с кнопкой
   (`app/bot/handlers/start.py:54`).
4. `handle_consent` (`app/bot/handlers/start.py:38`) пишет
   `consent_version`/`consent_at`, событие `consent_given` и показывает
   домашний экран `show_home` (`app/bot/handlers/start.py:59`).
5. `show_home` выбирает между «активный заказ» и экраном оплаты
   (`texts.checkout_text`), цена берётся из `templates.price_kopecks`.

### Оплата (заглушка)

1. Колбэк `checkout:start` ловит `handle_checkout`
   (`app/bot/handlers/checkout.py:36`).
2. Проверяется `SALES_ENABLED` (`app/bot/handlers/checkout.py:41`) —
   единственный реализованный предохранитель продаж.
3. `start_checkout` (`app/bot/handlers/checkout.py:48`) проверяет согласие,
   активный заказ (`repo.get_active_order`, `app/db/repo.py:169`) и берёт
   дефолтный шаблон (`repo.get_default_template`, `app/db/repo.py:110`).
4. `open_order` (`app/bot/handlers/checkout.py:66`) создаёт заказ:
   `repo.create_order` (`app/db/repo.py:129`) вызывает чистый `pricing.quote`
   и фиксирует цену в заказе.
5. `charge_order` (`app/bot/handlers/checkout.py:82`) зовёт
   `payments.create_invoice`, проверяет `ensure_paid`
   (`app/bot/handlers/checkout.py:104`), затем `order_service.pay`
   (`app/domain/order_service.py:100`) и `attach_payment`.
6. `write_ledger` (`app/bot/handlers/checkout.py:95`) добавляет две записи:
   `topup` и `order_paid` (`app/domain/ledger.py:63`, `:77`).
7. События `order_created`, `order_paid` пишутся в `events`; пользователю
   уходит `texts.PHOTO_REQUEST`.

### Приём фото и постановка в очередь

1. `handle_photo` (`app/bot/handlers/upload.py:32`) находит активный заказ и
   требует `order_service.is_awaiting_photo` (`app/domain/order_service.py:156`),
   то есть статус `paid`.
2. `download_photo` (`app/bot/photo.py:25`) берёт `photo[-1]` или
   `document` с `image/*`, проверяет `file_size` до скачивания и читает
   байты в `BytesIO`.
3. `moderation.validate_photo` (`app/domain/moderation.py:68`) проверяет
   лимит 20 МБ, формат `JPEG/PNG/WEBP`, сторону 4096 px и перекодирует в
   JPEG без EXIF. Детекции лиц нет.
4. `save_photo` (`app/bot/photo.py:37`) кладёт файл в
   `LocalStorage.photo_path` = `photo-<order_id>.jpg`
   (`app/storage/local.py:16`).
5. `queue_order` (`app/bot/handlers/upload.py:83`) — `order_service.enqueue`
   (`paid → queued`) и `repo.create_job` с
   `idempotency_key = f"{order_id}:1"` (`app/bot/handlers/upload.py:91`).
6. Одним `session.commit()` фиксируются заказ, задание, событие
   `photo_accepted`.

### Воркер: от claim до движка

1. `run_pool` (`app/worker/loop.py:15`) поднимает `WORKER_CONCURRENCY`
   корутин `run_slot`; каждая в цикле делает `claim_next`
   (`app/worker/loop.py:44`), при простое — `asyncio.sleep(1)`.
2. `repo.claim_job` (`app/db/repo.py:194`) выбирает `jobs.status='new'` с
   `next_attempt_at <= now`, `ORDER BY id`, `FOR UPDATE SKIP LOCKED LIMIT 1`
   и в той же транзакции ставит `status='running'`, `submitted_at=now`.
3. `process_job` (`app/worker/pipeline.py:41`) вызывает `start_order`
   (`app/worker/pipeline.py:57`): `order_service.start` (`queued → running`)
   под `with_for_update` и чтение шаблона.
4. `build_spec` (`app/worker/pipeline.py:74`) собирает `JobSpec`:
   `video_url = template.source_path`, `photo_url = storage.photo_path(...)`,
   `prompt`, `duration_sec`, `resolution`, `idempotency_key`.
5. `generate_video` (`app/worker/pipeline.py:87`) вызывает
   `engine.generate(spec)` — весь цикл движка скрыт за одним вызовом.
6. Внутри `HiggsfieldVideoEngine.generate` (`app/engines/higgsfield.py:63`):
   `ensure_video_url` (кэш в памяти процесса, `:72`) → `upload_media` для
   фото → `submit` (`:81`) → `poll` (`:97`) до `completed`/`failed`/`nsfw`,
   таймаута `HF_POLL_MAX_MIN` или четвёртого неизвестного статуса.
7. HTTP-часть: `HttpTransport.request` (`app/engines/transport.py:62`) —
   до 3 попыток, backoff `2/5/15` с джиттером, `Retry-After` приоритетнее,
   маппинг `401/403 → EngineAuthError`, `402 → EngineNoCredits`,
   `400/422 → EngineInputRejected`, `404 → EngineBadConfig`.

### Выдача видео и очистка

1. `is_deliverable` (`app/worker/pipeline.py:93`) требует
   `EngineStatus.DONE` и непустой `result_url`.
2. `deliver` (`app/worker/pipeline.py:97`) достаёт `chat_id` через
   `load_chat_id` (`app/worker/pipeline.py:212`).
3. `send_video` (`app/worker/pipeline.py:119`) отправляет `FSInputFile`,
   если путь существует локально, иначе — строку как URL; подпись
   `texts.VIDEO_CAPTION` и клавиатура «Ещё раз».
4. `mark_delivered` (`app/worker/pipeline.py:133`) — `order_service.deliver`
   (`running → delivered`), `jobs.status='done'`, событие `order_delivered`.
5. `cleanup` (`app/worker/pipeline.py:151`) удаляет фото заказа и локальный
   результат; ошибки `OSError` только логируются.

### Отказ и компенсация

1. Любое исключение `EngineError`/`PipelineError` или не-`DONE` результат
   уходит в `fail_job` (`app/worker/pipeline.py:162`); непойманное —
   `except Exception` с `logger.exception` и кодом `internal`.
2. `mark_failed` (`app/worker/pipeline.py:168`) переводит заказ в `failed`
   (`order_service.fail`), закрывает задание `jobs.status='failed'` с
   `error_code`, пишет событие `job_failed`.
3. `refund_credit` (`app/worker/pipeline.py:189`) читает ledger заказа,
   зовёт чистый `ledger.refund` (`app/domain/ledger.py:93`), добавляет
   запись `refund`, событие `refund_issued` и переводит заказ в `refunded`
   (`order_service.mark_refunded`).
4. `notify_failure` (`app/worker/pipeline.py:202`) отправляет
   `texts.failure_text(code)` из `MappingProxyType` в
   `app/bot/texts.py:48`; неизвестный код даёт `GENERIC_FAILURE`.

**Управление состоянием:**
- Единственный источник правды — строки `orders`, `jobs`, `ledger`, `events`
  в PostgreSQL; в памяти процессов состояния заказа нет.
- Доменное состояние — неизменяемые `Order`/`LedgerEntry`; изменение через
  `dataclasses.replace`, запись — `repo.save_order`
  (`app/db/repo.py:156`), который копирует поля в ORM-строку.
- Транзакция = один шаг воронки: решение и запись в одной сессии, затем
  `commit`; при `PaymentFailed` в `open_order` — `rollback`
  (`app/bot/handlers/checkout.py:75`).
- Блокировки: `with_for_update()` на заказе в воркере, `skip_locked` на
  заданиях.

## Ключевые абстракции

**`VideoEngine`:**
- Назначение: спрятать весь цикл генерации за одним вызовом.
- Расположение: `app/engines/base.py:84`
- Реализации: `MockVideoEngine` (`app/engines/mock.py:40`),
  `HiggsfieldVideoEngine` (`app/engines/higgsfield.py:54`).
- Паттерн: порт + `Protocol`; единственный метод
  `async generate(spec: JobSpec) -> EngineResult`; ошибки — исключения
  `EngineError` и подтипы с атрибутом `code`.
- Сборка: `build_video_engine` (`app/engines/factory.py:12`), только в
  процессе `worker`.

**`PaymentProvider`:**
- Назначение: создание счёта и подтверждение оплаты.
- Расположение: `app/payments/base.py:40`
- Реализации: `StubPaymentProvider` (`app/payments/stub.py:10`).
- Паттерн: порт с `name`, `create_invoice(order) -> Invoice`,
  `refund(payment_id)`. Мгновенный провайдер возвращает `PaymentEvent` прямо
  в `Invoice.event`; `yookassa` не реализован и падает `ConfigError`
  (`app/payments/factory.py:12`).

**`Storage`:**
- Назначение: временные файлы заказа.
- Расположение: `app/storage/base.py:7`
- Реализации: `LocalStorage` (`app/storage/local.py:11`).
- Паттерн: `photo_path` — детерминированный путь по `order_id`, чтобы
  воркер нашёл фото без обращения к БД; запись/удаление — через
  `asyncio.to_thread`.

**`Result` / `Ok` / `Err`:**
- Назначение: ошибка как значение в ядре.
- Расположение: `app/domain/result.py`
- Паттерн: размеченное объединение с pattern matching
  (`match ... case Ok(...) / case Err(...)`), например
  `app/domain/moderation.py:79`, `app/worker/pipeline.py:64`.

**`Order` + `TRANSITIONS`:**
- Назначение: стейт-машина заказа.
- Расположение: `app/domain/order_service.py:26`, `:74`
- Паттерн: `MappingProxyType[OrderStatus, frozenset[OrderStatus]]`, проверка
  в `transition`, автоматическая простановка `paid_at`/`delivered_at` в
  `_stamp` (`app/domain/order_service.py:161`).

**`BotServices` / `WorkerServices`:**
- Назначение: явный DI-контейнер без фреймворка.
- Расположение: `app/bot/services.py:17`, `app/worker/services.py:16`
- Паттерн: `@dataclass(frozen=True)` с полями-зависимостями и
  `now: Callable[[], datetime] = utc_now`.

**Стейт-машина заказа (фактическая):**

```text
created ──pay──► paid ──enqueue──► queued ──start──► running ──deliver──► delivered ──purge──► purged
                   │                  │                │
                   ├──fail──► failed ─┴────────────────┘        failed ──mark_refunded──► refunded
                   └──reject──► rejected                          rejected ──mark_refunded──► refunded
```

Таблица переходов — `app/domain/order_service.py:74`. Активные статусы
(`paid/queued/running`) — `ACTIVE_STATUSES` (`app/domain/order_service.py:70`),
по ним работает гейт «один активный заказ».

Статусы, недостижимые в рантайме: `rejected` (в пайплайне вызывается
только `fail`) и `purged` (нет ни одного вызова `order_service.purge`).
Фактически рабочий путь: `created → paid → queued → running → delivered`
либо `→ failed → refunded`.

**Стейт-машина задания (фактическая):**
`new → running → done | failed` — `repo.JobStatus`
(`app/db/repo.py:20`). Выставляется в `claim_job`
(`app/db/repo.py:208`), `finish_job` (`app/db/repo.py:214`).

## Точки входа

**`app.main_bot`:**
- Расположение: `app/main_bot.py:43` (`main`), `:30` (`run_bot`).
- Запускается: `python -m app.main_bot`, сервис `bot` в
  `docker-compose.yml:32`.
- Ответственность: `load_settings` → `require_bot_token` →
  `configure_logging` → движок БД и фабрика сессий → `Bot` →
  `seed_default_template` (`app/db/seed.py:45`) → `build_dispatcher` →
  `start_polling`; в `finally` закрывает сессию бота и движок БД.

**`app.main_worker`:**
- Расположение: `app/main_worker.py:61` (`main`), `:41` (`run_worker`).
- Запускается: `python -m app.main_worker`, сервис `worker` в
  `docker-compose.yml:67`.
- Ответственность: настройки, токен бота, `require_engine_credentials`,
  `build_video_engine`, `LocalStorage`, `WorkerServices`, обработчики
  `SIGINT`/`SIGTERM`, `run_pool`.

**`build_dispatcher`:**
- Расположение: `app/main_bot.py:18`
- Триггер: старт бота и тесты (`tests/test_bot_wiring.py:29`).
- Ответственность: регистрация двух outer-middleware и трёх роутеров,
  передача `services` через `dispatcher["services"]`.

**`build_router` каждого хендлера:**
- Расположение: `app/bot/handlers/start.py:15`,
  `app/bot/handlers/checkout.py:18`, `app/bot/handlers/upload.py:58`.
- Триггер: `build_dispatcher`.
- Ответственность: создавать `Router` заново, без глобального состояния.

**`alembic` env:**
- Расположение: `app/db/migrations/env.py:57`
- Триггер: `alembic upgrade head` в контейнере `migrate`
  (`docker-compose.yml:36`).
- Ответственность: брать `DATABASE_URL` из `Settings`, а не из `alembic.ini`.

## Архитектурные ограничения

- **Модель исполнения:** один `asyncio`-цикл на процесс; конкурентность
  воркера — N корутин (`run_pool`), не потоки и не процессы. Блокирующий
  файловый ввод-вывод вынесен в `asyncio.to_thread`
  (`app/storage/local.py:21`, `:28`, `app/worker/pipeline.py:115`,
  `app/engines/higgsfield.py:137`); ffmpeg — `asyncio.create_subprocess_exec`
  (`app/engines/mock.py:111`).
- **Глобальное состояние:** модульных изменяемых синглтонов нет. Есть
  состояние в экземплярах: `OrderedDict` в `DedupeMiddleware`
  (`app/bot/middlewares/dedupe.py:16`), `dict` в `ThrottleMiddleware`
  (`app/bot/middlewares/throttle.py:27`), кэш URL видео
  `HiggsfieldVideoEngine.video_urls` (`app/engines/higgsfield.py:61`) —
  изменяемый `dict` внутри `frozen`-датакласса, живёт только в процессе.
- **Два экземпляра `Bot`:** бот в процессе `bot`
  (`app/main_bot.py:33`), отдельный бот в процессе `worker`
  (`app/main_worker.py:43`) — воркеру нужен только `send_video`/`send_message`.
- **Ключи движка:** `HF_KEY_ID`/`HF_KEY_SECRET` проверяются и используются
  только в `worker` (`app/config.py:106`, `app/engines/factory.py:19`);
  `bot` их не читает.
- **Циклические импорты:** не обнаружены. Направление `domain/ledger.py →
  domain/order_service.py` одностороннее; `worker/pipeline.py` импортирует
  `app.bot.texts`/`app.bot.keyboards`, но обратной зависимости нет.
- **Порядок императивной оболочки:** `parse → validate (ядро) →
  decide (ядро) → persist → notify`, реализован в
  `app/bot/handlers/upload.py:66` и `app/worker/pipeline.py:41`.
- **Лимиты кода:** модуль ≤ 300 строк — сейчас максимум
  `app/db/repo.py` (284), `app/engines/higgsfield.py` (230),
  `app/worker/pipeline.py` (218).

## Анти-паттерны

### Статусы задания сжаты до `new/running/done/failed`

**Что происходит:** `docs/architecture.md` §5 описывает
`new → submitted → polling → done`, но `repo.JobStatus`
(`app/db/repo.py:20`) знает только четыре статуса. `jobs.request_id` не
заполняется нигде, `submitted_at` фактически хранит время захвата
(`app/db/repo.py:209`), а промежуточные состояния submit/poll живут лишь в
памяти движка.
**Почему это плохо:** по таблице нельзя увидеть, на каком шаге застряло
задание; после падения процесса задание остаётся в `running` без
`request_id`, и восстановить опрос по нему невозможно.
**Как правильно:** либо привести код к документу (писать `request_id` и
промежуточные статусы из движка), либо привести документ к коду и явно
зафиксировать, что весь цикл движка непрозрачен для БД.

### `rejected` и `no_credits` не доезжают до заказа

**Что происходит:** `map_status` возвращает `EngineStatus.REJECTED` для
`nsfw` (`app/engines/higgsfield.py:191`), `EngineNoCredits` поднимается на
HTTP 402 (`app/engines/transport.py:122`), но `process_job` обрабатывает
любой не-`DONE` результат как `fail_job`
(`app/worker/pipeline.py:49`). `order_service.reject` вызывается только из
тестов, `EngineStatus.NO_CREDITS` не производится ни одной реализацией.
**Почему это плохо:** модерационный отказ и «кончились кредиты движка»
неотличимы от технической ошибки; документированный стоп продаж при
`no_credits` (§7, §8) не наступает.
**Как правильно:** в `process_job` разветвлять терминальный статус движка:
`REJECTED → order_service.reject`, `NO_CREDITS → reject/failed + остановка
продаж`; `NO_CREDITS` должен возвращаться реализацией, а не только
исключением транспорта.

### Политика повторов задания отсутствует

**Что происходит:** `docs/architecture.md` §2 и §7 ссылаются на
`worker/retry`, но такого модуля нет. Повторы есть только внутри
`HttpTransport` (`app/engines/transport.py:72`) — три попытки на один
HTTP-запрос. `jobs.attempt` всегда `1`, `idempotency_key` всегда
`"{order_id}:1"`, `next_attempt_at` никогда не сдвигается в будущее.
**Почему это плохо:** сетевой сбой, случившийся после исчерпания
HTTP-повторов, сразу ведёт к `failed` и возврату кредита; повторная
генерация невозможна, хотя `attempt` и `next_attempt_at` для неё уже есть в
схеме.
**Как правильно:** отдельная чистая функция политики (сколько попыток,
какой backoff, какие коды повторяемы) + `next_attempt_at` при
`finish_job(FAILED)`.

### Объявленные предохранители не подключены

**Что происходит:** `Settings` содержит `engine_credits_hint`,
`daily_generation_cap`, `job_timeout_min`, `job_stale_minutes`,
`storage_url_ttl_min`, `tg_admin_ids`, `tg_webhook_secret`
(`app/config.py:29-53`), но ни одно из этих значений не читается вне
`app/config.py` и тестов. Читается только `sales_enabled`
(`app/bot/handlers/checkout.py:41`).
**Почему это плохо:** гейт кредитов движка, дневной лимит, сторож
зависших заданий, таймаут задачи и админ-команды из §7–§8 фактически
отсутствуют, при этом конфигурация создаёт впечатление, что они есть.
**Как правильно:** либо реализовать гейты в точках решения (перед
`create_order`, в `run_pool`), либо убрать неиспользуемые настройки и
отразить это в документе.

### Воркер зависит от презентационного слоя бота

**Что происходит:** `app/worker/pipeline.py:13` импортирует
`app.bot.texts` и `app.bot.keyboards`, то есть процесс без пользовательского
диалога тянет модули, которые импортируют `aiogram`.
**Почему это плохо:** тексты и клавиатуры становятся общим контрактом двух
процессов; изменение UI-слоя может сломать воркер, а тесты воркера тянут
aiogram-типы.
**Как правильно:** вынести пользовательские тексты уведомлений в отдельный
модуль вне `app/bot/` (например, `app/obs/` или `app/messages.py`) либо
передавать готовые строки в `WorkerServices`.

### Движок не закрывается при остановке воркера

**Что происходит:** у `HiggsfieldVideoEngine` есть `aclose`
(`app/engines/higgsfield.py:115`), закрывающий `httpx.AsyncClient`, но
`run_worker` (`app/main_worker.py:53`) в `finally` закрывает только сессию
бота и движок БД; `VideoEngine` в протоколе
(`app/engines/base.py:84`) метода закрытия не имеет.
**Почему это плохо:** при остановке процесса HTTP-соединения и пул
сокетов не освобождаются явно; полагаться на сборщик мусора в async-коде
нельзя.
**Как правильно:** добавить `aclose` (или `async def close`) в протокол с
реализацией no-op у `MockVideoEngine` и вызывать его в `finally` точки
сборки.

### `STORAGE` игнорируется

**Что происходит:** настройка `storage: Literal["local", "s3"]`
(`app/config.py:51`) не используется: `LocalStorage` создаётся напрямую в
`app/bot/services.py:35` и `app/main_worker.py:50`.
**Почему это плохо:** `STORAGE=s3` молча даст локальные файлы; граница
`Storage` из `openspec/project.md` не имеет точки выбора реализации.
**Как правильно:** `app/storage/factory.py` по образцу
`app/engines/factory.py`, и обе точки сборки берут хранилище оттуда.

## Обработка ошибок

**Стратегия:** ошибка — значение в ядре, исключение — на границе с внешним
миром, где оно сразу превращается в `Err` или в код для пользователя.

**Паттерны:**
- Домен возвращает `Result[T, E]` с типизированными `dataclass`-ошибками:
  `AlreadyPaid`, `IllegalTransition` (`app/domain/order_service.py:44`, `:59`),
  `InvalidAmount`, `AlreadyCharged`, `AlreadyRefunded`,
  `OrderNotRefundable` (`app/domain/ledger.py:29`), `FileTooLarge`,
  `UnsupportedFormat`, `ImageTooLarge`, `CorruptedImage`
  (`app/domain/moderation.py:34`), `InvalidTariff`
  (`app/domain/pricing.py:36`).
- `Result` не несёт текстов для пользователя: перевод делает
  `texts.refusal_text` (`app/bot/texts.py:80`) через `match`.
- Внешние ошибки типизированы иерархией `EngineError` с атрибутом `code`
  (`app/engines/base.py:42`), HTTP-коды маппятся в
  `error_for_status` (`app/engines/transport.py:114`).
- Пайплайн ловит `EngineError`/`PipelineError` и превращает их в
  `fail_job(code)`; всё остальное — `internal` с `logger.exception`
  (`app/worker/pipeline.py:50`).
- Нарушения инвариантов в оболочке — исключения: `repo.save_order` бросает
  `LookupError`, если заказа нет (`app/db/repo.py:159`);
  `repo.create_order` бросает `ValueError` при некорректном тарифе
  (`app/db/repo.py:133`); `queue_order` — `LookupError` при недопустимом
  переходе (`app/bot/handlers/upload.py:86`).
- Ошибки хранения не валят диалог: `save_photo` возвращает `bool`
  (`app/bot/photo.py:37`), `cleanup` глотает `OSError`
  (`app/worker/pipeline.py:158`), `notify_failure` глотает ошибку отправки.
- Ошибки конфигурации фатальны и не ретраятся: `ConfigError` →
  `SystemExit(2)` (`app/main_bot.py:47`, `app/main_worker.py:67`).

## Сквозные аспекты

**Логирование:** структурный JSON в stdout через `JsonLogFormatter`
(`app/obs/logs.py:32`); поля `ts`, `level`, `logger`, `message`,
`exception` плюс `extra`. Редакция PII по списку `SENSITIVE_FIELDS`
(`tg_id`, `photo`, `photo_path`, `photo_url`, `signed_url`, `download_url`)
с глубиной до 3 уровней (`app/obs/logs.py:81`). Логируются идентификаторы
(`order_id`, `job_id`, `error_code`), не содержимое файлов.

**Валидация:** два уровня. Конфигурация — `pydantic-settings` с `frozen=True`
и валидаторами (`app/config.py:14`). Пользовательский ввод — чистая
`moderation.prepare_photo` (`app/domain/moderation.py:75`); лимит размера
проверяется до скачивания в `download_photo` (`app/bot/photo.py:30`).
Проверки «одно лицо в кадре» нет — это зафиксировано в docstring модуля и
в тесте `tests/test_moderation.py:94`.

**Аутентификация и авторизация:** пользователь опознаётся по `tg_id` из
апдейта, отдельной сессии нет. Админ-команд, whitelist `TG_ADMIN_IDS` и
проверки `is_banned` в коде нет. Вебхука нет — используется long polling,
поэтому `TG_WEBHOOK_SECRET` не применяется.

**Идемпотентность:** три уровня по `openspec/project.md`, фактически
работают два: `update_id` через `DedupeMiddleware` (в памяти процесса) и
`payment_id` с `UNIQUE` в `orders` (`app/db/models.py:86`).
`idempotency_key` задания уникален в БД (`app/db/models.py:111`), но в
payload Higgsfield не передаётся — `build_payload`
(`app/engines/higgsfield.py:162`) отправляет только `video_url`,
`image_url`, `prompt`, `duration`, `resolution`.

**Наблюдаемость:** только логи и таблица `events`; модуля метрик, `/health`,
`/admin stats` и алертов в Telegram нет.

## Расхождения с `docs/architecture.md`

| Документ утверждает | Фактическое состояние |
|---|---|
| `api/webhook_*` принимает внешние события (§2, §9, §11) | Каталога `app/api/` нет; `fastapi`/`uvicorn` объявлены в `pyproject.toml`, но не используются; работает `start_polling` (`app/main_bot.py:37`) |
| `VideoEngine` = `ensure_asset` / `submit` / `poll` / `cancel` (§4) | Один метод `generate(spec)` (`app/engines/base.py:84`); `cancel` отсутствует |
| `PaymentProvider.handle_update(payload)` (§4) | Метода нет; `create_invoice` возвращает готовый `PaymentEvent` (`app/payments/base.py:45`) |
| Presigned URL с TTL 15 минут, приватный бакет (§9) | Только локальная файловая система, публичных ссылок нет (`app/storage/local.py`) |
| `worker/retry` — политика повторов и таймауты (§2, §7) | Модуля нет; повторы только внутри `HttpTransport` (`app/engines/transport.py:72`) |
| Сторож возвращает зависшие `running` в `new` (§6) | Не реализован; `JOB_STALE_MINUTES` не читается |
| `bot/middlewares` ведёт сессию БД (§2) | Сессия создаётся внутри хендлеров через `services.session_factory()`; middleware только `dedupe` и `throttle` |
| Между фото и выдачей есть `download` + `normalize` через ffmpeg (§3.1, шаги 11–12) | Шагов нет: результат движка уходит в Telegram как есть (`app/worker/pipeline.py:119`); ffmpeg используется только заглушкой движка (`app/engines/mock.py`) |
| `templates.engine_video_url` — кэш `ensure_asset` (§5) | Колонки есть в модели, но не заполняются; кэш живёт в памяти процесса (`app/engines/higgsfield.py:61`) |
| Модерация «одно лицо» (§2, §9) | Детекции лиц нет, только лимиты, формат и перекодирование (`app/domain/moderation.py:71`) |
| `domain/moderation` не хранит файлы (§2) | Соответствует: модуль работает с байтами в памяти |
| Гейты: кредиты движка, дневной лимит, kill switch, таймаут (§8) | Реализован только kill switch (`app/bot/handlers/checkout.py:41`); остальные настройки не читаются |
| Стейт-машина задания `new → submitted → polling → done` (§5) | `new → running → done/failed` (`app/db/repo.py:20`) |
| Порядок отказов: `rejected` без retry, `no_credits` = стоп продаж (§7) | Оба случая сводятся к `order.failed` + возврат кредита (`app/worker/pipeline.py:49`) |
| `obs/*` — логи, метрики, редакция PII (§2) | Есть только логи и редакция (`app/obs/logs.py`), метрик нет |
| `/admin stats`, алерты админу, админ-команды (§9, §10) | Отсутствуют; `TG_ADMIN_IDS` не читается |

---

*Анализ архитектуры: 2026-11-08*
