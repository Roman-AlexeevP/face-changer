---
last_mapped_commit: 8cdc2abb49b272f3240a75e55c06f62b162fc586
last_mapped_at: 2026-11-08
---
<!-- refreshed: 2026-11-08 -->
# Testing Patterns

**Analysis Date:** 2026-11-08

## Test Framework

**Runner:**

- pytest `>=8.3,<9`, pytest-asyncio `>=0.24,<1`, pytest-xdist `>=3.6,<4`,
  pytest-cov `>=5,<7`, pytest-html `>=4.1,<5` — секция `dev` в `pyproject.toml:23-31`.
- Конфигурация — `pyproject.toml:52-59`:

  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  asyncio_mode = "auto"
  asyncio_default_fixture_loop_scope = "session"
  addopts = "-ra"
  markers = [
      "integration: требует PostgreSQL (TEST_DATABASE_URL), пропускается без него",
  ]
  ```

  `asyncio_mode = "auto"` — `async def test_*` не требует `@pytest.mark.asyncio`;
  `asyncio_default_fixture_loop_scope = "session"` — async-фикстуры по умолчанию живут
  в session-loop, а function-scoped фикстура `session` переопределяет loop через
  `loop_scope="function"` (`tests/conftest.py:53`).

**Assertion Library:**

- Встроенный `assert`, `pytest.raises`, `pytest.fail`, `pytest.skip`.
- Сторонних assertion-библиотек нет; `unittest.mock`, `MagicMock`, `patch`,
  `mocker` не используются (0 совпадений в `tests/`).
- Сравнение — по значению `frozen` датаклассов: `assert pay(order, NOW) == Ok(expected)`.

**Run Commands:**

```powershell
.\tasks.ps1 test        # весь набор в контейнере: pytest + coverage + HTML-отчёты
.\tasks.ps1 lint        # ruff check . && ruff format --check .
.\tasks.ps1 fmt         # ruff format .

# без обёртки
docker compose --profile test run --rm tests
docker compose --profile test run --rm tests sh -c "pytest -q tests/test_order_service.py"
docker compose --profile test run --rm tests sh -c "pytest -q -k 'ledger' --no-header"
```

`command` сервиса `tests` — список (`docker-compose.yml:106-115`), поэтому выбор
отдельного файла/теста делается через `sh -c "pytest ..."`, иначе аргументы допишутся
к уже готовой команде.

Тестовый образ — stage `test` в `Dockerfile:26-35`: тот же `base` с ffmpeg, плюс
`pip install -e ".[dev]"`. Compose монтирует `./app`, `./tests`, `./pyproject.toml`
и `./reports` (`docker-compose.yml:101-105`), поэтому правки видны без пересборки,
а HTML-отчёты остаются на хосте.

**Фактическое состояние (2026-11-08):**

- 191 тестовый случай: 100 функций в 15 файлах, остальное — параметризация.
- `ruff check .` — «All checks passed!», `ruff format --check .` — 65 файлов.
- Эталонный прогон в контейнере (`reports/report.html`, 06.11.2026):
  **191 passed, 0 failed, 0 skipped, 0 errors**.
- Вне контейнера без PostgreSQL 4 интеграционных теста пропускаются, без ffmpeg —
  ещё 1 (`tests/test_engines_mock.py:37`).

## Test File Organization

**Location:**

- Отдельный каталог `tests/` в корне, без `__init__.py`; тесты не лежат рядом с кодом.
- Один файл — один предмет: доменный модуль, слой или сквозное свойство.

**Naming:**

- `tests/test_<subject>.py`, где subject — модуль (`test_order_service.py`,
  `test_ledger.py`) или свойство (`test_architecture.py`, `test_bot_wiring.py`).
- Имена тестов — утверждение о поведении в настоящем времени:
  `test_pay_twice_returns_already_paid`, `test_illegal_transition_returns_error`,
  `test_refund_for_delivered_order_is_rejected`, `test_stub_refund_does_not_raise`.
- Никаких `test_1`, `test_works`, `test_happy_path`.

**Structure:**

```text
tests/
├── conftest.py                  # 69 строк: схема на xdist-воркера, сессия с откатом
├── test_architecture.py         #   1 кейс  — AST-проверка чистоты domain/
├── test_bot_wiring.py           #   3 кейса — регистрация хендлеров, непустые тексты
├── test_config.py               #   6 кейсов — env, SecretStr, обязательные переменные
├── test_engines_mock.py         #   2 кейса — контракт mock-движка (ffmpeg)
├── test_higgsfield_engine.py    #  14 кейсов — HTTP-контракт на httpx.MockTransport
├── test_ledger.py               #  16 кейсов — записи, двойное списание/возврат
├── test_logs.py                 #   4 кейса — JSON и редакция PII
├── test_models.py               #   4 кейса — статическая схема БД
├── test_moderation.py           #  10 кейсов — лимиты фото, EXIF, перекодирование
├── test_order_service.py        # 107 кейсов — стейт-машина (68 нелегальных переходов)
├── test_payments_stub.py        #   2 кейса — инвойс и возврат заглушки
├── test_pricing.py              #  10 кейсов — тариф → цена → заказ
├── test_repo_integration.py     #   4 кейса — PostgreSQL, маркер integration
├── test_result.py               #   5 кейсов — Ok/Err, неизменяемость, match
└── test_seed.py                 #   3 кейса — промпт из файла
```

## Test Structure

**Suite Organization:**

- Классов нет — только функции. В начале модуля: докстринг, константы времени,
  фабрики значений, затем тесты.

```python
# tests/test_order_service.py:31-44,77-82
NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
CREATED_AT = datetime(2026, 1, 15, 11, 0, tzinfo=UTC)


def make_order(status: OrderStatus = OrderStatus.CREATED) -> Order:
    return Order(
        id=1, user_id=10, template_id=20, status=status,
        price_kopecks=9900, credits_cost=2, created_at=CREATED_AT,
    )


@pytest.mark.parametrize(("source", "target"), legal_pairs())
def test_legal_transition_returns_updated_order(source: OrderStatus, target: OrderStatus) -> None:
    order = make_order(source)
    result = transition(order, target, NOW)
    assert result == Ok(expected_order(order, target))
    assert order.status is source
```

**Patterns:**

- Arrange → Act → Assert; одна проверяемая мысль на тест. Вспомогательные
  `make_*` / `build_*` / `encode_*` / `format_*` живут в том же модуле.
- Исходный объект проверяется на неизменность после вызова
  (`assert order.status is source`, `tests/test_order_service.py:82`).
- Чтение `Result`: либо сравнение целиком (`assert ... == Err(...)`), либо `match`
  с `pytest.fail` в ветке-сюрпризе (`tests/test_order_service.py:128-135`).
- Перечисления сравниваются через `is` (`assert order.status is OrderStatus.FAILED`).
- Неизменяемость проверяется явно:

  ```python
  # tests/test_result.py:24-26
  def test_result_is_immutable() -> None:
      with pytest.raises(FrozenInstanceError):
          Ok(1).value = 2
  ```

- Для интеграционных тестов — маркер на весь модуль:
  `pytestmark = pytest.mark.integration` (`tests/test_repo_integration.py:12`).
- Параметризация строится генератором, чтобы покрыть комбинаторику целиком, и
  сортируется для детерминированного порядка:

  ```python
  # tests/test_order_service.py:55-70
  def legal_pairs() -> list[tuple[OrderStatus, OrderStatus]]:
      """Пары сортированы: frozenset не даёт стабильного порядка между процессами."""
      return [
          (source, target)
          for source in OrderStatus
          for target in sorted(TRANSITIONS[source], key=lambda status: status.value)
      ]
  ```

## Mocking

**Framework:** библиотеки моков нет. Используются четыре приёма:

1. `monkeypatch` — окружение и атрибуты модуля (`tests/test_config.py:24-29`,
   `tests/test_seed.py:17-19`).
2. `httpx.MockTransport` — HTTP без сети (`tests/test_higgsfield_engine.py:73-81`).
3. Рукописные фейки за `Protocol` для портов.
4. Инжектированные `sleep` / `now` / `transport` вместо патчей.

**Patterns:**

```python
# tests/test_higgsfield_engine.py:41-81
class SleepRecorder:
    """Фиксирует паузы повторов вместо реального ожидания."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def make_engine(handler, config=None, sleep=None) -> HiggsfieldVideoEngine:
    transport = HttpTransport(
        base_url=BASE_URL, key_id="kid", key_secret="secret",
        timeout_sec=1.0, transport=httpx.MockTransport(handler), sleep=sleep or no_sleep,
    )
    return HiggsfieldVideoEngine(config or make_config(), transport)
```

Проверяется не «был ли вызван мок», а наблюдаемое поведение: последовательность
запросов, тело submit, заголовок авторизации, число и длительность пауз
(`tests/test_higgsfield_engine.py:134-144,195-227`).

**What to Mock:**

- Внешний HTTP — `httpx.MockTransport`, без сети и без реальных ключей.
- Время и паузы — через параметры (`sleep`, `now`) или фиксированные даты.
- Окружение — `monkeypatch.delenv/setenv`, `monkeypatch.chdir(tmp_path)`.
- Файловые корни — `tmp_path` (`tests/test_engines_mock.py:31-39`,
  `tests/test_higgsfield_engine.py:252-274`, `tests/test_seed.py`).

**What NOT to Mock:**

- Домен — вызывается напрямую, без БД, сети и моков; если нужен мок времени, значит
  время не передали параметром (правило из `AGENTS.md:107-113`).
- Pillow — тесты генерируют настоящие байты изображений (`tests/test_moderation.py:23-33`),
  поэтому проверяются реальные лимиты, EXIF и перекодирование.
- PostgreSQL — в интеграционных тестах используется настоящая база, не SQLite и не моки.
- ffmpeg — не мокается: тест либо проверяет понятную ошибку без бинарника
  (`tests/test_engines_mock.py:31-34`), либо пропускается (`:37`).

## Fixtures and Factories

**Test Data:**

- Фабрики — обычные функции, а не fixture-фабрики: `make_order`, `make_entry`,
  `make_tariff`, `make_draft`, `make_spec`, `build_template`, `photo_bytes`,
  `build_record`.
- Значения по умолчанию — валидный минимум; отклонение задаётся аргументом:
  `make_order(credits_cost=0)`, `make_config(poll_max_min=0)`, `PhotoPolicy(max_bytes=10)`.
- Файлы: `encode(image, format, exif)` → `bytes`, без записи на диск
  (`tests/test_moderation.py:23-33`).

**Location:**

- `tests/conftest.py` — только инфраструктура БД.
- Остальные помощники — в модуле, который их использует; общий «fixtures.py» не нужен.

**Схема на воркера (главная фикстура):**

```python
# tests/conftest.py:19-50
DEFAULT_TEST_URL = "postgresql+asyncpg://user:pass@localhost:5433/facechanger_test"
WORKER = os.getenv("PYTEST_XDIST_WORKER", "master")
SCHEMA = f"test_{WORKER}"


def build_engine(schema: str) -> AsyncEngine:
    """Движок, у которого все таблицы живут в схеме конкретного воркера."""
    return create_async_engine(
        test_database_url(),
        connect_args={"server_settings": {"search_path": f"{schema},public"}},
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_schema() -> AsyncIterator[str]:
    engine = build_engine(SCHEMA)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
            await connection.run_sync(Base.metadata.create_all)
    except (SQLAlchemyError, OSError) as error:
        pytest.skip(f"PostgreSQL недоступен: {error}")
    yield SCHEMA
```

- `PYTEST_XDIST_WORKER` даёт каждому процессу `pytest -n auto` свою схему
  `test_<worker>`; таблицы создаются один раз на сессию и удаляются
  `DROP SCHEMA ... CASCADE`. Поэтому интеграционные тесты безопасно идут параллельно.
- Без базы фикстура делает `pytest.skip`, и все зависимые тесты помечаются skipped,
  а не падают.
- URL берётся из `TEST_DATABASE_URL`; дефолт совпадает с сервисом `postgres-test`
  (`localhost:5433`, `docker-compose.yml:77-85`).

**Изоляция теста — транзакция с откатом:**

```python
# tests/conftest.py:53-69
@pytest_asyncio.fixture(loop_scope="function")
async def session(db_schema: str) -> AsyncIterator[AsyncSession]:
    """Сессия в транзакции, которая откатывается после теста."""
    engine = build_engine(db_schema)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        db_session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield db_session
        finally:
            await db_session.close()
            await transaction.rollback()
    await engine.dispose()
```

`join_transaction_mode="create_savepoint"` превращает `session.commit()` приложения
в savepoint, поэтому внешняя транзакция откатывает всё, включая «закоммиченные»
данные; чистить таблицы между тестами не нужно.

**Sync-фикстуры:**

- `clean_env` (`tests/test_config.py:24-29`) удаляет обязательные переменные и
  делает `monkeypatch.chdir(tmp_path)`, чтобы `.env` из корня не подмешивался.

## Coverage

**Requirements:**

- Жёсткого порога нет: `--cov-fail-under` не задан, CI-конфигурации в репозитории нет.
  Покрытие — метрика и отчёт, а не гейт.
- Настроено (`pyproject.toml:61-71`): `source = ["app"]`, `branch = true`,
  миграции исключены (`omit = ["app/db/migrations/*"]`), исключены строки
  `pragma: no cover`, `if TYPE_CHECKING:`, `raise NotImplementedError`;
  `show_missing = true`.

**View Coverage:**

```powershell
.\tasks.ps1 test     # обновляет reports/report.html и reports/coverage/index.html
```

- HTML покрытия — `reports/coverage/index.html`, сырые числа —
  `reports/coverage/status.json`; HTML тестов — `reports/report.html`
  (`--self-contained-html`). Каталог `reports/` в git не попадает (`.gitignore:30`).

**Реальные цифры** (coverage 7.17.2, прогон 06.11.2026, `reports/coverage/status.json`):

| Метрика | Всего | Не покрыто | Покрытие |
|---|---|---|---|
| Statements | 1724 | 571 | **67%** |
| Branches | 278 | 161 (31 частичных) | **42%** |
| Итого | 2002 | 732 | **63%** |

По пакетам:

| Пакет / файл | Statements | Пропущено | Branches | Пропущено | Покрытие |
|---|---|---|---|---|---|
| `app/domain/` | 238 | 0 | 38 | 2 | **99.3%** |
| `app/db/` | 256 | 39 | 16 | 9 | **82.4%** |
| `app/engines/` | 364 | 46 | 72 | 17 | **85.6%** |
| `app/obs/` | 47 | 3 | 10 | 3 | **89.5%** |
| `app/payments/` | 45 | 5 | 2 | 2 | **85.1%** |
| `app/storage/` | 33 | 13 | 0 | 0 | **60.6%** |
| `app/bot/` | 373 | 195 | 82 | 80 | **39.6%** |
| `app/worker/` | 200 | 200 | 38 | 38 | **0%** |
| `app/config.py` | 77 | 4 | 14 | 5 | **90.1%** |
| `app/main_bot.py` | 41 | 18 | 2 | 1 | **55.8%** |
| `app/main_worker.py` | 47 | 47 | 4 | 4 | **0%** |
| `app/clock.py` | 3 | 1 | 0 | 0 | **66.7%** |

Домен покрыт практически полностью: `order_service` (79 statements, 0 пропущенных),
`ledger` (52/0), `result` (8/0) — 100%; `moderation` — 98.6%, `pricing` — 97.8%.
Слабое место — оболочка: воркер и бот.

## Test Types

**Unit Tests:**

- Домен — без БД, сети и моков: `tests/test_order_service.py`, `test_ledger.py`,
  `test_pricing.py`, `test_result.py`, `test_moderation.py`.
- Конфигурация и тексты/логи — `test_config.py`, `test_logs.py`.
- Статическая схема — `test_models.py` читает `Base.metadata`, БД не нужна.
- Сборка диспетчера — `test_bot_wiring.py` обходит `message.handlers` и
  `callback_query.handlers`, сеть не нужна.
- Мета-тест архитектуры — `test_architecture.py` парсит AST домена.
- Платёжная заглушка — `test_payments_stub.py` (async, без сети).
- Промпт шаблона — `test_seed.py` (файлы в `.tmp/seed-test`).

**Integration Tests:**

- `tests/test_repo_integration.py` — 4 теста на реальном PostgreSQL, маркер
  `integration`; проверяют активность заказа до/после оплаты, однократный
  `claim_job` (SKIP LOCKED), нулевую сумму ledger после списания.
- Используют фикстуру `session` с откатом; коммиты приложения становятся savepoint.
- Без `TEST_DATABASE_URL`/PostgreSQL — skipped, не failed.

**E2E Tests:**

- Нет. `ENGINE=mock` + `PAYMENT_PROVIDER=stub` участвуют в юнит-тестах движка и
  заглушки по отдельности, но сквозного сценария «/start → оплата → фото → job →
  видео → delivered» нет. Это расхождение с `AGENTS.md:107-113` зафиксировано ниже.

## Common Patterns

**Async Testing:**

```python
# tests/test_payments_stub.py:22-31
async def test_stub_invoice_contains_success_event() -> None:
    provider = StubPaymentProvider()
    order = make_order()
    invoice = await provider.create_invoice(order)
    assert invoice.payment_id == build_stub_payment_id(order)
    assert invoice.event is not None
```

- `async def test_*` без маркера (`asyncio_mode = "auto"`).
- Асинхронные фикстуры — через `pytest_asyncio.fixture` с явным `loop_scope`
  (`tests/conftest.py:36,53`).
- Блокирующая проверка файла выносится в поток:
  `assert await asyncio.to_thread(is_valid_mp4, Path(result.result_url))`
  (`tests/test_engines_mock.py:44`).

**Error Testing:**

```python
# tests/test_higgsfield_engine.py:195-206
async def test_500_is_retried_exactly_three_times() -> None:
    calls: list[str] = []
    sleeps = SleepRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(500, text="boom")

    with pytest.raises(EngineFailed):
        await make_engine(handler, sleep=sleeps).generate(SPEC)
    assert calls == [MODEL_PATH] * 3
    assert len(sleeps.delays) == 2
```

- Для исключений — `pytest.raises(...)`, при необходимости с `match=` по тексту
  (`tests/test_engines_mock.py:33`, `tests/test_config.py:60`).
- Для `Result` — сравнение с `Err(...)` целиком, без проверки строк.
- Проверяется и побочное поведение: сколько запросов ушло, были ли повторы,
  сколько было пауз (`tests/test_higgsfield_engine.py:170-227`).

**Determinism:**

- Даты фиксированы константами с `tzinfo=UTC` (`NOW`, `CREATED_AT`, `SPEC`).
- Единственное место с реальным временем — `CLAIM_AT = datetime.now(UTC) + timedelta(minutes=1)`
  с объяснением: колонка заполняется серверным `now()`
  (`tests/test_repo_integration.py:15-18`).
- Порядок пар в параметризации сортируется; в контейнере задан `PYTHONHASHSEED=0`
  (`docker-compose.yml:95`).
- Случайность не используется; джиттер проверяется по числу пауз, а не по значению
  (`tests/test_higgsfield_engine.py:195-206`).

**Skip:**

- Внешний бинарник: `@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason=...)`
  (`tests/test_engines_mock.py:37`).
- База: `pytest.skip` внутри `db_schema` (`tests/conftest.py:44-46`) — скипает все
  зависимые интеграционные тесты.

**Как писать новый тест (правила проекта):**

1. Домен — новая чистая функция → новый тест в `tests/test_<module>.py`, без фикстур,
   с `frozen`-значениями и параметризацией всех веток перехода/валидации.
2. Порт (`VideoEngine`, `PaymentProvider`, `Storage`) — фейк за `Protocol` или
   `httpx.MockTransport`; инжектировать `sleep`/`now`, а не патчить модуль.
3. Новый SQL-запрос — интеграционный тест в `tests/test_repo_integration.py`
   с `pytestmark = pytest.mark.integration` и фикстурой `session`.
4. Не мокать время: если без этого не обойтись — время не передали параметром,
   чинить код (`AGENTS.md:107-113`).
5. Новый модуль оболочки без теста допустим только как тонкая проводка; бизнес-ветки
   в нём должны быть покрыты.

## Что не покрыто

Данные — из `reports/coverage/status.json` (06.11.2026). Приоритет: **High** — деньги,
доставка, жизненный цикл заказа; **Medium** — пользовательские ветки; **Low** — обвязка.

| Область | Файл | Покрытие | Что не покрыто и почему это важно |
|---|---|---|---|
| Пайплайн задания | `app/worker/pipeline.py` | **0%** (148 statements, 32 branches) | **High.** Не покрыт весь путь `process_job` → `start_order` → `generate_video` → `deliver`/`fail_job`, включая возврат кредита (`refund_credit:189-199`) и очистку файлов (`cleanup:151-159`). Ошибка здесь = потерянный заказ или незакрытый возврат. |
| Цикл и сборка воркера | `app/worker/loop.py` (35), `app/worker/services.py` (17), `app/main_worker.py` (47) | **0%** | **High.** Конкурентность `run_pool`, обработка падения слота и graceful shutdown (`install_signal_handlers`) не проверяются. |
| Сборка движка | `app/engines/factory.py` | **0%** (19 statements) | **High.** Ветка `ENGINE=higgsfield` и требование ключей не тестируются на уровне фабрики (проверяется только `require_engine_credentials`). |
| Хендлеры бота | `app/bot/handlers/checkout.py` (81), `start.py` (53), `upload.py` (70) | **30% / 29% / 33%**, ветви — 0% | **High.** Не покрыты все отказы: нет согласия, есть активный заказ, нет шаблона, `sales_enabled=false`, `PaymentFailed` с откатом, отказ фото. |
| Фото и хранилище | `app/bot/photo.py` (29), `app/storage/local.py` (22) | **27% / 59%** (28 statements) | **Medium.** `download_photo`, `save_photo`, `LocalStorage.save_photo/delete_photo` не проверяются: ошибка диска и удаление фото после доставки не тестируются. |
| Точка входа бота | `app/main_bot.py` | **56%** (18 statements) | **Medium.** `run_bot`/`main` не покрыты; проверен только `build_dispatcher`. |
| Клавиатуры и middleware | `app/bot/keyboards.py` (13), `throttle.py` (45), `dedupe.py` (16) | **54% / 33% / 50%** (37 statements) | **Medium.** Throttle не вызывается ни разу; дедупликация проверяется только импортом. |
| Ретраи и ошибки транспорта | `app/engines/transport.py` | **89%** (9 statements) | **Medium.** Не покрыты сетевой `httpx.TransportError`, `aclose`, ветка 404, неразборчивый `Retry-After`, битый JSON (`read_json:158-166`). |
| Ветки Higgsfield | `app/engines/higgsfield.py` | **88%** (12 statements, 11 частичных веток) | **Medium.** `submit_path` без модели, fallback-поля upload URL, `extract_status_url`, разбор вложенной ошибки. |
| Сид шаблона | `app/db/seed.py` | **71%** (6 statements) | **Low.** `build_default_template`/`seed_default_template` не покрыты; тестируется только `resolve_prompt`. |
| Часть `repo` | `app/db/repo.py` | **77%** (29 statements) | **Medium.** Без тестов: `load_user`, `record_consent`, `get_default_template`, `load_template`, `count_templates`, `finish_job`, `load_order_ledger`, `record_event`. |
| Фабрика оплаты | `app/payments/factory.py` | **44%** (3 statements) | **Low.** Ветка неизвестного провайдера (`ConfigError`) не проверяется. |
| Строки и форматирование | `app/bot/texts.py` | **68%** (10 statements) | **Low.** `refusal_text` (все ветки отказа) и ветка `format_price` с ненулевыми копейками не покрыты. |

**Сквозной сценарий отсутствует.** `AGENTS.md:107-113` требует «один сквозной тест на
`ENGINE=mock`, `PAYMENT_PROVIDER=stub`», но в `tests/` нет теста, который проходит
`/start → consent → checkout → photo → job → deliver` и проверяет видео и баланс.
`tests/test_engines_mock.py` проверяет только контракт движка, `tests/test_bot_wiring.py` —
только регистрацию хендлеров. Это самый крупный пробел: он закрывает сразу пайплайн,
хендлеры и точку сборки.

**Ветвевое покрытие — узкое место.** 42% branches означает, что даже покрытые строки
часто проверены только по одной ветке: частичные ветки есть в `app/config.py` (5),
`app/engines/higgsfield.py` (11), `app/engines/transport.py` (3), `app/obs/logs.py` (3),
`app/bot/texts.py` (2), `app/db/repo.py` (3), `app/main_bot.py` (1),
`app/domain/moderation.py` (1), `app/domain/pricing.py` (1),
`app/engines/mock.py` (1).

---

*Testing analysis: 2026-11-08*
