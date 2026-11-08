---
last_mapped_commit: 8cdc2abb49b272f3240a75e55c06f62b162fc586
last_mapped_at: 2026-11-08
---
<!-- refreshed: 2026-11-08 -->
# Coding Conventions

**Analysis Date:** 2026-11-08

## Functional Rules

**Функциональное ядро, императивная оболочка.** Базовое правило проекта (`AGENTS.md:28-75`)
соблюдается во всём коде: бизнес-логика — чистые функции над неизменяемыми данными, всё,
что общается с миром, живёт на краю.

| Слой | Где | Что разрешено |
|---|---|---|
| Чистое ядро | `app/domain/` | Чистые функции, `dataclass(frozen=True)`, `StrEnum`, `frozenset`, `MappingProxyType`. Импорты: stdlib (`dataclasses`, `datetime`, `enum`, `io`, `types`, `collections.abc`) и `PIL` — только для декодирования байтов в памяти (`app/domain/moderation.py`). |
| Императивная оболочка | `app/bot/`, `app/worker/`, `app/db/`, `app/engines/`, `app/payments/`, `app/storage/`, `app/obs/`, `app/config.py`, `app/clock.py`, `app/main_*.py` | I/O, БД, сеть, файлы, часы, `raise`, тонкие клиенты внешних API. |

Запрет на инфраструктурные импорты в ядре проверяется тестом:
`tests/test_architecture.py:8` — `FORBIDDEN_MODULES = {"aiogram", "sqlalchemy", "httpx", "os", "time", "random", "uuid"}`;
тест парсит AST всех файлов `app/domain/*.py` и требует пустой список нарушений
(`tests/test_architecture.py:29-41`).

**Ошибки как значения (`Result`).** В домене нет исключений — только
`Result[T, E]` из `app/domain/result.py`:

```python
# app/domain/result.py:6-20
@dataclass(frozen=True)
class Ok[T]:
    value: T


@dataclass(frozen=True)
class Err[E]:
    error: E


type Result[T, E] = Ok[T] | Err[E]
```

Правила:

- Функция, которая может отказать, возвращает `Result`; тип ошибки — `frozen` датакласс
  с данными, а не строка (`AlreadyPaid(order_id)`, `IllegalTransition(order_id, current, target)`).
- Набор ошибок операции — union-алиас: `type OrderError = AlreadyPaid | IllegalTransition`
  (`app/domain/order_service.py:68`), `type LedgerError = ...` (`app/domain/ledger.py:58`),
  `type PhotoError = ...` (`app/domain/moderation.py:63`), `type PricingError = InvalidTariff`
  (`app/domain/pricing.py:44`).
- Успех без возможности отказа возвращается значением, не `Ok`: `attach_payment` → `Order`
  (`app/domain/order_service.py:107`), `calculate_balance` → `int` (`app/domain/ledger.py:111`).
- `raise` в `app/domain/` отсутствует (0 совпадений на 2026-11-08).
- Оболочка разворачивает `Result` через `isinstance(result, Err)` либо `match`:
  `app/bot/handlers/upload.py:69-75`, `app/worker/pipeline.py:64-66`, `app/db/repo.py:132`.
- Пользователю никогда не уходит текст исключения — только человеческая фраза из
  `app/bot/texts.py:80-97`.

**Неизменяемые данные.** Все доменные типы — `@dataclass(frozen=True)`; изменение только
через `dataclasses.replace`:

```python
# app/domain/order_service.py:93-104
def transition(order: Order, target: OrderStatus, now: datetime) -> Result[Order, OrderError]:
    if target not in TRANSITIONS[order.status]:
        return Err(IllegalTransition(order.id, order.status, target))
    return Ok(_stamp(replace(order, status=target), target, now))
```

- Справочники — `frozenset` и `MappingProxyType`, не изменяемые литералы:
  `ACTIVE_STATUSES` (`app/domain/order_service.py:70`), `TRANSITIONS` (`:74`),
  `REFUNDABLE_STATUSES` (`app/domain/ledger.py:60`), `ALLOWED_FORMATS`
  (`app/domain/moderation.py:13`).
- Аргументы не мутируются: `ledger.debit(order, entries)` только читает `entries`
  (`app/domain/ledger.py:77`); в сигнатурах — `Sequence`/`Mapping`, а не `list`/`dict`.
- Мутабельные значения по умолчанию запрещены; вместо них `field(default_factory=...)`
  (`EventRecord.props`, `app/db/repo.py:82`) или неизменяемый синглтон
  (`DEFAULT_POLICY = PhotoPolicy()`, `app/domain/moderation.py:65`).

**Явные зависимости.**

- Время входит параметром `now` в каждую доменную функцию, которая ставит отметку
  (`pay(order, now)`, `fail(order, now, error_code)`); домен не читает часы.
- В оболочке часы и «сейчас» приходят из `app/clock.py:6` и подставляются как
  `now: Callable[[], datetime] = utc_now` в `BotServices` (`app/bot/services.py:25`) и
  `WorkerServices` (`app/worker/services.py:25`).
- Порты — `Protocol` с `...`-телами: `VideoEngine` (`app/engines/base.py:84`),
  `PaymentProvider` (`app/payments/base.py:40`), `Storage` (`app/storage/base.py:7`).
  Наследования между реализациями нет; реализация выбирается в точке сборки
  (`app/main_bot.py:36`, `app/main_worker.py:45-51`, `app/engines/factory.py:12-16`).
- Зависимости передаются в хендлеры через `Dispatcher["services"]`
  (`app/main_bot.py:26`) и через frozen-контексты `Checkout`, `PhotoUpload`
  (`app/bot/handlers/checkout.py:25`, `app/bot/handlers/upload.py:21`).

**Статус заказа меняется только переходом.** Прямая запись `order.status` есть только
внутри `repo.save_order` как перенос уже вычисленного значения (`app/db/repo.py:160`);
решение о переходе принимает `order_service.transition` / именованные обёртки
(`pay`, `enqueue`, `start`, `deliver`, `fail`, `reject`, `mark_refunded`, `purge`).

**Разрешённое изменяемое состояние.** Три места, все — тонкие клиенты/адаптеры:

- `DedupeMiddleware._seen` и `ThrottleMiddleware._last_seen` — in-memory кеши на процесс
  (`app/bot/middlewares/dedupe.py:16`, `app/bot/middlewares/throttle.py:27`).
- `HiggsfieldVideoEngine.video_urls` — кеш загруженного шаблона, поле `frozen` датакласса
  с пометкой в комментарии (`app/engines/higgsfield.py:61`).
- `HttpTransport._client` — `httpx.AsyncClient` (`app/engines/transport.py:55`).

`global` и модульные кеши в коде отсутствуют (0 совпадений).

## Naming Patterns

**Files:**

- `snake_case`, один модуль — одна ответственность. Файлов `utils.py`, `helpers.py`,
  `common.py` нет.
- Суффиксы несут роль: `*_service.py` — доменный сервис (`app/domain/order_service.py`),
  `base.py` — порт и типы ошибок (`app/engines/base.py`, `app/payments/base.py`,
  `app/storage/base.py`), `factory.py` — сборка (`app/engines/factory.py`,
  `app/payments/factory.py`), `mock.py` / `stub.py` / `local.py` — реализации
  (`app/engines/mock.py`, `app/payments/stub.py`, `app/storage/local.py`),
  `pipeline.py` / `loop.py` / `services.py` — воркер, `repo.py` / `session.py` /
  `models.py` / `seed.py` — БД, `logs.py` — наблюдаемость.
- Тесты: `tests/test_<subject>.py`, где subject — модуль или возможность.
- Миграции: `NNNN_slug.py` (`app/db/migrations/versions/0001_initial.py`).

**Functions:**

- Имя = глагол + объект: `build_order`, `calculate_balance`, `parse_retry_after`,
  `extract_upload_url`, `resolve_prompt`, `redact_field`, `compute_delay`.
- Используемые префиксы: `build_*` (собрать значение), `create_*` (создать сущность),
  `load_*` / `get_*` (прочитать), `save_*` / `record_*` / `add_*` (записать),
  `is_*` / `has_*` (предикат: `is_active`, `is_deliverable`, `is_awaiting_photo`,
  `is_remote_url`, `is_blank_secret`, `_has_reason`), `format_*`, `describe_*`,
  `require_*` (проверка конфигурации), `ensure_*` (ленивая инициализация),
  `apply_*`, `install_*`, `run_*` (циклы и точки входа).
- Приватные помощники — с `_` и без докстринга: `_stamp`, `_has_reason`,
  `_open_image`, `_normalize`, `_reencode`, `_attempt`, `_remember`, `_is_throttled`.
- Исключения из «глагол + объект»: `handle_*` в `app/bot/handlers/` (конвенция aiogram) и
  `process_job` (`app/worker/pipeline.py:41`) как оркестратор одного задания.
- Конвертеры строк БД → домен: `to_order`, `to_ledger_entry` (`app/db/repo.py:259,277`).

**Variables:**

- `snake_case`, единицы измерения в имени: `price_kopecks`, `amount_kopecks`,
  `credits_cost`, `timeout_sec`, `poll_max_min`, `min_interval_sec`, `MAX_BYTES`,
  `max_side` (px), `jitter_ratio`.
- Идентификаторы и внешние ключи: `order_id`, `user_id`, `template_id`, `job_id`,
  `tg_id`, `payment_id`, `request_id`, `idempotency_key`.
- Время: `now`, `created_at`, `paid_at`, `delivered_at`, `next_attempt_at`,
  `submitted_at`, `finished_at` — все `datetime` с таймзоной.
- `result` — всегда `Result`; `error` — payload `Err`; `entries` — список записей ledger.
- Константы — `UPPER_SNAKE` на уровне модуля: `MAX_BYTES`, `RETRY_DELAYS_SEC`,
  `SENSITIVE_FIELDS`, `DEFAULT_TEMPLATE_KEY`, `JOB_ATTEMPT`.

**Types:**

- `PascalCase`, существительные. Ошибки называются по ситуации, а не по «Error»:
  `AlreadyPaid`, `AlreadyCharged`, `AlreadyRefunded`, `IllegalTransition`,
  `OrderNotRefundable`, `InvalidTariff`, `InvalidAmount`, `FileTooLarge`,
  `ImageTooLarge`, `UnsupportedFormat`, `CorruptedImage`.
- Исключения оболочки — с суффиксом `Error` или глагольным именем, всегда с машинным
  кодом: `EngineError` и наследники (`app/engines/base.py:42-82`), `ConfigError`
  (`app/config.py:10-11`), `PipelineError` с кодом экземпляра
  (`app/worker/pipeline.py:25-30`), `PaymentFailed` (`app/payments/base.py:36-37`).
- Статусы — `StrEnum` со строчными строковыми значениями (`OrderStatus`,
  `LedgerReason`, `EngineStatus`, `PaymentStatus`, `JobStatus`).
- Дженерики — PEP 695: `class Ok[T]`, `type Result[T, E]`.

## Code Style

**Formatting:**

- `ruff format`, `line-length = 100`, `target-version = "py312"`
  (`pyproject.toml:36-40`). На 2026-11-08: `ruff format --check .` → «65 files already
  formatted».
- Двойные кавычки, висячие запятые, четыре пробела. Длинный вызов — по одному аргументу
  на строку, закрывающая скобка на своей строке (`app/db/repo.py:181-191`,
  `app/worker/pipeline.py:151-153`).
- Длинные строки пользовательских текстов склеиваются неявной конкатенацией
  (`app/bot/texts.py:13-21`).

**Linting:**

- `ruff check .` → «All checks passed!» (ruff 0.17.3, 2026-11-08).
- Набор правил (`pyproject.toml:42-50`): `E`, `F`, `I`, `UP`, `B`, `SIM`, `C4`,
  `ASYNC`, `DTZ`, `PT`. Практический смысл: `DTZ` запрещает naive `datetime`, `ASYNC` —
  блокирующие вызовы в async, `B` — мутабельные дефолты, `SIM`/`C4` — упрощения,
  `PT` — идиоматичный pytest, `UP` — современный синтаксис.
- Единственное исключение — `E501` для `app/db/migrations/versions/*.py`
  (`pyproject.toml:45-47`).
- `# noqa` и `# type: ignore` в `app/` не используются (0 совпадений).

**Python 3.12 idioms:**

- PEP 695 generics и union-алиасы (`type OrderError = ...`).
- `StrEnum`, `datetime.UTC`, `match` по вариантам `Result` и `PhotoError`.
- `asyncio.to_thread` для файловых операций (`app/storage/local.py:21`,
  `app/engines/higgsfield.py:137`, `app/worker/pipeline.py:115`).
- `X | None` вместо `Optional[X]`; `collections.abc` вместо `typing` для протоколов
  коллекций.

## Import Organization

**Order** (ruff isort, `known-first-party = ["app"]`, `pyproject.toml:49-50`):

1. stdlib: `asyncio`, `json`, `logging`, `signal`, `sys`, `dataclasses`, `datetime`,
   `enum`, `io`, `pathlib`, `shutil`, `tempfile`, `types`, `typing`,
   `collections.abc`, `decimal`.
2. third-party: `aiogram`, `httpx`, `pydantic`, `pydantic_settings`, `sqlalchemy`,
   `PIL`, `alembic`.
3. `app.*`.

- Только абсолютные импорты: относительных (`from .`) нет ни в `app/`, ни в `tests/`.
- Алиас — только при коллизии имён или для ясности:
  `from app.db.session import build_engine as build_db_engine` (`app/main_worker.py:17`),
  `from app.domain.pricing import quote as quote_price` (`app/db/repo.py:16`).
- Импортов внутри функций нет; всё на уровне модуля.

**Path Aliases:**

- Нет. First-party корень — `app`; тесты импортируют `app.*` напрямую, без
  `sys.path`-хаков и без установки пакета в editable-режиме на хосте.

## Error Handling

**Patterns:**

- В домене — `Result`, без `raise` (см. «Functional Rules»).
- На границе — типизированные исключения с машинным кодом:

  ```python
  # app/engines/base.py:42-45
  class EngineError(RuntimeError):
      """Движок не смог выдать результат; сообщение идёт в лог."""

      code = "engine_error"
  ```

  Иерархия: `EngineUnavailable`, `EngineFailed`, `EngineAuthError`, `EngineNoCredits`,
  `EngineInputRejected`, `EngineBadConfig` (`app/engines/base.py:48-82`).
  `PipelineError` хранит код экземпляра (`app/worker/pipeline.py:25-30`).
- HTTP-коды превращаются в типы в одном месте — `error_for_status`
  (`app/engines/transport.py:114-132`): 401/403 → `EngineAuthError`, 402 →
  `EngineNoCredits`, 400/422 → `EngineInputRejected`, 404 → `EngineBadConfig`,
  5xx/429 → повтор с последующим `EngineFailed`.
- Перехват на верхнем уровне задания — только два вида:

  ```python
  # app/worker/pipeline.py:50-54
  except (EngineError, PipelineError) as error:
      await fail_job(services, claim, error.code)
  except Exception:
      logger.exception("job failed unexpectedly", extra={"job_id": claim.id})
      await fail_job(services, claim, "internal")
  ```

  В цикле воркера `except Exception` логируется и слот продолжает работу
  (`app/worker/loop.py:28-41`).
- Нарушения инвариантов — ошибки программиста, а не доменные: `ValueError` при
  некорректном тарифе (`app/db/repo.py:132-133`), `LookupError` при отсутствии заказа
  (`app/db/repo.py:158-159`, `app/bot/handlers/upload.py:85-86`).
- Ошибки конфигурации — `ConfigError` с текстом для человека; процессы завершаются
  с кодом 2 (`app/config.py:10-11`, `app/main_bot.py:43-51`).
- Цепочка `raise ... from error` обязательна при переупаковке
  (`app/config.py:80`, `app/engines/transport.py:163`, `app/engines/higgsfield.py:139`).
- Терминальное состояние — не ошибка: `fail_order` молча выходит, если переход
  запрещён (`app/worker/pipeline.py:181-186`); `refund_credit` игнорирует `Err`
  (`:189-199`). Это осознанная идемпотентность, а не проглатывание.
- Голых `except:` нет.

## Logging

**Framework:** stdlib `logging` + собственный JSON-форматтер `app/obs/logs.py`;
сторонних логгеров нет.

**Patterns:**

- `logger = logging.getLogger(__name__)` в модулях оболочки, которые логируют
  (`app/worker/pipeline.py:22`, `app/worker/loop.py:12`, `app/main_worker.py:26`).
- Точка настройки — `configure_logging(level, stream)` (`app/obs/logs.py:40-46`):
  очищает корневые handlers и ставит один `StreamHandler` с `JsonLogFormatter`.
- Формат строки: `ts`, `level`, `logger`, `message`, `exception` + все поля из
  `extra` (`app/obs/logs.py:49-61`); JSON компактный, `ensure_ascii=False`
  (`:64-65`).
- В `extra` — только идентификаторы: `extra={"job_id": claim.id}`,
  `extra={"engine": settings.engine}`. Никаких фото, имён, `tg_id`, подписанных URL.
- Редакция PII: `SENSITIVE_FIELDS` (`tg_id`, `photo`, `photo_path`, `photo_url`,
  `signed_url`, `download_url`, `source_photo`, `telegram_id`) → `[redacted]`;
  вложенные словари/списки чистятся рекурсивно до `MAX_REDACTION_DEPTH = 3`, глубже —
  `[redacted]` (fail-closed) — `app/obs/logs.py:12-29,81-97`.
- `logger.exception` — для неожиданных сбоев; `logger.warning` — для восстановимых
  (не удалился файл, не ушло уведомление): `app/worker/pipeline.py:152-159,202-209`.
- `print` только для ошибки конфигурации в `sys.stderr` (`app/main_bot.py:48`,
  `app/main_worker.py:68`); пользовательские сообщения — только через `bot.send_*`
  и тексты из `app/bot/texts.py`.

## Comments

**When to Comment:**

- Каждый содержательный модуль начинается однострочным докстрингом на русском,
  описывающим ответственность (`app/domain/order_service.py:1`:
  «Стейт-машина заказа: переходы только через чистые функции»). Пустые `__init__.py`
  докстринга не имеют.
- Публичные функции ядра и сборки — однострочный докстринг, часто фиксирующий важное
  свойство: «не выполняя I/O» (`app/domain/ledger.py:78`), «лица не проверяются»
  (`app/domain/moderation.py:71`), «баланс меняется только записями»
  (`app/domain/ledger.py:1`). Тонкие CRUD-обёртки в `app/db/repo.py` (например,
  `load_user`, `create_job`) докстринга не имеют — имя и аннотации достаточны.
- Приватные помощники докстринга обычно не имеют (`_stamp`, `_has_reason`, `_attempt`).
- Инлайн-комментарии — только про неочевидные ограничения, не про «что делает код»:
  секреты исключены из `repr` (`app/engines/higgsfield.py:37`), промпт читается из файла
  рядом с видео (`app/db/seed.py:17`), серверный `now()` против переданного времени
  (`tests/test_repo_integration.py:15-17`), порядок пар в parametrize
  (`tests/test_order_service.py:56`).
- `TODO`, `FIXME`, `HACK`, `XXX` — 0 совпадений в `app/`.

**Docstrings:**

- Формат — одна строка `"""..."""` сразу под `def`, без секций `Args:`/`Returns:`:
  типы уже в аннотациях, поведение — в тексте.
- Исключения в докстрингах отдельно не перечисляются: тип виден по `raise` и
  иерархии, а текст исключения пишется для лога, не для пользователя
  (`app/engines/higgsfield.py:125`, `app/engines/transport.py:114-132`).
- Язык комментариев и докстрингов — русский; идентификаторы — английские.

## Function Design

**Size:**

| Предел (`AGENTS.md:81-87`) | Факт на 2026-11-08 |
|---|---|
| Функция 25 строк (жёстко 40) | Максимум в `app/` — 20 строк: `handle_photo` (`app/bot/handlers/upload.py:32`) и `create_overlay_image` (`app/engines/mock.py:73`); 195 функций без миграций, ни одна не превышает 25. Единственные функции >25 строк — миграции (`app/db/migrations/versions/0001_initial.py:99` — 37 строк). |
| Позиционных параметров 3 | Максимум 3 (`app/worker/pipeline.py:74,87,97`); функций с 4+ позиционными нет. |
| Уровень вложенности 2 | Максимум 2; глубже не встречается ни в одной функции (`handle_photo` `app/bot/handlers/upload.py:32`, `poll` `app/engines/higgsfield.py:97`, `request` `app/engines/transport.py:62`, `run_slot` `app/worker/loop.py:27`). |
| Модуль 300 строк | Максимум 284 — `app/db/repo.py`; далее `app/engines/higgsfield.py` (230), `app/worker/pipeline.py` (218). Всего 3316 строк в 49 модулях `app/`. |
| Без `utils`/`helpers`/`common` | Таких модулей нет. |

**Parameters:**

- Больше 3 значений — собираются в `frozen` датакласс-контекст: `Checkout`
  (`app/bot/handlers/checkout.py:25`), `PhotoUpload` (`app/bot/handlers/upload.py:21`),
  `MockRender` (`app/engines/mock.py:30`), `JobRequest` / `ConsentRecord` / `JobOutcome`
  (`app/db/repo.py:37-73`).
- Флаги и режимы — keyword-only после `*`:
  `repo.load_order(session, order_id, *, for_update=False)` (`app/db/repo.py:146-148`),
  `HttpTransport.__init__(self, *, base_url, ...)` (`app/engines/transport.py:42-52`).
- Побочные зависимости инжектируются с production-дефолтом:
  `sleep: Sleeper = asyncio.sleep` (`app/engines/transport.py:51`),
  `now: Clock = time.monotonic` (`app/engines/higgsfield.py:59`),
  `transport: httpx.AsyncBaseTransport | None = None` (`:49`).

**Return Values:**

- `Result` — если операция может отказать по доменной причине.
- Значение — если функция тотальна (`order_price` → `Price`, `calculate_balance` → `int`);
  `quote` возвращает `Result`, потому что валидирует тариф.
- `None` — «не найдено» для чтения (`load_order`, `get_active_order`), а не исключение.
- `bool` — предикаты (`is_active`, `save_photo` в `app/bot/photo.py:37`).
- `-> None` указывается явно у всех тестов и процедур.

## Module Design

**Exports:**

- `__all__` не используется (0 совпадений). Публичное имя — то, что без `_`.
- Импорт всегда из модуля-владельца: `from app.domain.result import Err, Ok, Result`,
  а не из пакета.
- `app/__init__.py`, `app/db/__init__.py`, `app/domain/__init__.py` и
  `app/obs/__init__.py` содержат только докстринг, остальные `__init__.py` пусты.
  Реэкспортов нет.

**Barrel Files:** отсутствуют — это осознанное решение, чтобы импорт показывал слой
и точный модуль.

**Constants:** константа живёт в модуле, который владеет понятием: `MAX_BYTES`,
`MAX_SIDE`, `JPEG_QUALITY` — в `app/domain/moderation.py:10-13`; `ACTIVE_STATUSES`,
`TRANSITIONS` — в `app/domain/order_service.py:70-90`; `RETRY_DELAYS_SEC`,
`RETRYABLE_STATUSES` — в `app/engines/transport.py:19-22`; пороги воркера и продаж —
в `Settings` (`app/config.py:42-49`).

## Money

- **Только целые числа.** Денежные поля имеют суффикс `_kopecks`: `price_kopecks`
  в `Order` (`app/domain/order_service.py:34`), `Template` (`app/db/models.py:65`),
  `Invoice` / `PaymentEvent` (`app/payments/base.py:23,32`). Полей `_rub`, `_rubles`,
  `price` без единицы нет.
- `float` для денег не используется: в коде он встречается только для таймаутов,
  задержек и долей (джиттер). Единственный `Decimal` — себестоимость генерации в долларах:
  `jobs.cost_usd: Numeric(12, 6)` (`app/db/models.py:117`), не цена пользователю.
- Цена считается и валидируется в домене: `quote(tariff)` отклоняет `price_kopecks <= 0`
  и `credits_cost <= 0` (`app/domain/pricing.py:47-53`), `build_order` копирует цену
  в заказ (`:56-72`). `order_price` читает заказ, а не текущий тариф (`:75-77`) —
  поэтому изменение шаблона не меняет цену уже созданного заказа
  (`tests/test_pricing.py:67-85`).
- Кредиты — отдельная целочисленная величина (`credits_cost`), не деньги. Баланс —
  сумма знаковых `delta` записей ledger (`app/domain/ledger.py:111-113`); двойное
  списание и двойной возврат отсекаются по `reason` + `order_id`
  (`AlreadyCharged` / `AlreadyRefunded`, `:77-108`).
- Форматирование для человека — единственная точка `format_price`
  (`app/bot/texts.py:58-63`): `divmod(kopecks, 100)`, «₽», без float-арифметики.
  Хендлеры и SQL деньги не считают и не форматируют.
- В БД деньги — `Integer` (`app/db/models.py:65,83`). Идемпотентность денег: уникальный
  `orders.payment_id` (`app/db/models.py:86`) и `jobs.idempotency_key` (`:111`);
  возврат — только запись в ledger, денежные возвраты не автоматизируются
  (`docs/architecture.md:194`).

## Time

- **Одна точка чтения часов:** `app/clock.py:6` — `utc_now()`.
- В домен время приходит параметром `now` (`pay`, `transition`, `fail`, `deliver`,
  `mark_refunded`); домен часов не читает.
- В оболочке «сейчас» — зависимость `now: Callable[[], datetime]`, подставляемая в
  `BotServices` / `WorkerServices`; в тестах она заменяется, а не мокается
  `datetime`.
- **Только aware-datetime:** `datetime.now(UTC)`, литералы `datetime(..., tzinfo=UTC)`.
  Naive-дат нет; за этим следит `DTZ` в ruff.
- В БД — `DateTime(timezone=True)` (`app/db/models.py:44-45,88-92,133-135`),
  `created_at` — `server_default=func.now()`, остальные метки пишет приложение из
  переданного `now`.
- Логи: `datetime.fromtimestamp(created, tz=UTC).isoformat()` (`app/obs/logs.py:68-69`).
- Интервалы и дедлайны — по монотонным часам: `time.monotonic` в движке
  (`app/engines/higgsfield.py:59,99`) и в throttle (`app/bot/middlewares/throttle.py:44`).
  Ожидание — только `asyncio.sleep`, и в движке оно инжектируется
  (`Sleeper = Callable[[float], Awaitable[None]]`, `app/engines/transport.py:27`) —
  поэтому тесты проверяют паузы без реального ожидания.
- `time.sleep` в коде отсутствует (0 совпадений); локальное время — только в текстах
  для пользователя (`openspec/project.md:74`).

---

*Convention analysis: 2026-11-08*
