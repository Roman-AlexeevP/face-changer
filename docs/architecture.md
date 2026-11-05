# Архитектура

Версия документа: MVP-1. Область: Telegram-бот «лицо в видео-шаблон».

## 1. Контекст

```
Пользователь (Telegram)
        │  фото
        ▼
   ┌─────────┐   заказ    ┌────────────┐  submit/poll  ┌──────────────┐
   │   Bot   │ ─────────► │ PostgreSQL │ ◄──────────── │    Worker    │
   └─────────┘            └────────────┘               └──────┬───────┘
        ▲                                                     │
        │  sendVideo                                          ▼
        └───────────────────────────────────────────  Higgsfield API
                                                      (Genjutsu)
```

Два процесса (`bot`, `worker`), одна кодовая база, одна БД. Обмен — только
через таблицы. Никаких брокеров сообщений.

**Почему так:** на MVP ожидаемая нагрузка — единицы заказов в час. Очередь на
`SELECT ... FOR UPDATE SKIP LOCKED` держит десятки задач в минуту и не требует
ни Redis, ни Celery. Добавление брокера — это отдельное изменение, когда
появится реальная потребность в горизонтальном масштабировании воркеров.

## 2. Компоненты

| Компонент | Ответственность | Не делает |
|---|---|---|
| `bot/middlewares` | дедуп `update_id`, троттлинг, сессия БД | бизнес-логику |
| `bot/handlers` | диалог, тексты, клавиатуры | прямые запросы к движку |
| `domain/order_service` | стейт-машина заказа, возвраты | знание про Telegram |
| `domain/moderation` | валидация фото, «одно лицо» | хранение файлов |
| `payments/*` | создание инвойса, обработка события оплаты | выдачу результата |
| `engines/*` | submit / poll, маппинг ошибок движка | ретраи (это `worker/retry`) |
| `storage/*` | временное хранение файлов, presigned URL | публичный доступ |
| `worker/pipeline` | оркестрация одного заказа | UI-тексты |
| `worker/retry` | политика повторов, таймауты | знание о конкретном движке |
| `api/webhook_*` | приём внешних событий | тяжёлую работу |
| `obs/*` | логи, метрики, редакция PII | бизнес-логику |

## 3. Потоки

### 3.1. Основной путь

```
1  /start                → запись users, показ согласия
2  согласие              → users.consent_version, users.consent_at
3  «Начать»              → создаётся order(status=created), берётся default template
4  оплата (stub)         → order.status=paid, ledger(+1 кредит)
5  фото                  → валидация → storage → order.status=queued + job(status=new)
6  worker: pick          → job.status=running
7  ensure_asset          → templates.engine_video_url (кэш)
8  upload фото           → storage/движок возвращает URL
9  submit                → job.request_id, job.status=submitted
10 poll (2s → 10s)       → до терминального статуса или таймаута
11 download              → storage (tmp)
12 normalize             → ffmpeg 720p H.264, ≤20 МБ
13 sendVideo             → order.status=delivered, job.status=done
14 cleanup               → удалить фото и tmp-файлы
```

### 3.2. Путь отказа

```
любой шаг 5–14 → job.status=failed
              → retry по политике (см. §7), если попытки не исчерпаны
              → иначе order.status=failed → возврат кредита в ledger
              → сообщение пользователю с причиной
              → алерт админу, если причина инфраструктурная
```

## 4. Контракты

```python
# engines/base.py
class EngineStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    REJECTED = "rejected"      # модерация движка
    NO_CREDITS = "no_credits"

@dataclass(frozen=True)
class JobSpec:
    template_key: str
    video_url: str
    photo_url: str
    prompt: str
    duration_sec: int
    resolution: str
    idempotency_key: str        # f"{order_id}:{attempt}"

@dataclass(frozen=True)
class EngineResult:
    status: EngineStatus
    result_url: str | None
    error_code: str | None
    raw: dict | None

class VideoEngine(Protocol):
    async def ensure_asset(self, local_path: Path) -> str: ...
    async def submit(self, spec: JobSpec) -> str: ...
    async def poll(self, request_id: str) -> EngineResult: ...
    async def cancel(self, request_id: str) -> None: ...
```

```python
# payments/base.py
class PaymentProvider(Protocol):
    async def create_invoice(self, order: Order) -> str: ...
    async def handle_update(self, payload: dict) -> PaymentEvent | None: ...
    async def refund(self, payment_id: str) -> None: ...
```

Требование: **любая реализация движка обязана возвращать `NO_CREDITS` как
отдельный статус**, а не как общую ошибку. На нём держится гейт продаж (§8).

## 5. Данные

```
users      id, tg_id UNIQUE, created_at, is_banned,
           consent_version, consent_at, trial_used
templates  id, key UNIQUE, title, source_path, prompt, engine_model,
           duration_sec, resolution, credits_cost, price_kopecks,
           is_active, engine_video_url, engine_video_at
orders     id, user_id → users, template_id → templates, status,
           price_kopecks, credits_cost, payment_provider, payment_id UNIQUE,
           error_code, created_at, paid_at, delivered_at
jobs       id, order_id → orders, attempt, engine, request_id,
           status, idempotency_key UNIQUE, next_attempt_at,
           submitted_at, finished_at, cost_usd, error_code
ledger     id, user_id, delta, reason, order_id, created_at
events     id, user_id NULL, name, props jsonb, created_at
```

Индексы: `orders(status)`, `jobs(status, submitted_at)`,
`jobs(request_id)`, `events(name, created_at)`.

### Стейт-машина заказа

```
 created ──► paid ──► queued ──► running ──► delivered ──► purged
               │        │          │
               └────────┴──────────┴──► failed ──► refunded
```

Разрешённые переходы описаны в `order_service.TRANSITIONS`. Любой другой
переход — исключение и запись в лог уровня `error`.

### Стейт-машина задания

```
new ──► submitted ──► polling ──► done
         │             │
         └─────────────┴──► failed        (retry, если attempt < max)
                        └──► rejected      (без retry)
                        └──► no_credits    (без retry, стоп продаж)
```

## 6. Очередь

```sql
SELECT id FROM jobs
 WHERE status = 'new'
   AND next_attempt_at <= now()
 ORDER BY id
   FOR UPDATE SKIP LOCKED
 LIMIT 1;
```

Воркер берёт задачу, ставит `status='running'` в той же транзакции, затем
работает. При падении процесса задача остаётся в `running` — отдельный
«сторож» (часть `worker/loop`) возвращает в `new` задачи, висящие в `running`
дольше `JOB_STALE_MINUTES`.

## 7. Политика отказов

| Событие | Retry | Возврат кредита | Действие |
|---|---|---|---|
| Ошибка сети при submit | да, 3×, backoff 2/5/15 с | нет | — |
| `5xx` движка | да, 3× | нет | алерт при исчерпании |
| `failed` от движка | да, 1× | если исчерпано | сообщение юзеру |
| `rejected` (модерация) | нет | да | сообщение юзеру |
| `no_credits` (402) | нет | да | **стоп продаж** + алерт |
| Таймаут > 8 мин | нет | да | алерт |
| Нет 1 лица на фото | нет | — | отказ до оплаты |
| Видео > 20 МБ | — | — | перекодирование |
| Telegram 429 | да, по `retry_after` | нет | — |

Правило: **возврат кредита — единственный способ компенсации в MVP.**
Денежные возвраты не автоматизируются.

## 8. Гейты и предохранители

1. **Гейт кредитов.** Перед созданием заказа проверяется
   `engine_credits_available >= template.credits_cost`. Источник значения в
   MVP — `settings.engine_credits_hint`, обновляемый админом вручную.

   Важно не путать два разных баланса: **кредиты пользователя** (сколько
   генераций он оплатил — считается по `ledger`) и **кредиты движка**
   (сколько осталось на счёте Higgsfield — вводится вручную). Гейт работает
   по второму.
2. **Один активный заказ на пользователя** (`orders` в статусах
   `paid/queued/running`).
3. **Дневной лимит генераций** (`settings.daily_generation_cap`).
4. **Kill switch** `SALES_ENABLED=false` — бот отвечает «техработы».
5. **Таймаут задачи** `JOB_TIMEOUT_MIN=8`. Пользователю обещается «обычно
   1–3 минуты, максимум 7» — таймаут выбран с запасом на одну минуту, чтобы
   не сообщать о неудаче раньше, чем движок успел бы ответить.

## 9. Безопасность

- Фото: принимается только `image/*`, перекодируется через Pillow (убивает
  polyglot-файлы), EXIF вырезается, лимит 20 МБ и 4096 px по стороне.
- Файлы доступны только по presigned URL с TTL 15 минут; бакет/каталог не
  публичный.
- Логи: `tg_id` хешируется в `user_ref`, содержимое файлов и URL с подписью
  не логируются.
- Секреты — только env. Ключ движка доступен только процессу `worker`, боту
  он не передаётся.
- Вебхук Telegram — `secret_token` + проверка заголовка.
- Админ-команды — whitelist `tg_id`, все действия пишутся в `events`.

## 10. Наблюдаемость

Минимум, без внешних систем:

- структурные логи (JSON) в stdout;
- счётчики в `events`: `order_created`, `order_paid`, `job_submitted`,
  `job_done`, `job_failed`, `refund_issued`;
- `/admin stats` — заказы за 24 ч, успешность, среднее время, расход кредитов;
- алерты в личный чат админа: `no_credits`, `job_stale`, `error_rate > 20%`.

## 11. Деплой

```
docker compose
  ├── postgres:16
  ├── bot      (python -m app.main_bot)
  └── worker   (python -m app.main_worker)
```

Внешний HTTPS — Caddy/nginx перед `bot` (нужен для вебхука Telegram).
Секреты — `.env`, в репозиторий не попадает.

## 12. Эволюция

| Когда | Что добавляется | Что не меняется |
|---|---|---|
| Каталог шаблонов | UI выбора, `templates` уже есть | контракты движка |
| Реальная оплата | `payments/yookassa.py` | контракт платежа |
| Рост нагрузки | отдельный воркер-пул, затем брокер | таблица `jobs` |
| WebApp | отдельный фронт, тот же API | домен и БД |
| Второй движок | `engines/backup.py` + флаг | `VideoEngine` |
