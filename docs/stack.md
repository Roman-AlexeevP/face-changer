# Стек

## Принцип выбора

Стек подобран под одного разработчика и MVP на 2–3 недели. Критерий — не
«модно» и не «масштабируется на миллион», а: минимум компонентов, минимум
инфраструктуры, максимум скорости внесения изменений.

## Решения

| Слой | Выбор | Почему | Что отвергли |
|---|---|---|---|
| Язык | **Python 3.12** | вся экосистема AI/медиа здесь; async достаточен для I/O | Node/TS — второй язык ради одного бота |
| Бот | **aiogram 3.x** | асинхронный, аккуратный FSM, зрелые middleware | python-telegram-bot — тяжелее, больше магии |
| HTTP | **FastAPI + uvicorn** | нужен только вебхук и health; минимум кода | aiohttp — ручная сборка роутинга |
| БД | **PostgreSQL 16** | очередь на SKIP LOCKED, jsonb для событий, ACID для денег | SQLite — нет SKIP LOCKED и нормальной конкурентности |
| ORM | **SQLAlchemy 2.0 async + Alembic** | миграции обязательны с первого дня | raw SQL — миграции руками; Tortoise — меньше экосистема |
| Конфиг | **pydantic-settings** | типизация env, падение на старте при отсутствии секрета | os.environ — ошибки в рантайме |
| HTTP-клиент | **httpx** | async, один клиент на процесс | requests — блокирующий |
| Медиа | **ffmpeg/ffprobe** (системный) | единственный надёжный способ нормализовать видео | moviepy — тянет зависимости и память |
| Изображения | **Pillow** | перекодирование и вырезание EXIF | без перекодирования — polyglot-риск |
| Тесты | **pytest + pytest-asyncio** | стандарт | — |
| Линт | **ruff** | один инструмент вместо трёх | flake8+isort+black |
| Запуск | **docker compose** | два сервиса и БД, без k8s | k8s — избыточно |

## Чего в стеке сознательно нет

| Нет | Вместо | Когда добавить |
|---|---|---|
| Redis | БД + `SKIP LOCKED` | когда нужен распределённый rate limit |
| Celery / arq | таблица `jobs` | когда воркеров станет больше 2–3 |
| S3 | локальный диск + TTL | когда понадобится горизонтальное масштабирование |
| Prometheus / Grafana | таблица `events` + `/admin stats` | когда появятся SLO |
| Sentry | структурные логи + алерты в TG | сразу после первых платящих |
| Kubernetes | docker compose | никогда в MVP |
| Telegram WebApp | inline-кнопки | после подтверждения воронки |

## Переменные окружения

```dotenv
# Telegram
TG_BOT_TOKEN=
TG_WEBHOOK_SECRET=
TG_ADMIN_IDS=123456789            # через запятую

# База
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/facechanger

# Движок
ENGINE=mock                       # mock | higgsfield
HF_KEY_ID=
HF_KEY_SECRET=
HF_BASE_URL=https://api.higgsfield.ai
HF_MODEL=
HF_POLL_INTERVAL_SEC=3
HF_POLL_MAX_MIN=8

# Экономика и лимиты
PRICE_KOPECKS=29900
CREDITS_PER_ORDER=1
ENGINE_CREDITS_HINT=0             # ручной учёт остатка кредитов
DAILY_GENERATION_CAP=30
SALES_ENABLED=true
JOB_TIMEOUT_MIN=8
JOB_STALE_MINUTES=12

# Хранилище
STORAGE=local                     # local | s3
STORAGE_DIR=/data/tmp
STORAGE_URL_TTL_MIN=15

# Оплата
PAYMENT_PROVIDER=stub             # stub | yookassa
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=
```

## Структура репозитория

```
app/
  config.py
  main_bot.py
  main_worker.py
  db/{models,repo,session}.py
  db/migrations/
  bot/
    handlers/{start,catalog,checkout,upload,status,admin}.py
    keyboards.py
    texts.py
    middlewares/{dedupe,throttle,db_session}.py
  domain/
    {order_service,pricing,moderation}.py
  payments/{base,stub,yookassa}.py
  engines/{base,mock,higgsfield}.py
  storage/{base,local,s3}.py
  worker/{loop,pipeline,retry}.py
  api/{webhook_tg,health}.py
  obs/{logs,metrics}.py
templates/
  <key>/{source.mp4,config.yaml,preview.mp4}
tests/
docker-compose.yml
.env.example
pyproject.toml
openspec/
docs/
```

## Правила кода

- Домен (`app/domain/`) — чистые функции над неизменяемыми данными, без I/O.
  Всё недетерминированное (`now`, `new_id`, `rng`) приходит параметром.
- Ошибки домена — значения (`Result`), исключения только на границе с внешним
  миром.
- Классы с состоянием допустимы только как тонкие клиенты внешних API.
- Наследование не используется — `Protocol` и композиция.
- Никаких `time.sleep` — только `asyncio.sleep`.
- Любой внешний вызов — с таймаутом.
- Деньги — только `int` в копейках.
- Даты — только `datetime` с `tzinfo=UTC`.
- Прямая запись `order.status` запрещена — только чистая функция перехода.
- В хендлерах нет HTTP-вызовов к движку и БД-логики сложнее одного запроса.
- Лимиты: функция ≤ 25 строк, ≤ 3 позиционных аргумента, модуль ≤ 300 строк.

Полные правила и примеры — [`AGENTS.md`](../AGENTS.md).
