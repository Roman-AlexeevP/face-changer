---
last_mapped_commit: 8cdc2abb49b272f3240a75e55c06f62b162fc586
last_mapped_at: 2026-11-08
---
# Codebase Concerns

**Analysis Date:** 2026-11-08

Срез на момент анализа: реализованы блоки 1–2 плана (каркас, домен), блок 5
(Higgsfield-движок на фикстурах), блок 9 частично (тестовая инфраструктура);
бот и воркер собраны и работают на `ENGINE=mock`, но деньги-критичный путь
(`app/worker/pipeline.py`) не покрыт тестами, а отказоустойчивость из
`docs/architecture.md` §7–8 (ретраи, сторож, гейты) не реализована.

## Tech Debt

**Пайплайн воркера без ретраев и без политики отказов:**
- Issue: любая ошибка движка сразу терминальна. `process_job` ловит
  `EngineError`/`PipelineError` и зовёт `fail_job`, не различая сеть, `5xx`,
  `failed` и таймаут.
- Files: `app/worker/pipeline.py:41-54`, `app/worker/pipeline.py:162-165`,
  `app/worker/pipeline.py:168-178`
- Impact: расхождение с `docs/architecture.md` §7 (таблица отказов: сеть/`5xx`
  — 3×, `failed` — 1×) и `docs/implementation-plan.md:109`. Один сетевой сбой
  Higgsfield стоит пользователю заказа и возврата кредита. `jobs.attempt`
  всегда `1` (`app/bot/handlers/upload.py:18`), поэтому повторить задание
  нельзя и по данным.
- Fix approach: отдельный `worker/retry.py` (его нет, хотя он описан в
  `docs/architecture.md:40`, `docs/higgsfield-contract.md:97`): классификация
  `EngineError.code` → `retryable`, backoff `2/5/15` с, инкремент `attempt` и
  новый `idempotency_key` при перепостановке (`app/db/repo.py:181-191`).

**Ключ идемпотентности не передаётся движку:**
- Issue: `JobSpec.idempotency_key` собирается (`app/worker/pipeline.py:83`), но
  `build_payload` кладёт в тело только `video_url/image_url/prompt/duration/
  resolution`.
- Files: `app/engines/higgsfield.py:162-172`, `app/engines/base.py:29`,
  `openspec/changes/mvp-001-core-flow/specs/generation/spec.md:12-22`
- Impact: требование «повторный submit не создаёт вторую генерацию» не
  выполнено на уровне контракта. После любого рестарта между submit и
  получением `request_id` возможна вторая генерация и второй расход кредитов.
- Fix approach: передавать ключ в `input` (или заголовком, если так поддерживает
  API) и проверить на живом запросе; до этого — не ретраить submit.

**`jobs.request_id` и `jobs.cost_usd` никогда не пишутся:**
- Issue: движок возвращает `request_id` (`app/engines/higgsfield.py:81-88`), но
  он живёт только в памяти вызова `generate`; в БД попадает только
  `error_code`.
- Files: `app/db/models.py:99-118`, `app/db/repo.py:194-221`,
  `app/worker/pipeline.py:87-90`
- Impact: нет способа возобновить polling после падения воркера, отменить
  запрос или посчитать стоимость. Требование
  `specs/generation/spec.md:16-18` (продолжить polling при наличии
  `request_id`) невыполнимо на текущих данных. `cost_usd` не заполняется —
  расход кредитов не учитывается.
- Fix approach: `repo.mark_submitted(session, job_id, request_id)` сразу после
  `submit`; `resume`-ветка в пайплайне — по сохранённому `request_id`.

**Мёртвые колонки и мёртвые настройки:**
- Issue: `templates.engine_video_url`/`engine_video_at`, `templates.engine_model`,
  `jobs.cost_usd`, `users.trial_used`, `users.is_banned` не читаются и не
  пишутся нигде. `engine_credits_hint`, `daily_generation_cap`,
  `job_timeout_min`, `job_stale_minutes`, `storage_url_ttl_min`,
  `tg_admin_ids`, `tg_webhook_secret` объявлены, но не используются.
- Files: `app/db/models.py:61-68`, `app/db/models.py:117`, `app/config.py:44-53`,
  `app/config.py:29-30`
- Impact: настройки создают ложное впечатление работающих предохранителей:
  `JOB_TIMEOUT_MIN` и `JOB_STALE_MINUTES` не влияют ни на что, гейт кредитов и
  дневной лимит отсутствуют. Кэш URL видео шаблона живёт в памяти
  (`app/engines/higgsfield.py:61,72-79`), а не в `templates.engine_video_url`,
  как обещает `docs/architecture.md:55` и `docs/higgsfield-contract.md:34-37`.
- Fix approach: либо реализовать потребителей (блок 7), либо удалить поля из
  конфига, чтобы конфиг не врал. Для кэша шаблона — писать
  `engine_video_url`/`engine_video_at` и проверять TTL.

**Настройка `STORAGE` игнорируется:**
- Issue: `Settings.storage` допускает `s3`, но обе точки сборки жёстко создают
  `LocalStorage`.
- Files: `app/config.py:51-53`, `app/bot/services.py:35`,
  `app/main_worker.py:50`
- Impact: `STORAGE=s3` молча даёт локальный диск; при переезде на общий том
  поведение не изменится и ошибка не проявится.
- Fix approach: `storage/factory.py` по образцу `engines/factory.py` и явный
  `ConfigError` для нереализованного значения.

**Ручной маппинг строки заказа в домен:**
- Issue: `save_order` перечисляет поля руками; `to_order` — тоже.
- Files: `app/db/repo.py:156-166`, `app/db/repo.py:259-274`
- Impact: новое поле домена (например, `rerolls` из блока 6.5) молча не
  сохранится; тест этого не поймает.
- Fix approach: тест «все поля `Order` записываются/читаются» через
  `dataclasses.fields` либо `session.merge` по явной таблице соответствий.

**Коды ошибок не совпадают с обещанной таксономией:**
- Issue: спецификация требует коды `timeout`, `moderated`, `no_credits`,
  `engine_5xx`, `network`, `bad_input`, `unknown`
  (`specs/generation/spec.md:69-77`). Фактически в БД попадают либо коды
  исключений (`engine_auth`, `engine_bad_config`, `no_credits`), либо код
  провайдера из ответа (`extract_error_code`), либо `internal`.
- Files: `app/engines/higgsfield.py:183-230`, `app/worker/pipeline.py:49-54`,
  `app/worker/pipeline.py:174`
- Impact: `texts.failure_text` знает только четыре кода
  (`app/bot/texts.py:48-55`), остальные падают в общий текст; аналитика по
  `events.error_code` невозможна.
- Fix approach: единая функция нормализации кода на границе движка, тест
  «каждый код из спеки даёт определённый текст пользователю».

**Мёртвые тексты и отсутствующий обработчик команд:**
- Issue: `UNKNOWN_COMMAND`, `AGAIN_HINT`, `AGAIN_REQUEST` объявлены и не
  используются. Любое не-фото сообщение уходит в `handle_other`.
- Files: `app/bot/texts.py:40-45`, `app/bot/handlers/upload.py:54-63`
- Impact: после получения видео пользователь, написавший «спасибо», получает
  «Нужно фото…»; требование
  `specs/tg-entry/spec.md:78-82` (объяснить, почему фото нужно снова) не
  выполнено.
- Fix approach: отдельный роутер текстовых сообщений: `/start`-подсказка,
  `PHOTO_REQUEST` только в состоянии `paid`.

**`seed` не синхронизирует контент шаблона:**
- Issue: `seed_default_template` выходит, если в таблице есть строки.
- Files: `app/db/seed.py:45-53`
- Impact: решение D6 (`openspec/changes/mvp-001-core-flow/design.md:69-75`)
  обещает «промпт правится в файле и применяется рестартом»; фактически
  `templates/default/prompt.txt` читается только на пустой БД. Смена промпта
  без SQL не подхватится.
- Fix approach: upsert по `key` с обновлением `prompt`/`price` из конфига, либо
  честно зафиксировать в дизайне, что синка нет.

**Расхождение документации и кода:**
- Issue: `docs/architecture.md:104-109` описывает `VideoEngine` c
  `ensure_asset/submit/poll/cancel`, в коде порт — один `generate`
  (`app/engines/base.py:84-89`). Стейт-машина задания в
  `docs/architecture.md:154-162` (submitted/polling/rejected/no_credits) не
  совпадает с `repo.JobStatus` (new/running/done/failed,
  `app/db/repo.py:20-26`). `docs/architecture.md:151-152` обещает исключение и
  error-лог на нелегальный переход — код возвращает `Err` без лога
  (`app/domain/order_service.py:93-97`). `README.md:6` утверждает «MVP не
  начат», `README.md:85` — «0/63 tasks». `tasks.md:24` помечает миграции в
  entrypoint выполненными, `README.md:69-70` объясняет, что их там нет.
- Files: `docs/architecture.md`, `README.md`,
  `openspec/changes/mvp-001-core-flow/tasks.md:24`, `app/engines/base.py:84-89`,
  `app/db/repo.py:20-26`
- Impact: планировщик и исполнитель будут опираться на неверные контракты;
  чек-листы приёмки закрываются «по галочке», а не по поведению.
- Fix approach: привести доки к коду (или наоборот) в рамках отдельного
  изменения; не отмечать задачи выполненными до появления потребителя.

**Лишние зависимости и отсутствие lockfile:**
- Issue: `fastapi` и `uvicorn` объявлены, но не импортируются нигде; lockfile
  (`uv.lock`/`requirements.txt`) отсутствует, версии заданы диапазонами.
- Files: `pyproject.toml:11-21`, `Dockerfile:18-19`
- Impact: неповторяемая сборка (новая минорная версия aiogram ломает polling),
  лишняя поверхность атаки и вес образа.
- Fix approach: убрать неиспользуемые пакеты, зафиксировать зависимости
  lock-файлом и собирать по нему.

## Known Bugs

**Заказ в `paid` без фото блокирует пользователя навсегда:**
- Symptoms: пользователь оплатил и не прислал фото; при следующем `/start` и
  при нажатии «Оплатить» бот отвечает `ACTIVE_ORDER` («заказ в работе»),
  нового заказа нет.
- Files: `app/domain/order_service.py:70-72`, `app/db/repo.py:169-178`,
  `app/bot/handlers/start.py:59-70`, `app/bot/handlers/checkout.py:55-57`
- Trigger: `/start` → «Оплатить» → закрыть чат. Повторить через час.
- Workaround: ручной SQL `UPDATE orders SET status='failed'`.
- Fix approach: TTL для `paid` (например, 30 минут) с переходом в `failed` без
  возврата или с возвратом; экран «продолжить заказ» вместо тупика.

**Остановка воркера оставляет заказ в `running` навсегда:**
- Symptoms: `docker compose down`/деплой во время генерации → `jobs.status =
  running`, `orders.status = running`; повторного взятия нет, сторож отсутствует,
  пользователь не получает ни видео, ни отказа.
- Files: `app/worker/loop.py:15-24`, `app/worker/loop.py:44-48`,
  `app/main_worker.py:41-58` (`stop_grace_period: 30s` в
  `docker-compose.yml:66` при генерации до 8 минут), `app/config.py:48`
- Trigger: SIGTERM в окне `process_job`; либо падение процесса после `claim_job`.
- Impact: заказ не терминален, кредит не возвращён; нарушено
  `docs/implementation-plan.md:125` («ни один заказ не остаётся в
  неопределённом статусе») и `specs/generation/spec.md:79-85`.
- Fix approach: сторож (`running` старше `JOB_STALE_MINUTES` → `new` с
  инкрементом `attempt`), плюс на SIGTERM не отменять слоты, а дождаться или
  вернуть задачу в очередь.

**Возврат и «провал» после уже отправленного видео:**
- Symptoms: пользователь получает видео, а следом — «Не получилось сделать
  видео. Кредит за заказ вернул».
- Files: `app/worker/pipeline.py:97-110`,
  `app/worker/pipeline.py:41-54`, `app/worker/pipeline.py:181-186`
- Trigger: `send_video` прошёл, а `mark_delivered` упал (обрыв БД, гонка за
  строку заказа). Исключение уходит в общий `except Exception` → `fail_job`;
  `fail_order` не может перевести `delivered → failed` и молча выходит.
- Impact: рассинхрон доставки и статуса; задача помечена `failed`, заказ
  остаётся `delivered`, уведомление об ошибке ложное.
- Fix approach: различать «доставлено, не сохранили» (повтор `mark_delivered`,
  не `fail_job`) и «не доставлено»; для `delivered` в `fail_job` — no-op с
  отдельным событием.

**Фото остаётся на диске, если постановка в очередь провалилась:**
- Symptoms: файл `photo-<order_id>.jpg` лежит в `STORAGE_DIR` без заказа в
  очереди.
- Files: `app/bot/handlers/upload.py:76-79`,
  `app/bot/handlers/upload.py:83-95`
- Trigger: `save_photo` успешен, `queue_order` бросил `LookupError` (гонка,
  статус уже не `paid`), или `create_job` упал на `UNIQUE idempotency_key`.
- Impact: нарушение `specs/privacy-retention/spec.md:3-18`; мусор копится без
  сторожа.
- Fix approach: сохранять фото после успешной постановки в очередь либо
  удалять его в `except` вокруг `queue_order`.

**В Docker воркер не видит фото бота и шаблон видео:**
- Symptoms: на `ENGINE=higgsfield` в контейнерах заказ падает с
  `engine_failed` («не удалось прочитать файл photo-N.jpg»), хотя бот ответил
  «Принято».
- Files: `docker-compose.yml:20-32`, `docker-compose.yml:52-67`,
  `app/config.py:52` (`/data/tmp`), `app/storage/local.py:16-28`,
  `app/engines/higgsfield.py:135-139`, `Dockerfile:14-15`,
  `app/db/seed.py:13`
- Trigger: `tasks.ps1 up` с `ENGINE=higgsfield`, реальный заказ. Фото пишет
  контейнер `bot`, читает контейнер `worker` — общего тома нет, `VOLUME` в
  образе не объявлен. `templates/` в образ не копируется, поэтому
  `source_path = "templates/default/source.mp4"` не существует и внутри
  контейнера.
- Impact: реальный движок в контейнерной сборке неработоспособен; `mock`
  маскирует проблему, потому что не читает фото
  (`app/engines/mock.py:47-62`).
- Fix approach: named volume на `STORAGE_DIR` в оба сервиса, `templates/` в
  образ или в том, проверка существования файла до `submit`.

**Пустая БД роняет бота: `up` не применяет миграции:**
- Symptoms: `python -m app.main_bot` падает на
  `seed_default_template` с `UndefinedTable` при `tasks.ps1 up` без
  предварительного `tasks.ps1 migrate`.
- Files: `app/main_bot.py:30-40` (`seed_default_template` на строке 35),
  `Dockerfile:22-24`, `docker-compose.yml:20-32`,
  `openspec/changes/mvp-001-core-flow/tasks.md:24`
- Trigger: чистый том `postgres_data`, `.\tasks.ps1 up`.
- Impact: порядок команд неочевиден, ошибка выглядит как падение приложения.
- Fix approach: `depends_on: migrate: service_completed_successfully` для
  `bot`/`worker` либо entrypoint с `alembic upgrade head` (как ошибочно
  отмечено в `tasks.md`), плюс `/health`, который это показывает.

**Два фото подряд могут дать `IntegrityError` вместо ответа:**
- Symptoms: пользователь присылает два фото почти одновременно; на втором
  обработчик падает, ответа нет.
- Files: `app/bot/handlers/upload.py:32-51`,
  `app/bot/handlers/upload.py:83-95`, `app/db/models.py:111`,
  `app/worker/pipeline.py:57-71`
- Trigger: два апдейта в пределах одного `get_active_order` (нет блокировки
  строки). Второй проходит `is_awaiting_photo`, затем `create_job` нарушает
  `UNIQUE(idempotency_key)`; логика ретрая/ответа отсутствует, обработчик
  ошибок в aiogram не зарегистрирован (`app/main_bot.py:18-27`).
- Impact: техническая ошибка пользователю, шум в логах, потенциально два
  задания на один заказ.
- Fix approach: `SELECT ... FOR UPDATE` на заказе при приёме фото, обработка
  `IntegrityError` как «фото уже принято».

**`claim_job` зависит от расхождения часов приложения и БД:**
- Symptoms: задание не забирается сразу после создания; тест вынужден брать
  заведомо будущее время.
- Files: `app/db/repo.py:194-211`, `app/db/models.py:112-114`,
  `tests/test_repo_integration.py:15-18`
- Trigger: `next_attempt_at` заполняется серверным `now()`, сравнение идёт с
  `services.now()` из процесса (`app/worker/loop.py:44-48`). Комментарий в
  тесте прямо фиксирует зависимость.
- Impact: при расхождении часов задание «висит» до выравнивания; в тестах это
  замаскировано.
- Fix approach: `next_attempt_at` заполнять из приложения (`now()` как
  параметр) либо сравнивать с `func.now()` в SQL.

## Security Considerations

**Бесплатная генерация при публичном доступе (заглушка оплаты):**
- Risk: `PAYMENT_PROVIDER=stub` всегда подтверждает оплату
  (`app/payments/stub.py:15-23`), дневного лимита и гейта кредитов нет
  (`app/config.py:44-45` не читаются). Любой пользователь может генерировать
  бесконечно и жечь кредиты Higgsfield.
- Files: `app/payments/factory.py:8-12`, `app/payments/stub.py:9-27`,
  `app/bot/handlers/checkout.py:36-79`, `app/config.py:46`
- Current mitigation: `SALES_ENABLED` проверяется в
  `app/bot/handlers/checkout.py:41-43` — это единственный работающий
  предохранитель.
- Recommendations: до публичного запуска — дневной лимит
  (`specs/ops/spec.md:41-48`), гейт `engine_credits_hint`, алерт на всплеск
  `order_created`; не выставлять `stub` в прод.

**Неверифицированный контракт Higgsfield:**
- Risk: каждый шаг внешнего API — предположение: поля `input`, multipart
  загрузки, имя поля со ссылкой, `status_url`, имена статусов, код ошибки.
  Документ честно перечисляет 8 неподтверждённых мест.
- Files: `docs/higgsfield-contract.md:21-32`,
  `app/engines/higgsfield.py:120-180`, `app/engines/transport.py:114-132`
- Current mitigation: 13 тестов на `httpx.MockTransport`
  (`tests/test_higgsfield_engine.py`) — но фикстуры написаны по тем же
  предположениям, поэтому проверяют согласованность с собой, а не с API.
  Задача 0 (живой прогон) не закрыта, задача 5.6 не закрыта.
- Recommendations: выполнить чек-лист `docs/higgsfield-contract.md:39-58` до
  продакшена; при расхождении — правки только в перечисленных там функциях;
  сохранять `EngineResult.raw` в `events`/лог для разбора (сейчас `raw` не
  используется нигде: `app/engines/base.py:32-39`).

**Передача фото третьей стороне не раскрыта в согласии:**
- Risk: фото лица уходит в Higgsfield (multipart на `HF_UPLOAD_URL`,
  `app/engines/higgsfield.py:120-132`), срок жизни и юрисдикция хранения на
  стороне провайдера не контролируются. Текст согласия говорит только об
  «обработке фотографии для генерации».
- Files: `app/bot/texts.py:13-21`, `app/bot/handlers/start.py:12`,
  `openspec/changes/mvp-001-core-flow/specs/privacy-retention/spec.md:20-42`
- Current mitigation: фиксация `consent_version`/`consent_at` в `users`
  (`app/db/repo.py:104-107`), удаление фото на терминальном статусе
  (`app/worker/pipeline.py:151-159`).
- Recommendations: добавить в согласие явный пункт о передаче изображения
  внешнему сервису и трансграничной передаче; хранить версию текста, чтобы
  смена формулировки требовала нового согласия (сейчас `CONSENT_VERSION="v1"`
  статичен, `app/bot/handlers/start.py:12`).

**Редакция логов не покрывает сообщения и трейсбеки:**
- Risk: `SENSITIVE_FIELDS` фильтрует только `extra`-поля записи. Текст
  сообщения (`record.getMessage()`) и `exception` попадают в JSON как есть;
  при `LOG_LEVEL=DEBUG` (`app/config.py:59`) root-логгер включает отладочный
  вывод aiogram, где печатаются апдейты с именем/username пользователя и
  `file_id`.
- Files: `app/obs/logs.py:12-23`, `app/obs/logs.py:49-61`,
  `app/obs/logs.py:72-90`, `app/config.py:59`
- Current mitigation: собственный код логирует только `job_id`/`engine`
  (`app/worker/loop.py:32,41`, `app/worker/pipeline.py:53,159,209`).
- Recommendations: запретить `DEBUG` в прод-конфиге, добавить фильтр на
  `aiogram`-логгеры, редактировать `message`/`exception` по тем же правилам,
  тест «трейсбек с URL не содержит секретов».

**Файлы фото без TTL и без подписи:**
- Risk: `specs/privacy-retention/spec.md:44-51` требует подписанные ссылки с
  TTL 15 минут, `spec.md:53-59` — очистку `STORAGE_DIR` при старте. Реализация:
  предсказуемый путь `photo-<order_id>.jpg`, без TTL, без очистки при
  рестарте; файл удаляется только по терминальному статусу.
- Files: `app/storage/local.py:16-28`, `app/worker/pipeline.py:151-159`,
  `app/config.py:53`
- Current mitigation: каталог не публикуется наружу; движку файл уходит
  multipart-загрузкой, а не ссылкой на наш диск.
- Recommendations: удаление при старте процесса и сторож по возрасту файла
  (>15 минут); либо `PresignedStorage` по образцу `engines/factory.py`.

**`is_banned` не проверяется, админ-команд нет:**
- Risk: флаг `users.is_banned` существует, но ни один обработчик его не
  читает; `/admin ban` отсутствует, как и whitelist `TG_ADMIN_IDS`.
- Files: `app/db/models.py:47`, `app/config.py:30`,
  `openspec/changes/mvp-001-core-flow/specs/ops/spec.md:17-31`
- Current mitigation: отсутствие админки означает отсутствие и вектора атаки
  через неё.
- Recommendations: при добавлении админки — проверка whitelist в middleware,
  аудит в `events`, тест «не-админ получает нейтральный отказ».

**Секреты движка изолированы в воркере (митигация):**
- Risk: снижен — ключи Higgsfield читаются только при сборке воркера.
- Files: `app/main_bot.py:43-51` (движок не собирается),
  `app/main_worker.py:61-71`, `app/config.py:106-113`
- Current mitigation: `SecretStr` + `repr=False` в конфиге движка
  (`app/engines/higgsfield.py:37-39`), падение при отсутствии ключей.
- Recommendations: сохранить это разделение при появлении `/health` и
  админки в боте — не тащить движок в процесс бота.

## Performance Bottlenecks

**Пропускная способность воркера:**
- Problem: два слота на один процесс, каждый держит задачу до терминального
  статуса включительно (uptime генерации до 8 минут плюс доставка).
- Files: `app/config.py:49`, `app/worker/loop.py:15-24`,
  `app/worker/pipeline.py:41-54`, `app/config.py:40`
- Cause: конкурентность фиксирована, слот занят на всё время `poll`
  (`app/engines/higgsfield.py:97-110`, интервал 3 с, до ~160 запросов на
  задание).
- Improvement path: вынести `poll` в отдельный пул или увеличить
  `WORKER_CONCURRENCY` после замера лимитов API; при 8 минутах на заказ и двух
  слотах потолок ≈ 15 заказов в час на процесс.

**Загрузка шаблонного видео целиком в память без блокировки:**
- Problem: `read_bytes` всего `.mp4` и передача в multipart; кэш —
  `dict` в памяти экземпляра движка.
- Files: `app/engines/higgsfield.py:72-79`,
  `app/engines/higgsfield.py:120-137`
- Cause: при старте процесса кэш пуст; два слота могут одновременно пройти
  проверку `cached is None` и загрузить файл дважды. При рестарте — снова.
- Improvement path: `asyncio.Lock` на `template_key`, потоковая загрузка
  (`httpx` с file-like), кэш в `templates.engine_video_url` с TTL.

**Доставка видео по URL без проверки размера и нормализации:**
- Problem: `send_video` отдаёт Telegram строку-URL, если файл не локальный;
  размер, контейнер и битрейт не проверяются.
- Files: `app/worker/pipeline.py:119-126`,
  `app/worker/pipeline.py:129-130`, `app/config.py:40`
- Cause: задачи 6.1–6.4 не реализованы; лимит Bot API на `sendVideo` по URL
  (20 МБ) не контролируется, ffmpeg для нормализации есть в образе, но не
  используется (`Dockerfile:9-12`).
- Improvement path: скачать результат в `STORAGE_DIR`, прогнать
  `ffmpeg -vf scale=-2:720 ... -movflags +faststart`, проверить размер,
  при превышении — документ; сохранять `file_id` (сейчас колонки нет).

**Холостой опрос очереди:**
- Problem: каждый слот раз в секунду открывает сессию и делает `SELECT`.
- Files: `app/worker/loop.py:27-41`, `app/db/repo.py:194-211`
- Cause: `IDLE_DELAY_SEC = 1.0` без `LISTEN/NOTIFY` и без экспоненциальной
  паузы.
- Improvement path: `pg_notify` при `create_job`; либо пауза 1→5 с при
  повторных пустых выборках.

**Отсутствие индексов на горячих запросах:**
- Problem: `ledger` не имеет ни одного индекса, кроме PK; `orders` — только
  `status`; `events` и `jobs` растут без ретенции.
- Files: `app/db/migrations/versions/0001_initial.py:138-165`,
  `app/db/migrations/versions/0001_initial.py:96`,
  `app/db/repo.py:169-178`, `app/db/repo.py:230-233`
- Cause: `get_active_order` фильтрует по `user_id, status`; `load_order_ledger`
  и `load_ledger` — seq scan по `ledger`.
- Improvement path: partial index `orders(user_id) WHERE status IN
  ('paid','queued','running')`, индекс `ledger(user_id, order_id)`,
  ретенция `events`/`jobs` (архив или удаление старше 90 дней).

## Fragile Areas

**`app/worker/pipeline.py` — деньги без тестов:**
- Files: `app/worker/pipeline.py:41-218`
- Why fragile: 218 строк с refund-логикой, четырьмя независимыми сессиями БД,
  сетевой отправкой и вызовами `asyncio.to_thread`; ноль тестов
  (`tests/` не содержит ни `process_job`, ни `fail_job`, ни `deliver`).
- Safe modification: тест на фейковом движке и фейковом боте (задача 9.7)
  до любой правки; все ветки `write → send → mark` проверять по событиям в
  `events` и записям `ledger`.
- Test coverage: 0%.

**`app/engines/higgsfield.py` — тесты подтверждают предположения:**
- Files: `app/engines/higgsfield.py:63-230`,
  `tests/test_higgsfield_engine.py:103-296`,
  `docs/higgsfield-contract.md:21-32`
- Why fragile: 13 тестов построены на тех же ожиданиях, что и код; регресс
  против реального API они не поймают. Любое изменение `map_status`/
  `build_payload` ломает совместимость без внешнего сигнала.
- Safe modification: правки — только в функциях из таблицы
  `docs/higgsfield-contract.md:61-73`; после правки обновлять документ и
  фикстуры; держать `raw` ответа для разбора.
- Test coverage: контракт — на фикстурах, живого прогона нет (задача 5.6).

**Состояние в памяти процесса:**
- Files: `app/engines/higgsfield.py:61`, `app/bot/middlewares/dedupe.py:16`,
  `app/bot/middlewares/throttle.py:27`
- Why fragile: `HiggsfieldVideoEngine` — `frozen` dataclass с изменяемым
  `dict`; кэш шаблона и дедуп/троттлинг живут только в одном процессе.
  Реплик бота или воркера быть не может без тихой потери гарантий
  (повторная загрузка шаблона, повторная обработка апдейта, отсутствие
  троттлинга между процессами).
- Safe modification: не масштабировать горизонтально, пока состояние в
  памяти; при необходимости — кэш в БД, дедуп по `update_id` в таблице.
- Test coverage: дедуп и троттлинг не тестируются вообще.

**Молчаливое проглатывание ошибок домена:**
- Files: `app/worker/pipeline.py:181-186` (`return` при `Err`),
  `app/worker/pipeline.py:189-194` (`return` при `Err`),
  `app/worker/pipeline.py:168-178`
- Why fragile: нелегальный переход и повторный возврат не логируются и не
  попадают в `events` (событие `job_failed` пишется с `user_id=None`,
  `app/worker/pipeline.py:176`). Двойной возврат или потерянный возврат
  проявятся только по расхождению в ledger.
- Safe modification: логировать `IllegalTransition`/`AlreadyRefunded` с
  `job_id` и писать событие; тест «повторный fail не создаёт второй refund».
- Test coverage: домен покрыт (`tests/test_ledger.py`,
  `tests/test_order_service.py`), интеграция домена с БД — нет.

**Обработчики бота проверены только на регистрацию:**
- Files: `tests/test_bot_wiring.py:28-55`,
  `app/bot/handlers/checkout.py:36-101`,
  `app/bot/handlers/upload.py:32-95`
- Why fragile: тесты утверждают, что хендлеры подключены, но ни один не
  вызывается. Ошибка в `charge_order`/`write_ledger` (например, порядок
  `top_up`/`debit` или отсутствие проверки идемпотентности,
  `app/bot/handlers/checkout.py:95-101`) не будет замечена.
- Safe modification: E2E через aiogram test-клиент (задача 9.8) и юнит-тесты
  на `start_checkout`/`handle_photo` с фейковой сессией.
- Test coverage: только wiring и непустые тексты.

**Валидация фото зависит от Pillow-поведения:**
- Files: `app/domain/moderation.py:75-107`, `app/bot/photo.py:25-34`
- Why fragile: полигоны и «decompression bomb» обрабатываются через
  исключения Pillow; `download_photo` не проверяет размер, если
  `file_size is None` (документ без размера) — лимит применяется уже после
  полной загрузки в память.
- Safe modification: добавить тесты на усечённый JPEG и на документ без
  `file_size`; проверять размер после скачивания и до `Image.load`.
- Test coverage: 10 тестов на `prepare_photo`, ноль на `download_photo`.

## Scaling Limits

**Хранилище на локальном диске:**
- Current capacity: один хост, один `STORAGE_DIR`, решение D8
  (`openspec/changes/mvp-001-core-flow/design.md:85-91`) — «до нескольких
  сотен заказов в день».
- Limit: вторая машина воркера не увидит фото; общий том — единственный
  вариант без S3.
- Scaling path: `Storage`-порт уже есть (`app/storage/base.py:7-24`) —
  реализовать `S3Storage` и включить по `STORAGE`.

**Очередь и воркер:**
- Current capacity: 2 одновременные задачи, потолок ≈ 15 заказов/час на
  процесс при 8-минутной генерации.
- Limit: всплеск заказов копится в `jobs`, пользователь ждёт в неведении
  (задачи 3.5 — обновление сообщения о статусе — не реализованы).
- Scaling path: увеличить `WORKER_CONCURRENCY` после замера лимитов API,
  затем отдельный пул; брокер не нужен до сотен задач в час
  (`design.md:20-31`).

**Postgres как очередь и `events` как единственная аналитика:**
- Current capacity: `claim_job` укладывается в `ix_jobs_status_next_attempt_at`.
- Limit: `events`/`jobs` без ретенции; `/admin stats` (блок 7.3) не
  реализован, значит запросов по `events` пока нет, но таблица растёт с
  каждым заказом.
- Scaling path: партиционирование `events` по месяцу и ретенция.

**Лимиты Telegram:**
- Current capacity: одно видео на заказ, отправка по URL или файлом.
- Limit: 20 МБ на `sendVideo` по URL, 50 МБ на загрузку файла; нормализация
  (6.1) и фолбэк на документ (6.2) не реализованы.
- Scaling path: ffmpeg-нормализация перед отправкой + сохранение `file_id`
  для повторной выдачи.

## Dependencies at Risk

**Higgsfield — единственный движок:**
- Risk: нет второго провайдера и фолбэка; `engines/factory.py` знает только
  `mock` и `higgsfield`. Риск «API недоступен из РФ» зафиксирован как средний
  (`openspec/changes/mvp-001-core-flow/proposal.md:47-51`,
  `design.md:134-136`, `docs/implementation-plan.md:106`).
- Impact: недоступность API = полная остановка продаж; `VideoEngine`-порт
  позволяет замену, но реализации нет.
- Migration plan: `engines/backup.py` по таблице эволюции
  (`docs/architecture.md:258`); выбор движка — флаг в конфиге, а не правка
  кода.

**Модель и цена кредитов неизвестны:**
- Risk: `HF_MODEL` и `HF_UPLOAD_URL` по умолчанию пусты
  (`app/config.py:35-37`), цена Genjutsu не подтверждена (задача 0.2),
  `engine_credits_hint` не используется.
- Impact: либо `EngineBadConfig` на первом же заказе, либо отрицательная
  маржа без предупреждения.
- Migration plan: закрыть этап 0 (`tasks.md:3-15`) и 5.6, завести гейт
  кредитов из блока 7.

**Нет фиксации версий:**
- Risk: `pyproject.toml:11-21` задаёт диапазоны (`aiogram>=3.15,<4`), lockfile
  отсутствует.
- Impact: пересборка образа в другой день даёт другой набор версий; для
  aiogram это исторически ломающие минорные изменения поведения polling.
- Migration plan: lockfile (`uv.lock`) + сборка из него; Dependabot/ручное
  обновление с прогоном тестов.

**Неиспользуемые `fastapi`/`uvicorn`:**
- Risk: пакеты в рантайм-зависимостях, но `app/api` не существует; `/health`
  (задача 7.5) не реализован.
- Impact: лишний вес образа и лишняя поверхность обновлений.
- Migration plan: удалить до появления `api/`; при реализации `/health`
  вернуть осознанно, с проверкой БД и возраста последней задачи
  (`specs/ops/spec.md:71-78`).

## Missing Critical Features

**Реальная оплата:**
- Problem: `PAYMENT_PROVIDER=yookassa` объявлен в конфиге
  (`app/config.py:55-57`) и в `docs/stack.md:73`, но фабрика поднимает
  `ConfigError`, а модуля `payments/yookassa.py` нет.
- Blocks: публичный запуск и приём денег; юридические чеки; обработка
  повторного `successful_payment` (сейчас идемпотентность держится только на
  проверке активного заказа, `app/bot/handlers/checkout.py:55-57`).

**Дневной лимит и гейт кредитов движка:**
- Problem: `daily_generation_cap` и `engine_credits_hint` не читаются;
  при `no_credits` продажи не останавливаются.
- Blocks: защита от слива кредитов (`specs/ops/spec.md:3-16,41-48`);
  `specs/generation/spec.md:59-67` (перевод `SALES_ENABLED=false`) невыполним
  в рантайме — конфиг `frozen` (`app/config.py:23`).

**Сторож и таймаут задания:**
- Problem: `JOB_TIMEOUT_MIN`/`JOB_STALE_MINUTES` не используются; сторож
  отсутствует; задача 4.4 не реализована.
- Blocks: гарантия «ни один заказ не остаётся в неопределённом статусе»
  (`docs/implementation-plan.md:125`); после падения процесса заказ
  навсегда `running`.

**Сохранение `file_id` и идемпотентная доставка:**
- Problem: колонки `file_id` в `orders` нет, `send_video` не сохраняет
  результат; повторная доставка невозможна без перегенерации.
- Blocks: `specs/delivery/spec.md:7-16,33-39`; повторная отправка того же
  видео по запросу пользователя.

**Нормализация и лимиты медиа:**
- Problem: нет ffmpeg-нормализации результата, проверки размера, фолбэка на
  документ, обработки 429 с `retry_after`.
- Blocks: `specs/delivery/spec.md:12-31`; видео >20 МБ сейчас не доставится
  вовсе и приведёт к возврату кредита после 8 минут ожидания.

**Бесплатный реролл:**
- Problem: колонки `rerolls` нет, кнопка «Не то» отсутствует; «Ещё раз»
  переиспользует `CHECKOUT_CALLBACK` и создаёт **новый** заказ с новой
  оплатой.
- Files: `app/bot/keyboards.py:24-26`,
  `app/bot/handlers/checkout.py:18-22`, `tasks.md:72-73`
- Blocks: `specs/billing/spec.md:61-78`; при `stub` пользователь не заметит
  списания, при реальной оплате — заплатит второй раз за «Ещё раз».

**Админка, алерты, `/health`:**
- Problem: `/admin stats|balance|sales|ban|order`, алерты и HTTP-эндпоинт
  здоровья отсутствуют; healthcheck в `docker-compose.yml` есть только у
  `postgres`.
- Blocks: `specs/ops/spec.md:17-31,49-78`; обнаружение зависшего воркера и
  кончившихся кредитов возможно только вручную по логам.

**Удаление данных по запросу пользователя:**
- Problem: нет команды и процедуры удаления артефактов пользователя.
- Blocks: `specs/privacy-retention/spec.md:36-42`; при работающем боте
  запрос «удалите мои данные» невыполним.

**Очистка `STORAGE_DIR` при старте:**
- Problem: ни один из процессов не чистит каталог при запуске; осиротевшие
  `photo-*.jpg` и `mock-*.mp4` остаются после падений.
- Files: `app/main_bot.py:30-40`, `app/main_worker.py:41-58`,
  `app/engines/mock.py:65-70`
- Blocks: `specs/privacy-retention/spec.md:53-59`.

**CI:**
- Problem: конфигурации CI нет (`glob .github/**` пуст), `ruff` и тесты
  запускаются только локально через `tasks.ps1`.
- Files: `pyproject.toml:36-71`, `tasks.ps1:52-58`
- Blocks: задача 9.9; регресс в домене и линте проезжает незамеченным, пока
  кто-то не запустит `tasks.ps1 test` вручную.

## Test Coverage Gaps

**Воркер: цикл и пайплайн:**
- What's not tested: `run_pool`, `run_slot`, `claim_next`, `process_job`,
  `deliver`, `fail_job`, `mark_failed`, `refund_credit`, `cleanup`.
- Files: `app/worker/loop.py:15-48`, `app/worker/pipeline.py:41-218`
- Risk: любая правка порядка «сохранить статус → отправить → вернуть кредит»
  может дать двойную доставку, потерянный возврат или зависший заказ. Это
  единственный путь, где двигаются деньги и кредиты.
- Priority: **High** (задача 9.7).

**Миграции против моделей:**
- What's not tested: соответствие `alembic upgrade head` и `Base.metadata`.
- Files: `tests/conftest.py:36-50` (схема создаётся `create_all`, Alembic в
  тестах не участвует), `app/db/migrations/versions/0001_initial.py`
- Risk: миграция и модели разойдутся молча; `tests/test_models.py` проверяет
  только модели. Планируемое DB-ограничение «один активный заказ» может
  появиться в модели и не попасть в миграцию.
- Priority: **High** (задача 9.6).

**Обработчики бота и денежный путь:**
- What's not tested: `handle_photo` (все ветки отказа и гонки),
  `handle_checkout`/`charge_order` (списание, `PaymentFailed`, повторный
  клик), `handle_consent`, `show_home`.
- Files: `app/bot/handlers/upload.py:32-95`,
  `app/bot/handlers/checkout.py:36-101`,
  `app/bot/handlers/start.py:23-70`, `tests/test_bot_wiring.py:28-55`
- Risk: двойное списание/отсутствие списания, приём фото без активного
  заказа, падение после оплаты (пользователь заплатил и не получил запрос
  фото) — всё это не поймается.
- Priority: **High** (задачи 9.7, 9.8).

**Middleware дедупликации и троттлинга:**
- What's not tested: повторный `update_id`, вытеснение по ёмкости, поведение
  для callback и message.
- Files: `app/bot/middlewares/dedupe.py:18-29`,
  `app/bot/middlewares/throttle.py:29-54`
- Risk: повторная обработка апдейта (двойной заказ) или троттлинг, режущий
  легитимные действия; изменения в порядке middleware не проверяются.
- Priority: **Medium**.

**Сквозной путь на `ENGINE=mock`:**
- What's not tested: `/start → согласие → оплата → фото → видео`; сквозного
  теста нет, `test_engines_mock.py:37-44` проверяет только генерацию mp4.
- Files: `app/main_bot.py:18-40`, `app/worker/pipeline.py`,
  `openspec/changes/mvp-001-core-flow/tasks.md:55,102`
- Risk: сборка «бот + воркер + БД» не проверяется вовсе; рассинхрон
  пути к фото (см. раздел Known Bugs) обнаружится только в контейнерах.
- Priority: **High** (задачи 4.7, 9.8).

**Хранилище и проводка зависимостей:**
- What's not tested: `LocalStorage` (сохранение, удаление, отсутствующий
  файл), `build_video_engine`/`build_payment_provider`,
  `build_bot_services`.
- Files: `app/storage/local.py:10-37`, `app/engines/factory.py:12-46`,
  `app/payments/factory.py:8-12`, `app/bot/services.py:28-37`
- Risk: неверная сборка (например, `STORAGE=s3` игнорируется) всплывёт в
  проде; ошибка в фабрике — на старте процесса, а не в тесте.
- Priority: **Medium**.

**Порог покрытия и CI-гейт:**
- What's not tested: нет `--cov-fail-under`, нет падения сборки на падении
  тестов вне ручного запуска.
- Files: `pyproject.toml:61-71`, `docker-compose.yml:106-115`,
  `tasks.ps1:52`
- Risk: покрытие деградирует незаметно; задачи 9.9 и 9.10 открыты, значит
  регресс не блокирует merge.
- Priority: **Medium**.

---

*Concerns audit: 2026-11-08*
