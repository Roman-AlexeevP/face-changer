---
last_mapped_commit: 8cdc2abb49b272f3240a75e55c06f62b162fc586
last_mapped_at: 2026-11-08
---
# Структура кодовой базы

**Дата анализа:** 2026-11-08

## Раскладка каталогов

```text
C:\Coding\face-changer\
├── app/                      # весь код приложения (единственный пакет)
├── tests/                    # pytest: юнит, архитектурный, интеграционный
├── docs/                     # проектная документация (архитектура, стек, план)
├── openspec/                 # OpenSpec: project.md + changes/mvp-001-core-flow/
├── .planning/codebase/       # карта кодовой базы (этот документ и ARCHITECTURE.md)
├── AGENTS.md                 # правила работы агентов и стиля кода
├── README.md                 # обзор, команды, ссылки на документы
├── pyproject.toml            # зависимости, ruff, pytest, coverage
├── alembic.ini               # script_location = app/db/migrations
├── Dockerfile                # стадии base / runtime / test
├── docker-compose.yml        # postgres, bot, worker, migrate, postgres-test, tests
├── tasks.ps1                 # обёртка над docker compose
├── tasks.cmd                 # шим для Windows PowerShell
├── .env                      # локальные секреты, в репозиторий не попадает
├── .env.example              # шаблон переменных окружения
├── .dockerignore
├── .gitignore
└── .gitattributes
```

Дерево `app/`:

```text
app/
├── __init__.py               # докстринг пакета
├── config.py                 # Settings (pydantic-settings), ConfigError
├── clock.py                  # utc_now — единственное чтение времени в оболочке
├── main_bot.py               # точка сборки бота: Dispatcher, polling, сид
├── main_worker.py            # точка сборки воркера: движок, пул, сигналы
├── bot/                      # императивная оболочка Telegram
│   ├── __init__.py
│   ├── keyboards.py          # инлайн-клавиатуры и callback_data
│   ├── photo.py              # выбор вложения, скачивание, сохранение
│   ├── services.py           # BotServices + build_bot_services
│   ├── texts.py              # все пользовательские строки и их маппинг
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py          # /start, согласие, домашний экран
│   │   ├── checkout.py       # создание заказа, stub-оплата, ledger
│   │   └── upload.py         # приём фото, queued + job(new)
│   └── middlewares/
│       ├── __init__.py
│       ├── dedupe.py         # дедуп update_id (память процесса)
│       └── throttle.py       # лимит частоты на tg_id (память процесса)
├── db/                       # инфраструктура данных
│   ├── __init__.py
│   ├── models.py             # шесть таблиц, индексы, naming_convention
│   ├── repo.py               # тонкие запросы, frozen-типы, to_* преобразования
│   ├── seed.py               # дефолтный шаблон при пустой таблице
│   ├── session.py            # build_engine, build_session_factory
│   └── migrations/
│       ├── env.py            # DATABASE_URL берётся из Settings
│       ├── script.py.mako    # шаблон автогенерации ревизий
│       └── versions/
│           └── 0001_initial.py
├── domain/                   # чистое ядро, без I/O
│   ├── __init__.py
│   ├── ledger.py             # topup / debit / refund / calculate_balance
│   ├── moderation.py         # валидация и перекодирование фото
│   ├── order_service.py      # Order, OrderStatus, TRANSITIONS, переходы
│   ├── pricing.py            # Tariff, quote, build_order, order_price
│   └── result.py             # Ok / Err / Result
├── engines/                  # порт и адаптеры видео-движка
│   ├── __init__.py
│   ├── base.py               # EngineStatus, JobSpec, EngineResult, VideoEngine, ошибки
│   ├── factory.py            # build_video_engine + build_higgsfield_engine
│   ├── higgsfield.py         # upload → submit → poll
│   ├── mock.py               # ffmpeg/lavfi заглушка
│   └── transport.py          # HttpTransport: авторизация, повторы, маппинг кодов
├── obs/                      # наблюдаемость
│   ├── __init__.py
│   └── logs.py               # JSON-форматтер и редакция PII
├── payments/                 # порт и адаптер оплаты
│   ├── __init__.py
│   ├── base.py               # PaymentProvider, Invoice, PaymentEvent, PaymentStatus
│   ├── factory.py            # stub либо ConfigError
│   └── stub.py               # мгновенный успех, stub-<order_id>
├── storage/                  # порт и адаптер временного хранилища
│   ├── __init__.py
│   ├── base.py               # Storage Protocol
│   └── local.py              # LocalStorage(STORAGE_DIR)
└── worker/                   # императивная оболочка воркера
    ├── __init__.py
    ├── loop.py               # run_pool, run_slot, claim_next
    ├── pipeline.py           # process_job и шаги обработки заказа
    └── services.py           # WorkerServices
```

Дерево `tests/`:

```text
tests/
├── conftest.py                   # схема на воркер pytest-xdist, откат транзакции
├── test_architecture.py          # domain/ не импортирует инфраструктуру
├── test_bot_wiring.py            # регистрация хендлеров и непустые тексты
├── test_config.py                # типизация env и обязательные секреты
├── test_engines_mock.py          # mock-движок и отсутствие ffmpeg
├── test_higgsfield_engine.py     # submit/poll/повторы/маппинг статусов
├── test_ledger.py                # чистые записи ledger
├── test_logs.py                  # JSON-логи и редакция PII
├── test_models.py                # схема: таблицы, колонки, индексы
├── test_moderation.py            # лимиты, форматы, EXIF
├── test_order_service.py         # все переходы стейт-машины
├── test_payments_stub.py         # инвойс и refund заглушки
├── test_pricing.py               # фиксация цены в заказе
├── test_repo_integration.py      # PostgreSQL, маркер integration
├── test_result.py                # Ok/Err, неизменяемость, pattern matching
└── test_seed.py                  # промпт из файла и фолбэк
```

## Назначение каталогов

**`app/domain/`:**
- Назначение: бизнес-правила как чистые функции; единственное место, где
  живут инварианты заказа, ledger, цены и приёма фото.
- Содержит: `@dataclass(frozen=True)` для значений и ошибок, `StrEnum`
  статусов, таблицы переходов, `Result`.
- Ключевые файлы: `app/domain/order_service.py` (стейт-машина),
  `app/domain/ledger.py`, `app/domain/pricing.py`,
  `app/domain/moderation.py`, `app/domain/result.py`.
- Запрещено: импорт `aiogram`, `sqlalchemy`, `httpx`, `os`, `time`,
  `random`, `uuid` (проверяется `tests/test_architecture.py:38`),
  любые чтения часов и файлов.

**`app/bot/`:**
- Назначение: диалог с пользователем и оркестрация шагов воронки.
- Содержит: хендлеры с `build_router()`, middleware, тексты, клавиатуры,
  загрузку фото, `BotServices`.
- Ключевые файлы: `app/bot/handlers/start.py`,
  `app/bot/handlers/checkout.py`, `app/bot/handlers/upload.py`,
  `app/bot/services.py`, `app/bot/texts.py`.

**`app/bot/handlers/`:**
- Назначение: один модуль на шаг воронки.
- Содержит: регистрацию фильтров в `build_router()` и тонкие функции
  обработки; вся бизнес-логика вызывается из `app/domain/`.
- Ключевые файлы: `start.py`, `checkout.py`, `upload.py`.
- Запрещено: `handle_*`, который содержит правила заказа, прямую запись
  `order.status` и HTTP-вызовы к движку.

**`app/bot/middlewares/`:**
- Назначение: сквозная обработка апдейтов до хендлеров.
- Содержит: классы-наследники `aiogram.BaseMiddleware` с состоянием в
  памяти процесса (`OrderedDict` в `dedupe.py`, `dict` в `throttle.py`).
- Ключевые файлы: `app/bot/middlewares/dedupe.py`,
  `app/bot/middlewares/throttle.py`.

**`app/db/`:**
- Назначение: инфраструктура данных — модели, запросы, сессии, сид,
  миграции.
- Содержит: ORM-модели, функции `repo.py`, фабрику сессий, ревизии Alembic.
- Ключевые файлы: `app/db/models.py`, `app/db/repo.py`,
  `app/db/session.py`, `app/db/seed.py`.
- Правило: `repo.py` — только чтение/запись, никаких бизнес-правил;
  единственное исключение — вызов чистого `pricing.quote` при создании
  заказа (`app/db/repo.py:131`).

**`app/engines/`:**
- Назначение: порт генерации и его реализации.
- Содержит: `base.py` (контракт), `factory.py` (выбор по `ENGINE`),
  адаптеры `mock.py`/`higgsfield.py`, `transport.py` для HTTP.
- Ключевые файлы: `app/engines/base.py`, `app/engines/higgsfield.py`,
  `app/engines/transport.py`, `app/engines/factory.py`.

**`app/payments/`:**
- Назначение: порт оплаты и адаптер-заглушка.
- Содержит: `base.py` с `PaymentProvider`, `stub.py`, `factory.py`.
- Ключевые файлы: `app/payments/base.py`, `app/payments/stub.py`,
  `app/payments/factory.py`.

**`app/storage/`:**
- Назначение: порт временного хранения файлов заказа и локальная реализация.
- Содержит: `base.py` с `Storage`, `local.py` с `LocalStorage`.
- Ключевые файлы: `app/storage/base.py`, `app/storage/local.py`.
- Факт: фабрики нет, `LocalStorage` создаётся напрямую в
  `app/bot/services.py:35` и `app/main_worker.py:50`.

**`app/worker/`:**
- Назначение: оркестрация очереди и одного заказа.
- Содержит: пул слотов, claim через `SKIP LOCKED`, пайплайн, `WorkerServices`.
- Ключевые файлы: `app/worker/loop.py`, `app/worker/pipeline.py`,
  `app/worker/services.py`.
- Запрещено: пользовательские тексты (они берутся из `app/bot/texts.py`) и
  прямые переходы статуса в обход `order_service`.

**`app/obs/`:**
- Назначение: структурные логи и редакция PII.
- Содержит: `JsonLogFormatter`, `configure_logging`, `redact_field`.
- Ключевые файлы: `app/obs/logs.py`.

**`tests/`:**
- Назначение: pytest-наборы по слоям.
- Содержит: юнит-тесты домена без БД и сети, архитектурный тест, тесты
  оболочки с фейками, интеграционные тесты на PostgreSQL.
- Ключевые файлы: `tests/conftest.py`, `tests/test_architecture.py`,
  `tests/test_repo_integration.py`.

**`docs/`:**
- Назначение: проектная документация.
- Ключевые файлы: `docs/architecture.md`, `docs/stack.md`,
  `docs/implementation-plan.md`, `docs/higgsfield-contract.md`.

**`openspec/`:**
- Назначение: спецификации и изменение `mvp-001-core-flow`.
- Ключевые файлы: `openspec/project.md`,
  `openspec/changes/mvp-001-core-flow/{proposal,design,tasks}.md`,
  `openspec/changes/mvp-001-core-flow/specs/*/spec.md`.

**`.planning/codebase/`:**
- Назначение: карта кодовой базы для планировщика и исполнителя GSD.
- Ключевые файлы: `.planning/codebase/ARCHITECTURE.md`,
  `.planning/codebase/STRUCTURE.md`.

## Ключевые файлы

**Точки входа:**
- `app/main_bot.py`: `main()` (`:43`), `run_bot()` (`:30`),
  `build_dispatcher()` (`:18`).
- `app/main_worker.py`: `main()` (`:61`), `run_worker()` (`:41`),
  `install_signal_handlers()` (`:29`).
- `app/db/migrations/env.py`: окружение Alembic, `DATABASE_URL` из
  `Settings`.
- `app/bot/handlers/*.py`: функции `build_router()` — точки расширения
  диспетчера.

**Конфигурация:**
- `app/config.py`: `Settings`, `load_settings`, `require_bot_token`,
  `require_engine_credentials`.
- `pyproject.toml`: зависимости, `[tool.ruff]`, `[tool.pytest.ini_options]`,
  `[tool.coverage.*]`.
- `alembic.ini`: `script_location = %(here)s/app/db/migrations`.
- `docker-compose.yml`: профили `tools`, `test`; сервисы `bot`, `worker`,
  `migrate`, `tests`, `postgres-test`.
- `.env.example`: шаблон переменных; `.env` содержит локальные секреты и в
  репозиторий не попадает.

**Логика:**
- `app/domain/order_service.py`: `OrderStatus`, `TRANSITIONS`,
  `transition`, `pay`, `enqueue`, `start`, `deliver`, `fail`, `reject`,
  `mark_refunded`, `purge`, `is_active`, `is_awaiting_photo`.
- `app/domain/ledger.py`: `top_up`, `debit`, `refund`,
  `calculate_balance`.
- `app/domain/pricing.py`: `quote`, `build_order`, `order_price`.
- `app/domain/moderation.py`: `validate_photo`, `prepare_photo`.
- `app/worker/pipeline.py`: `process_job`, `start_order`, `generate_video`,
  `deliver`, `mark_delivered`, `cleanup`, `fail_job`, `mark_failed`,
  `refund_credit`, `notify_failure`.
- `app/worker/loop.py`: `run_pool`, `run_slot`, `claim_next`.
- `app/db/repo.py`: `create_order`, `load_order`, `save_order`,
  `get_active_order`, `create_job`, `claim_job`, `finish_job`,
  `add_ledger_entry`, `record_event`.
- `app/engines/higgsfield.py`: `generate`, `ensure_video_url`, `submit`,
  `poll`, `build_payload`, `map_status`.
- `app/bot/handlers/checkout.py`: `handle_checkout`, `start_checkout`,
  `open_order`, `charge_order`, `write_ledger`.

**Тесты:**
- `tests/test_architecture.py`: запрет инфраструктурных импортов в
  `app/domain/`.
- `tests/conftest.py`: фикстуры `db_schema` и `session` (схема на воркер,
  откат транзакции, `join_transaction_mode="create_savepoint"`).
- `tests/test_repo_integration.py`: маркер `pytest.mark.integration`,
  требует `TEST_DATABASE_URL`.
- Запуск: `.\tasks.ps1 test` (контейнер `tests`), отчёт в `reports/`.

## Соглашения об именовании

**Файлы:**
- `snake_case.py`; имя модуля — существительное-возможность, а не действие:
  `order_service.py`, `moderation.py`, `pricing.py`, `ledger.py`.
- Порт всегда `base.py` (`engines/base.py`, `payments/base.py`,
  `storage/base.py`), реализация — по имени технологии: `mock.py`,
  `higgsfield.py`, `stub.py`, `local.py`; сборка — `factory.py`.
- Точки входа процесса — `main_<процесс>.py`: `main_bot.py`,
  `main_worker.py`.
- Хендлер — `app/bot/handlers/<шаг>.py`: `start.py`, `checkout.py`,
  `upload.py`.
- Миграция — `<номер>_<описание>.py`, где номер — четыре цифры:
  `0001_initial.py`.
- Тест — `test_<имя_модуля>.py`: `test_order_service.py` для
  `app/domain/order_service.py`.

**Каталоги:**
- Однословные, в нижнем регистре: `domain`, `engines`, `payments`,
  `storage`, `worker`, `obs`, `db`, `bot`.
- Множественное число — только для набора однотипных элементов:
  `handlers`, `middlewares`, `migrations`, `versions`.
- Запрещены `utils`, `helpers`, `common`, `shared`, `misc` — в проекте их
  нет; для общей зависимости используется явный `services.py` рядом с
  потребителем.

**Функции:**
- Название — глагол и объект: `build_spec`, `claim_next`, `send_video`,
  `mark_delivered`, `refund_credit`, `load_chat_id`, `record_event`,
  `to_order`.
- Префиксы по смыслу: `build_*` — собрать значение/объект, `load_*` —
  прочитать из БД, `create_*` — создать строку, `record_*` — записать факт,
  `claim_*` — взять из очереди, `finish_*` — закрыть, `to_*` — преобразовать
  строку в доменный тип, `is_*` — предикат.
- `handle_*` — только зарегистрированные в `Router` колбэки aiogram
  (`handle_start`, `handle_consent`, `handle_checkout`, `handle_photo`,
  `handle_other`); внутренние шаги хендлера называются глаголом
  (`start_checkout`, `open_order`, `charge_order`, `queue_order`,
  `accept_photo`).
- `process_job` (`app/worker/pipeline.py:41`) — единственное исключение из
  правила «без `process`»: это оркестратор шагов, а не исполнитель одного
  действия.
- Приватные помощники — с ведущим подчёркиванием: `_stamp`, `_has_reason`,
  `_open_image`, `_normalize`, `_reencode`, `_attempt`, `_is_throttled`,
  `_remember`.

**Классы и типы:**
- `PascalCase`; значения домена — `@dataclass(frozen=True)`: `Order`,
  `LedgerEntry`, `Tariff`, `OrderDraft`, `Price`, `PreparedPhoto`,
  `PhotoPolicy`, `JobSpec`, `EngineResult`, `Invoice`, `PaymentEvent`.
- Ошибка домена — тоже `frozen`-датакласс с говорящим именем-ситуацией:
  `AlreadyPaid`, `IllegalTransition`, `AlreadyCharged`, `AlreadyRefunded`,
  `OrderNotRefundable`, `InvalidAmount`, `InvalidTariff`, `FileTooLarge`,
  `UnsupportedFormat`, `ImageTooLarge`, `CorruptedImage`.
- Исключения оболочки — суффикс `Error`: `ConfigError`, `PipelineError`,
  `EngineError` и подтипы, `PaymentFailed`.
- Статусы — `StrEnum` с `UPPER_SNAKE` членами и строчными значениями:
  `OrderStatus.PAID = "paid"`, `EngineStatus.NO_CREDITS = "no_credits"`,
  `JobStatus.NEW = "new"`, `LedgerReason.ORDER_PAID = "order_paid"`.
- Контейнеры зависимостей — `*Services` (`BotServices`, `WorkerServices`);
  политики — `*Policy` (`ThrottlePolicy`, `RetryPolicy`, `PhotoPolicy`);
  конфиги адаптеров — `*Config` (`HiggsfieldConfig`).

**Переменные и константы:**
- Константы модуля — `UPPER_SNAKE`: `MAX_BYTES`, `MAX_SIDE`,
  `JPEG_QUALITY`, `ALLOWED_FORMATS`, `RETRY_DELAYS_SEC`,
  `IDLE_DELAY_SEC`, `CONSENT_VERSION`, `DEFAULT_TEMPLATE_KEY`.
- Приватное состояние экземпляра — с `_`: `_seen`, `_last_seen`,
  `_policy`, `_retry`, `_sleep`, `_client`.
- Деньги — суффикс `_kopecks` (`price_kopecks`, `amount_kopecks`); время —
  суффикс `_at` (`created_at`, `paid_at`, `delivered_at`, `consent_at`).
- Идентификаторы внешних систем — суффикс `_id` (`payment_id`,
  `request_id`, `tg_id`).

**Тексты и язык:**
- Идентификаторы, имена файлов, docstring-термины и статусы — английские.
- Docstring модулей и функций — русские, одна строка, без «что делает» у
  очевидных функций.
- Пользовательские строки — только в `app/bot/texts.py`; коды ошибок —
  ключи `FAILURE_TEXTS` (`app/bot/texts.py:48`).
- События — строчный snake_case: `consent_given`, `order_created`,
  `order_paid`, `photo_accepted`, `order_delivered`, `job_failed`,
  `refund_issued`.

**Импорты:**
- Порядок групп задаёт ruff/isort: стандартная библиотека, сторонние
  пакеты, first-party `app` (`known-first-party = ["app"]`,
  `pyproject.toml:50`).
- Абсолютные импорты от `app.`: `from app.domain.order_service import Order`.
- Внутри `app/domain/` — только `app.domain.*` и стандартная библиотека.

## Куда добавлять новый код

**Новое правило заказа (статус, переход, инвариант):**
- Основной код: `app/domain/order_service.py` — новая функция перехода
  через `transition` плюс строка в `TRANSITIONS`, если добавляется статус.
- Тесты: `tests/test_order_service.py` — параметризованные legal/illegal
  пары (`legal_pairs`/`illegal_pairs`).
- Обязательно: обновить `docs/architecture.md` §5 и спецификацию
  `openspec/changes/mvp-001-core-flow/specs/`, если меняется контракт.

**Новый шаг воронки бота:**
- Хендлер: `app/bot/handlers/<шаг>.py` с `build_router()`; регистрация в
  `app/main_bot.py:build_dispatcher` (порядок роутеров важен:
  `start → checkout → upload`).
- Тексты: `app/bot/texts.py`; кнопки и `callback_data` —
  `app/bot/keyboards.py` (константы `*_CALLBACK`).
- Тесты: `tests/test_bot_wiring.py` — проверка регистрации; тексты —
  отдельным тестом на непустоту.
- Нельзя: писать в `order.status` напрямую, вызывать движок, добавлять
  SQL сложнее одного вызова `repo.*`.

**Новый платёжный провайдер:**
- Реализация: `app/payments/<провайдер>.py` (например,
  `app/payments/yookassa.py`) с `name` и методами порта.
- Сборка: ветка в `app/payments/factory.py:build_payment_provider`.
- Конфиг: поля в `app/config.py:Settings`, значения в `.env.example` и в
  таблице env `docs/stack.md`.
- Тесты: `tests/test_payments_<провайдер>.py` по образцу
  `tests/test_payments_stub.py`.

**Новый видео-движок:**
- Реализация: `app/engines/<движок>.py`, реализующая `generate(spec)`;
  ошибки — подтипы `EngineError` с атрибутом `code`.
- Сборка: ветка в `app/engines/factory.py:build_video_engine`; новый
  литерал в `app/config.py:32`.
- Тесты: `tests/test_engines_<движок>.py` с фейковым `HttpTransport` по
  образцу `tests/test_higgsfield_engine.py`.
- Нельзя: добавлять ретраи и таймауты заказа внутрь движка — это политика
  оболочки.

**Новое хранилище:**
- Реализация: `app/storage/<хранилище>.py` с протоколом `Storage`.
- Сборка: создать `app/storage/factory.py` (сейчас отсутствует) и вызывать
  его в `app/bot/services.py:build_bot_services` и
  `app/main_worker.py:run_worker` вместо прямого `LocalStorage`.

**Новый запрос к БД или запись:**
- Основной код: `app/db/repo.py`, функция-глагол без бизнес-правил;
  входные данные — `frozen`-датакласс (`NewOrder`, `JobRequest`,
  `EventRecord`, `JobOutcome`), выход — доменный тип через `to_*`.
- Схема: `app/db/models.py` плюс миграция
  `app/db/migrations/versions/0002_<описание>.py`.
- Тесты: `tests/test_models.py` (для схемы) и
  `tests/test_repo_integration.py` (для запросов, маркер `integration`).

**Новое событие аналитики:**
- Вызов: `repo.record_event(session, repo.EventRecord(name, user_id, props))`
  рядом с уже существующими (`app/worker/pipeline.py:144`).
- Имя — snake_case; `props` — только идентификаторы, без PII.
- Потребители: пока только таблица `events`; `docs/architecture.md` §10
  перечисляет ожидаемые имена.

**Новый текст или код отказа:**
- Текст: `app/bot/texts.py` (константа или ключ `FAILURE_TEXTS`).
- Код ошибки: должен совпадать с `EngineError.code` или `PipelineError.code`,
  иначе пользователь получит `GENERIC_FAILURE`.

**Новая настройка:**
- `app/config.py:Settings` с типом и дефолтом.
- `.env.example` — строка-шаблон.
- `docs/stack.md` §«Переменные окружения».
- Нельзя: читать `os.environ` вне `app/config.py`.

**Новая точка входа или процесс:**
- `app/main_<процесс>.py` с `main()` и `asyncio.run`, по образцу
  `app/main_bot.py`.
- Сервис в `docker-compose.yml`; команда — `python -m app.main_<процесс>`.
- Обязательно: `configure_logging` и `ConfigError → SystemExit(2)`.

**Общий помощник:**
- Если он нужен двум процессам — `app/<область>/` рядом с потребителем
  (`app/clock.py`, `app/obs/logs.py`), а не `utils.py`.
- Если он нужен только одному модулю — приватная функция в этом модуле
  (`_stamp` в `app/domain/order_service.py`, `_normalize` в
  `app/domain/moderation.py`, `_attempt` в `app/engines/transport.py`).

**Тест:**
- Домен: `tests/test_<модуль>.py`, без БД и сети; время передаётся
  параметром, а не мокается.
- Порты: фейк-объект в тесте (`tests/test_engines_mock.py`,
  `tests/test_payments_stub.py`).
- Оболочка: `tests/test_bot_wiring.py` для сборки, интеграция — только с
  маркером `integration`.

## Специальные каталоги

**`.planning/codebase/`:**
- Назначение: карта кодовой базы (`ARCHITECTURE.md`, `STRUCTURE.md`),
  которой пользуются планировщик и исполнитель.
- Генерируется: да (агентом `gsd-codebase-mapper`).
- Коммитится: да.

**`reports/`:**
- Назначение: HTML-отчёт pytest и покрытие (`reports/report.html`,
  `reports/coverage/index.html`).
- Генерируется: да, `.\tasks.ps1 test`.
- Коммитится: нет.

**`face_changer.egg-info/`:**
- Назначение: метаданные editable-установки (`pip install -e .`).
- Генерируется: да, сборкой.
- Коммитится: нет.

**`.venv/`, `.uv-cache/`, `.npm-cache/`, `.pytest_cache/`, `.ruff_cache/`:**
- Назначение: локальные кеши инструментов.
- Генерируется: да.
- Коммитится: нет.

**`tmp/`, `.tmp/`:**
- Назначение: следы локальных прогонов (pip-сборки, тестовые каталоги).
- Генерируется: да.
- Коммитится: нет.

**`docs/`, `openspec/`:**
- Назначение: документация и спецификации.
- Генерируется: нет.
- Правило: код не меняется в обход спецификации; при расхождении сначала
  правится `openspec/changes/<id>/`, затем код.

**`.env`:**
- Назначение: локальные секреты (`TG_BOT_TOKEN`, ключи Higgsfield,
  `DATABASE_URL`).
- Генерируется: нет, создаётся вручную из `.env.example`.
- Коммитится: нет; содержимое не попадает в документы и логи.

**Каталог `templates/` (отсутствует):**
- Ожидается документацией: `templates/default/source.mp4` и
  `templates/default/prompt.txt` читаются `app/db/seed.py:18` и
  `:13`; `docs/stack.md` описывает `templates/<key>/config.yaml`.
- Фактически: каталога в репозитории нет, `resolve_prompt` молча
  возвращает `DEFAULT_PROMPT`, а `template.source_path` остаётся строкой
  `templates/default/source.mp4`, которой нет на диске.

## Бюджет размера модулей

Ограничение `AGENTS.md` — 300 строк на модуль. Текущие крупнейшие модули:

| Модуль | Строк |
|---|---|
| `app/db/repo.py` | 284 |
| `app/engines/higgsfield.py` | 230 |
| `app/worker/pipeline.py` | 218 |
| `app/db/migrations/versions/0001_initial.py` | 212 |
| `app/engines/transport.py` | 171 |
| `app/domain/order_service.py` | 166 |
| `app/db/models.py` | 152 |

`app/db/repo.py` ближе всего к пределу: новый запрос стоит добавлять,
только если он не раздувает модуль сверх 300 строк, иначе — делить
репозиторий по агрегатам (`repo_orders.py`, `repo_jobs.py`) с сохранением
импорта из `app/db/__init__.py`.

## Расхождения с раскладкой из `docs/stack.md`

`docs/stack.md:78-108` описывает структуру, часть которой не создана, и не
упоминает существующие модули.

**Описано, но отсутствует:**
- `app/api/{webhook_tg,health}.py` — каталога `app/api/` нет.
- `app/worker/retry.py` — политики повторов задания нет.
- `app/storage/s3.py` — реализация S3 отсутствует.
- `app/payments/yookassa.py` — реальная оплата не реализована.
- `app/obs/metrics.py` — метрик нет.
- `app/bot/handlers/{catalog,status,admin}.py` — шагов выбора шаблона,
  статуса и админки нет.
- `app/bot/middlewares/db_session.py` — сессия БД в middleware не
  создаётся.
- `templates/<key>/{source.mp4,config.yaml,preview.mp4}` — каталога нет.
- `.env.example` в списке отсутствует, но файл есть.

**Существует, но не описано:**
- `app/clock.py`, `app/bot/photo.py`, `app/bot/services.py`,
  `app/worker/services.py`, `app/engines/transport.py`,
  `app/engines/factory.py`, `app/payments/factory.py`, `app/db/seed.py`,
  `app/domain/{result,ledger,pricing}.py`.

**Совпадает:** `app/main_bot.py`, `app/main_worker.py`, `app/config.py`,
`app/domain/{order_service,moderation}.py`, `app/engines/{base,mock,
higgsfield}.py`, `app/payments/{base,stub}.py`, `app/storage/{base,local}.py`,
`app/worker/{loop,pipeline}.py`, `app/obs/logs.py`, `app/db/{models,repo,
session}.py`.

---

*Анализ структуры: 2026-11-08*
