---
last_mapped_commit: 8cdc2abb49b272f3240a75e55c06f62b162fc586
last_mapped_at: 2026-11-08
---
<!-- refreshed: 2026-11-08 -->
# External Integrations

**Analysis Date:** 2026-11-08

## APIs & External Services

**Telegram Bot API:**
- Единственный канал общения с пользователем: приём `/start`, согласия, фото и callback-кнопок, отправка текста и видео.
  - SDK/Client: `aiogram >=3.15,<4` (`pyproject.toml:12`); отдельного SDK нет — `Bot`, `Dispatcher`, `Router` из aiogram.
  - Auth: `TG_BOT_TOKEN` (`SecretStr`), проверяется `require_bot_token` (`app/config.py:99-103`); `Bot(token=token)` создаётся в `app/main_bot.py:33` и в `app/main_worker.py:43`.
  - Транспорт: long polling — `await dispatcher.start_polling(bot)` (`app/main_bot.py:37`). Вебхук не устанавливается, `set_webhook` в коде отсутствует.
  - Адрес API: дефолт aiogram (`api.telegram.org`); переменной для своего base URL в `Settings` нет.
  - Используемые методы: `message.answer` (`app/bot/handlers/start.py`, `app/bot/handlers/upload.py`), `callback.answer` (`app/bot/handlers/start.py:49`, `app/bot/handlers/checkout.py:40`), `bot.download` в память (`app/bot/photo.py:33`), `bot.send_video` с `FSInputFile` или URL (`app/worker/pipeline.py:119-126`), `bot.send_message` при отказе (`app/worker/pipeline.py:207`).
  - Входящие апдейты: `message.photo | message.document` (`app/bot/handlers/upload.py:61`), `/start` (`app/bot/handlers/start.py:18`), callback `consent:accept` и `checkout:start` (`app/bot/keyboards.py:7-8`).
  - Идемпотентность: дедупликация по `update_id` в памяти процесса (`app/bot/middlewares/dedupe.py`), окно 2000 записей; в БД `update_id` не пишется. Троттлинг — 1 секунда на пользователя, тоже в памяти (`app/bot/middlewares/throttle.py`).
  - Админ-доступ: `TG_ADMIN_IDS` парсится в `Settings` (`app/config.py:30`, `app/config.py:61-66`), но хендлеров админки и проверки прав в коде нет — переменная не используется.

**Higgsfield (Genjutsu, генерация видео):**
- Основная внешняя зависимость: загрузка медиа, submit задания, polling статуса до терминального результата.
  - SDK/Client: собственный тонкий клиент на `httpx` — `app/engines/transport.py` (`HttpTransport`), `app/engines/higgsfield.py` (`HiggsfieldVideoEngine`), сборка в `app/engines/factory.py`.
  - Auth: HTTP-заголовок `Authorization: Key {HF_KEY_ID}:{HF_KEY_SECRET}` (`app/engines/transport.py:57`); ключи — `SecretStr` из env, при `ENGINE=higgsfield` обязательны (`require_engine_credentials`, `app/config.py:106-112`).
  - База: `HF_BASE_URL`, по умолчанию `https://api.higgsfield.ai` (`app/config.py:35`).
  - Submit: `POST {HF_BASE_URL}/{HF_MODEL}` с телом `{"input": {"video_url", "image_url", "prompt", "duration", "resolution"}}` (`submit_path` и `build_payload`, `app/engines/higgsfield.py:90-95`, `162-172`). Пустой `HF_MODEL` — `EngineBadConfig`.
  - Загрузка медиа: `POST HF_UPLOAD_URL`, multipart с полем `file`; ссылка ищется в полях `url`/`file_url`/`media_url` (`upload_media`, `extract_upload_url`, `app/engines/higgsfield.py:120-159`). Уже готовые `http(s)://`-ссылки не загружаются повторно.
  - Polling: `GET {status_url}` из ответа submit либо `{HF_BASE_URL}/requests/{request_id}` (`extract_status_url`, `app/engines/higgsfield.py:175-180`); интервал `HF_POLL_INTERVAL_SEC`, предел `HF_POLL_MAX_MIN` (`app/config.py:39-40`).
  - Статусы: `completed` → `EngineStatus.DONE` с `video.url`; `failed` → `FAILED` с кодом из `error_code`/`error.code`/`error.message`; `nsfw` → `REJECTED` с кодом `moderated`; `queued`/`in_progress`/`processing`/`pending` — промежуточные (`map_status`, `app/engines/higgsfield.py:183-194`). Четвёртый неизвестный статус подряд завершает poll кодом `unknown_status` (`app/engines/higgsfield.py:106-107`).
  - Повторы: 3 попытки на сетевые ошибки, `429` и `5xx`, паузы 2/5/15 секунд с джиттером ±20%, `Retry-After` имеет приоритет (`app/engines/transport.py:19-24`, `150-155`). `401/403`, `400/422`, `402`, `404` не повторяются и превращаются в типизированные ошибки (`error_for_status`, `app/engines/transport.py:114-132`).
  - Таймауты: `HF_TIMEOUT_SEC` (по умолчанию 30 с) применяется к httpx-клиенту целиком (`app/engines/transport.py:55-60`).
  - Кэш: URL видео шаблона хранится в памяти процесса воркера — `video_urls: dict[str, str]` в `HiggsfieldVideoEngine` (`app/engines/higgsfield.py:61`), колонки `templates.engine_video_url`/`engine_video_at` в БД не используются.
  - Состояние контракта: реальных ключей и подтверждённой схемы нет. В `.env.example` `HF_KEY_ID`, `HF_KEY_SECRET`, `HF_MODEL`, `HF_UPLOAD_URL` пусты; тесты работают на `httpx.MockTransport` (`tests/test_higgsfield_engine.py:78`). Предположения и чек-лист первого живого запроса зафиксированы в `docs/higgsfield-contract.md`.

**Платёжные провайдеры (заглушка / ЮKassa):**
- Реального приёма денег нет: `PAYMENT_PROVIDER=stub` по умолчанию (`app/config.py:55`).
  - Порт: `PaymentProvider` (`app/payments/base.py`) — `create_invoice(order)` и `refund(payment_id)`; события — `PaymentEvent` (`succeeded`/`failed`).
  - MVP-реализация: `StubPaymentProvider` (`app/payments/stub.py`) — детерминированный `payment_id = "stub-{order_id}"`, счёт сразу считается оплаченным, `refund` ничего не делает. Деньги двигаются только записями `ledger` (`topup`, `order_paid`, `refund` — `app/domain/ledger.py`).
  - ЮKassa: в конфиге только заготовка — `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` и литерал `yookassa` (`app/config.py:55-57`). HTTP-клиента, вебхука уведомлений, чеков и возвратов через API нет; `build_payment_provider` поднимает `ConfigError` для всего, кроме `stub` (`app/payments/factory.py:8-12`).
  - Привязка к заказу: `orders.payment_provider` и `orders.payment_id` (`app/bot/handlers/checkout.py:82-92`, `app/db/models.py:85-86`).

**Медиа (локально, не сетевой сервис):**
- `ffmpeg` — системный бинарник в образе (`Dockerfile:9-12`), вызывается только mock-движком: `[ffmpeg, -f lavfi, -i testsrc2..., -i overlay.png, -c:v libx264, -movflags +faststart]` (`app/engines/mock.py:95-119`). Сеть при этом не используется.
- `ffprobe` и нормализация реального результата (720p/H.264/AAC) не реализованы: `worker/pipeline.py` отправляет файл или URL движка как есть.

## Data Storage

**Databases:**
- PostgreSQL 16 — единственное хранилище состояния; контейнер `postgres` (`docker-compose.yml:4-18`), том `postgres_data`.
  - Connection: `DATABASE_URL`, формат `postgresql+asyncpg://user:pass@postgres:5432/facechanger` (дефолт в `docker-compose.yml:28`; переменная обязательна в `app/config.py:26`).
  - Client: SQLAlchemy 2.0 async + asyncpg (`app/db/session.py`: `create_async_engine(..., pool_pre_ping=True)`, `async_sessionmaker(expire_on_commit=False)`).
  - Миграции: Alembic, одна ревизия `0001_initial` (`app/db/migrations/versions/0001_initial.py`), запуск отдельной одноразовой джобой `migrate` (профиль `tools`, `docker-compose.yml:36-50`).
  - Схема (6 таблиц, `app/db/models.py`): `users` (`tg_id` unique, согласие, бан, trial), `templates` (`key`, `source_path`, промпт, цена, `engine_video_url`), `orders` (статус, цена в копейках, `payment_provider`/`payment_id`, `error_code`, метки времени), `jobs` (очередь: `status`, `idempotency_key` unique, `request_id`, `next_attempt_at`, `cost_usd`), `ledger` (записи `delta`/`reason`/`order_id`), `events` (`name` + JSONB `props`).
  - Очередь: `SELECT ... FOR UPDATE SKIP LOCKED` по `jobs.status='new' AND next_attempt_at <= now` (`app/db/repo.py:194-211`), конкурентность — `WORKER_CONCURRENCY` (`app/worker/loop.py:17`).
  - Тестовая БД: сервис `postgres-test` на порту 5433, tmpfs (`docker-compose.yml:70-85`); URL — `TEST_DATABASE_URL` (`tests/conftest.py:19-25`), схема на каждый xdist-воркер.
  - Брокера нет: ни Redis, ни Celery/arq — очередь только на таблице `jobs` (`docs/stack.md:26-32`).

**File Storage:**
- Локальный диск, `LocalStorage` (`app/storage/local.py`): каталог `STORAGE_DIR` (по умолчанию `/data/tmp`), фото — `photo-{order_id}.jpg`, результат mock-движка — временный `mock-*.mp4` в том же каталоге.
- Порт `Storage` (`app/storage/base.py`) умеет только `photo_path`, `save_photo`, `delete_photo`, `delete_file`; публичных ссылок, presigned URL и TTL нет, `STORAGE_URL_TTL_MIN` не читается.
- `STORAGE=s3` объявлен в `Settings` (`app/config.py:51`), но реализации S3 нет, а `settings.storage` нигде не читается: в `app/bot/services.py:35` и `app/main_worker.py:50` жёстко создаётся `LocalStorage(settings.storage_dir)`.
- В `docker-compose.yml` у `bot`/`worker` нет тома под `/data/tmp` — медиа живут в слое контейнера и теряются при пересоздании.
- Удаление: фото удаляется после доставки или провала (`app/worker/pipeline.py:151-159`), результат mock-движка — тоже; исходники шаблонов (`templates/default/source.mp4`) в репозитории отсутствуют — каталог `templates/` не создан, путь захардкожен в `app/db/seed.py:13`.

**Caching:**
- Redis отсутствует. Кеши только в памяти процесса: `video_urls` в `HiggsfieldVideoEngine` (`app/engines/higgsfield.py:61`), `update_id` в `DedupeMiddleware`, `user_id → monotonic` в `ThrottleMiddleware`.
- Состояние в памяти не разделяется между `bot` и `worker` и теряется при рестарте.

## Authentication & Identity

**Auth Provider:**
- Собственной аутентификации нет; идентичность — Telegram-пользователь: `message.from_user.id` → `users.tg_id` (unique) через `repo.get_or_create_user` (`app/db/repo.py:90-97`).
- Согласие на обработку фото: версия `CONSENT_VERSION = "v1"` и `consent_at` в `users` (`app/bot/handlers/start.py:12`, `repo.record_consent`).
- Админ-авторизации нет: `TG_ADMIN_IDS` объявлен, но ни один хендлер его не проверяет.
- Межсервисной аутентификации нет: `bot` и `worker` общаются только через PostgreSQL.
- Внешняя аутентификация — только ключи Higgsfield (`Authorization: Key ...`) и токен Telegram-бота; секреты хранятся в `.env` (в git не попадает, `.gitignore`).

## Monitoring & Observability

**Error Tracking:**
- Sentry и аналоги отсутствуют. Ошибки пайплайна логируются `logger.exception` и превращаются в `jobs.error_code`/`orders.error_code` (`app/worker/pipeline.py:50-54`, `162-178`).

**Logs:**
- Структурный JSON в stdout через `logging` и `JsonLogFormatter` (`app/obs/logs.py`): поля `ts`, `level`, `logger`, `message`, `exception` + `extra`.
- Редакция PII: набор `SENSITIVE_FIELDS` (`tg_id`, `telegram_id`, `photo`, `photo_path`, `photo_url`, `source_photo`, `signed_url`, `download_url`) заменяется на `[redacted]` (`app/obs/logs.py:12-23`, `app/obs/logs.py:81-97`).
- Уровень — `LOG_LEVEL` (`app/config.py:59`), настраивается `configure_logging` в обеих точках входа.
- Метрик нет: модуль `app/obs/metrics.py` из `docs/stack.md:99` не создан. Продуктовая аналитика — таблица `events` (`order_created`, `order_paid`, `photo_accepted`, `order_delivered`, `job_failed`, `refund_issued`, `consent_given` — `app/bot/handlers/*.py`, `app/worker/pipeline.py`).
- Алерты админу в Telegram описаны в `docs/architecture.md:236` и `openspec/changes/mvp-001-core-flow/specs/ops/spec.md`, но в коде не реализованы: исходящих сообщений админу нет.
- Health-эндпоинта нет: `/health` упомянут в спецификации `ops`, HTTP-сервер в проекте отсутствует.

## CI/CD & Deployment

**Hosting:**
- Самостоятельный запуск через `docker compose` на одном хосте: сервисы `postgres`, `bot`, `worker` (`docker-compose.yml`). Облачная платформа, реестр образов и манифесты развёртывания не заданы.
- Внешний HTTPS-прокси (Caddy/nginx) описан как требование для вебхука (`docs/architecture.md:247`), конфигурации в репозитории нет.

**CI Pipeline:**
- CI отсутствует: нет `.github/workflows`, `.gitlab-ci.yml` и других конфигураций.
- Сборка/тесты/миграции — вручную: `tasks.ps1` (`up`, `down`, `migrate`, `test`, `lint`, `fmt`, `psql`, `ps`, `clean`) или напрямую `docker compose` (`README.md:61-67`).
- Образы: `Dockerfile` stage `runtime` (бот/воркер/миграции) и `test` (pytest + отчёт в `reports/`, том монтируется в `docker-compose.yml:101-105`).

## Environment Configuration

**Required env vars:**
- `DATABASE_URL` — обязательна всегда (`app/config.py:26`).
- `TG_BOT_TOKEN` — обязательна на старте и `bot`, и `worker` (`require_bot_token`).
- `ENGINE` — `mock` | `higgsfield` (дефолт `mock`); для `higgsfield` обязательны `HF_KEY_ID`, `HF_KEY_SECRET`.
- `HF_BASE_URL`, `HF_MODEL`, `HF_UPLOAD_URL`, `HF_TIMEOUT_SEC`, `HF_POLL_INTERVAL_SEC`, `HF_POLL_MAX_MIN` — настройки движка.
- `PAYMENT_PROVIDER` — `stub` | `yookassa` (дефолт `stub`; `yookassa` пока приводит к `ConfigError`).
- `PRICE_KOPECKS`, `CREDITS_PER_ORDER`, `SALES_ENABLED`, `WORKER_CONCURRENCY` — экономика и лимиты.
- `STORAGE`, `STORAGE_DIR`, `STORAGE_URL_TTL_MIN` — хранилище (реально используется только `STORAGE_DIR`).
- `LOG_LEVEL` — уровень логов.
- Полный каталог с комментариями — `.env.example`; те же имена и дефолты продублированы в `docs/stack.md:40-76`.

**Secrets location:**
- Только `.env` в корне (файл присутствует локально, исключён `.gitignore` и `.dockerignore`); `.env.example` — шаблон без значений.
- `docker-compose.yml` подключает `.env` через `env_file` с `required: false`.
- Пароли PostgreSQL в compose имеют dev-дефолты `user`/`pass` (`docker-compose.yml:7-9`), тестовая база — те же значения (`docker-compose.yml:74-76`).

## Webhooks & Callbacks

**Incoming:**
- Нет. HTTP-сервер не запускается: `fastapi`/`uvicorn` объявлены в `pyproject.toml`, но не импортируются; пакета `app/api/` и эндпоинтов нет. `TG_WEBHOOK_SECRET` объявлен в `Settings` (`app/config.py:29`), но не читается.
- Обновления Telegram приходят long polling'ом (`app/main_bot.py:37`), события Higgsfield — опросом (`GET status_url`), события оплаты — синхронным ответом заглушки: `StubPaymentProvider.create_invoice` сразу возвращает `Invoice` с `PaymentEvent(SUCCEEDED)` (`app/payments/stub.py:15-23`).
- Платёжные коллбэки не принимаются: ни эндпоинта уведомлений, ни проверки подписи/секрета платежа нет.

**Outgoing:**
- Исходящих вебхуков нет. Внешние вызовы: Telegram Bot API (aiogram), Higgsfield (`httpx`), локальный `ffmpeg` (subprocess).

---

*Integration audit: 2026-11-08*
