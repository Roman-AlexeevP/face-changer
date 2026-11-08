---
last_mapped_commit: 8cdc2abb49b272f3240a75e55c06f62b162fc586
last_mapped_at: 2026-11-08
---
<!-- refreshed: 2026-11-08 -->
# Technology Stack

**Analysis Date:** 2026-11-08

## Languages

**Primary:**
- Python 3.12 — весь код в `app/` и `tests/`. Версия задана тремя местами: `requires-python = ">=3.12"` в `pyproject.toml`, `target-version = "py312"` в `[tool.ruff]`, базовый образ `python:3.12-slim` в `Dockerfile`. В коде используются `StrEnum` (`app/engines/base.py:8`, `app/domain/order_service.py:12`) и `type X = ...` (PEP 695, `app/bot/photo.py:12`, `app/domain/moderation.py:63`), поэтому 3.12 — нижняя граница, а не пожелание.
- SQL — только через SQLAlchemy и Alembic; отдельных `.sql`-файлов нет. DDL одной ревизии: `app/db/migrations/versions/0001_initial.py`.

**Secondary:**
- PowerShell 5.1 — `tasks.ps1` (`#Requires -Version 5.1`), обёртка над `docker compose`; `tasks.cmd` — шим для запуска в обход ExecutionPolicy.
- YAML — `docker-compose.yml` (сервисы, профили, healthcheck).
- Dockerfile-инструкции — `Dockerfile` (multi-stage: `base`, `runtime`, `test`).
- TOML — `pyproject.toml` (зависимости, ruff, pytest, coverage).

## Runtime

**Environment:**
- Python 3.12 в Debian-slim: `FROM python:3.12-slim AS base` (`Dockerfile:1`).
- asyncio, два независимых процесса: `python -m app.main_bot` (точка сборки `app/main_bot.py`) и `python -m app.main_worker` (`app/main_worker.py`), оба описаны в `docker-compose.yml` (`bot` — строка 32, `worker` — строка 67).
- Модель конкурентности: один event loop на процесс; бот — `Dispatcher.start_polling`, воркер — пул из `WORKER_CONCURRENCY` asyncio-задач, каждая берёт по одному job (`app/worker/loop.py:15-25`). Потоки не используются, блокирующий I/O выносится через `asyncio.to_thread` (`app/engines/higgsfield.py:137`, `app/storage/local.py:21-28`).
- Системный `ffmpeg` устанавливается в образ (`Dockerfile:9-12`) и вызывается через `asyncio.create_subprocess_exec` в `app/engines/mock.py`. `ffprobe` и нормализация результата (720p, H.264, AAC, faststart) в коде не реализованы — комментарий в `Dockerfile:9` описывает цель, а не текущее поведение.
- PostgreSQL 16 — контейнер `postgres` (`docker-compose.yml:4-18`); тестовая база — `postgres-test` на tmpfs с портом 5433 (`docker-compose.yml:70-85`).

**Package Manager:**
- `pip` внутри образа: `pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" .` (`Dockerfile:19`); dev-зависимости — `pip install ... -e ".[dev]"` (`Dockerfile:32`).
- Метаданные проекта и зависимости — `pyproject.toml`, backend `setuptools.build_meta` (`pyproject.toml:1-3`), пакеты `app*` (`pyproject.toml:33-34`).
- Lockfile: отсутствует. Нет `uv.lock`, `poetry.lock`, `requirements.txt`; версии заданы диапазонами в `pyproject.toml`, поэтому сборка не воспроизводится побитово — обновление в пределах диапазона меняет содержимое образа.
- Зеркало PyPI настраивается build-arg `PIP_INDEX_URL` (`Dockerfile:18`, `Dockerfile:29`), по умолчанию `https://pypi.org/simple`.
- В рабочей копии присутствуют `.venv` и `.uv-cache` (следы локального `uv`), но ни `tasks.ps1`, ни `Dockerfile` uv не вызывают.

## Frameworks

**Core:**
- aiogram `>=3.15,<4` — Telegram Bot API: `Bot`, `Dispatcher`, `Router`, `BaseMiddleware`, `FSInputFile` (`app/main_bot.py`, `app/bot/handlers/*.py`, `app/worker/pipeline.py`). FSM не используется: диалог построен на inline-кнопках и состоянии заказа в БД.
- SQLAlchemy `[asyncio] >=2.0.36,<3` + asyncpg `>=0.30,<1` — `create_async_engine`, `async_sessionmaker`, `Mapped`/`mapped_column` (`app/db/session.py`, `app/db/models.py`).
- Alembic `>=1.14,<2` — миграции, URL берётся из настроек, а не из ini (`app/db/migrations/env.py:22-26`).
- pydantic-settings `>=2.4,<3` — типизированные настройки из env (`app/config.py`).
- httpx `>=0.27,<1` — единственный HTTP-клиент, только для движка Higgsfield (`app/engines/transport.py`).
- Pillow `>=11,<12` — валидация и перекодирование фото (`app/domain/moderation.py`) и отрисовка оверлея MOCK (`app/engines/mock.py`).

**Testing:**
- pytest `>=8.3,<9`, pytest-asyncio `>=0.24,<1`, pytest-cov `>=5,<7`, pytest-html `>=4.1,<5`, pytest-xdist `>=3.6,<4` — секция `dev` в `pyproject.toml:23-31`.
- Конфигурация pytest — `pyproject.toml:52-59`: `testpaths = ["tests"]`, `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "session"`, `addopts = "-ra"`, маркер `integration` (требует `TEST_DATABASE_URL`).
- Запуск в контейнере: сервис `tests` (`docker-compose.yml:87-115`) выполняет `pytest -q -n auto --cov=app --cov-report=html:reports/coverage --html=reports/report.html --self-contained-html`.

**Build/Dev:**
- Docker multi-stage: `base` → `runtime` (CMD `python -m app.main_bot`) и `test` (CMD pytest с HTML-отчётом) — `Dockerfile:22-35`.
- docker compose профили: `tools` (одноразовый `migrate`), `test` (`postgres-test`, `tests`) — `docker-compose.yml:37`, `docker-compose.yml:71`, `docker-compose.yml:88`.
- ruff `>=0.8,<1` — линт и формат: `line-length = 100`, `select = ["E","F","I","UP","B","SIM","C4","ASYNC","DTZ","PT"]`, `known-first-party = ["app"]`, исключение `E501` для миграций (`pyproject.toml:36-50`).
- Обёртки задач: `tasks.ps1` (`up`, `down`, `logs`, `migrate`, `test`, `lint`, `fmt`, `psql`, `ps`, `clean`) и `tasks.cmd`.
- Статической проверки типов нет: `mypy`/`pyright` не объявлены и не настроены; контроль качества — ruff и тесты.
- Метаданные пакета: `name = "face-changer"`, `version = "0.1.0"`, README подключается как `readme` (`pyproject.toml:5-10`).
- Покрытие: `source = ["app"]`, `branch = true`, миграции исключены (`pyproject.toml:61-71`).

## Key Dependencies

**Critical:**
- `aiogram >=3.15,<4` — весь пользовательский вход и доставка видео; без него нет ни бота, ни воркера (воркер тоже создаёт `Bot` для `send_video`/`send_message`).
- `sqlalchemy[asyncio] >=2.0.36,<3` + `asyncpg >=0.30,<1` — хранение заказов, ledger, events и очередь заданий на `SELECT ... FOR UPDATE SKIP LOCKED` (`app/db/repo.py:194-211`).
- `httpx >=0.27,<1` — транспорт Higgsfield: авторизация, таймауты, повторы (`app/engines/transport.py`).
- `pydantic-settings >=2.4,<3` — падение на старте при отсутствии `DATABASE_URL`/`TG_BOT_TOKEN` вместо ошибки в рантайме (`app/config.py:76-116`).
- `Pillow >=11,<12` — приём фото: лимит 20 МБ, сторона ≤ 4096 px, форматы JPEG/PNG/WEBP, перекодирование в JPEG без EXIF (`app/domain/moderation.py`).
- `alembic >=1.14,<2` — единственная ревизия `0001_initial` создаёт 6 таблиц (`app/db/migrations/versions/0001_initial.py`).

**Infrastructure:**
- `fastapi >=0.115,<1` и `uvicorn[standard] >=0.32,<1` объявлены в `pyproject.toml:15,20`, но импортов `fastapi`/`uvicorn` нет ни в `app/`, ни в `tests/`; HTTP-сервера и пакета `app/api/` в репозитории нет.
- `ffmpeg` (apt-пакет) — единственный внешний бинарник; нужен mock-движку (`app/engines/mock.py:47-50` возвращает `EngineUnavailable`, если бинарника нет в PATH).
- `pytest-html`/`pytest-cov`/`pytest-xdist` — отчёты и параллельный прогон в контейнере.
- Node.js/JS-зависимостей нет: `node_modules/` и `.npm-cache/` только в `.gitignore`.

## Configuration

**Environment:**
- Единственный механизм — `pydantic-settings`: `Settings` в `app/config.py:14-73`, `SettingsConfigDict(env_file=".env", env_ignore_empty=True, case_sensitive=False, extra="ignore", frozen=True)`.
- Секреты — `SecretStr` (`TG_BOT_TOKEN`, `TG_WEBHOOK_SECRET`, `HF_KEY_ID`, `HF_KEY_SECRET`, `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`); в `HiggsfieldConfig` поля ключей помечены `repr=False` (`app/engines/higgsfield.py:38-39`).
- Ошибки конфигурации — `ConfigError` с человекочитаемым текстом (`describe_settings_error`), процессы завершаются с кодом 2 (`app/main_bot.py:43-51`, `app/main_worker.py:61-71`).
- Обязательные переменные: `DATABASE_URL` (`app/config.py:26`), `TG_BOT_TOKEN` на старте обоих процессов (`require_bot_token`), для `ENGINE=higgsfield` — `HF_KEY_ID` и `HF_KEY_SECRET` (`require_engine_credentials`, `app/config.py:106-112`).
- Каталог переменных с комментариями: `.env.example` (43 строки). Реальный `.env` в рабочей копии присутствует и в git не попадает (`.gitignore`).
- Объявлены, но не читаются кодом: `TG_ADMIN_IDS` (парсится валидатором, но хендлеров админки нет), `ENGINE_CREDITS_HINT`, `DAILY_GENERATION_CAP`, `JOB_TIMEOUT_MIN`, `JOB_STALE_MINUTES`, `STORAGE`, `STORAGE_URL_TTL_MIN`, `TG_WEBHOOK_SECRET`. Дефолты в `Settings` повторяют значения `.env.example`, кроме `TG_ADMIN_IDS` (в примере подставлен числовой id).

**Build:**
- `Dockerfile` — установка ffmpeg, копирование `pyproject.toml`/`README.md`/`alembic.ini`/`app`, установка пакета, два целевых stage.
- `docker-compose.yml` — сервисы `postgres`, `bot`, `worker`, профили `tools`/`test`, `env_file: .env` с `required: false`, healthcheck `pg_isready`, `stop_grace_period: 30s` у воркера.
- `alembic.ini` — `script_location = %(here)s/app/db/migrations`, URL базы задаётся через `DATABASE_URL` в `app/db/migrations/env.py`.
- `.dockerignore` исключает `.env`, `.env.*`, `data`, `tmp`, `docs`, `openspec`, кеши и `reports`.

## Platform Requirements

**Development:**
- Хост разработчика — Windows/PowerShell: `tasks.ps1` требует PowerShell 5.1, `tasks.cmd` — cmd-шим на случай запрета `.ps1`; Docker обязателен, хостовые Python, ffmpeg и make не требуются (`tasks.ps1:4-9`, `README.md:34`).
- Тесты требуют PostgreSQL: `TEST_DATABASE_URL` или дефолт `postgresql+asyncpg://user:pass@localhost:5433/facechanger_test` (`tests/conftest.py:19-25`); если база недоступна, фикстура `db_schema` пропускает зависящие от неё тесты.
- Каждый xdist-воркер работает в своей схеме `test_<worker>` (`tests/conftest.py:20-33`).

**Production:**
- Целевая среда — Linux-контейнеры через `docker compose`: `postgres`, `bot`, `worker` (`docs/stack.md:24`, `README.md:63-67`).
- Внешний HTTPS-прокси (Caddy/nginx) упомянут в `docs/architecture.md:247` как необходимость для вебхука Telegram, но в репозитории его конфигурации нет; бот работает long polling.
- Тома: `postgres_data` для БД (`docker-compose.yml:117-118`); каталог `/data/tmp` для медиа задаётся `STORAGE_DIR` и отдельным томом не описан.
- CI-конфигурации в репозитории нет: ни `.github/workflows`, ни GitLab CI. Сборка и тесты запускаются вручную через `tasks.ps1`/`tasks.cmd`.

---

*Stack analysis: 2026-11-08*
