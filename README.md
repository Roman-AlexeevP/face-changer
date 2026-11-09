# face-changer

Telegram-бот: пользователь присылает фото, бот вставляет лицо в видео-шаблон
через Higgsfield API (Genjutsu) и возвращает готовое видео.

Стадия: **внешние интеграционные гейты.** Mock/stub-сценарий уже работает в
Telegram и сохранён как регрессионная база. Следующая фаза проверяет live
Higgsfield и минимально доступную оплату; нужны внешние credentials и тестовые
данные, а платёжный провайдер выбирается по фактической доступности.

## Документы

| Документ | Что внутри |
|---|---|
| [`.planning/PROJECT.md`](.planning/PROJECT.md) | контекст, границы MVP, ключевые решения |
| [`.planning/REQUIREMENTS.md`](.planning/REQUIREMENTS.md) | требования v1 с REQ-ID и матрицей ошибок |
| [`.planning/ROADMAP.md`](.planning/ROADMAP.md) | фазы, критерии приёмки, трассировка |
| [`docs/architecture.md`](docs/architecture.md) | компоненты, контракты, схема БД, потоки |
| [`docs/stack.md`](docs/stack.md) | стек, env-переменные, структура |
| [`docs/implementation-plan.md`](docs/implementation-plan.md) | исторический исходный план этапов |
| [`docs/higgsfield-contract.md`](docs/higgsfield-contract.md) | что подтверждено и что проверить |
| [`docs/archive/openspec/`](docs/archive/openspec/) | исторические требования MVP (архив, не действуют) |

## Команды

Всё выполняется в контейнерах — на хосте не нужны ни Python, ни ffmpeg, ни make.

```powershell
.\tasks.cmd up        # поднять postgres, bot, worker
.\tasks.cmd migrate   # одноразовая джоба: alembic upgrade head
.\tasks.cmd test      # тесты + HTML-отчёт в reports/
.\tasks.cmd lint      # ruff check + format --check
.\tasks.cmd down      # остановить
```

`tasks.cmd` — тонкий шим над `tasks.ps1`: нужен потому, что на Windows
PowerShell по умолчанию запрещает запуск `.ps1`. `tasks.ps1` сохранён в UTF-8
с BOM, чтобы Windows PowerShell 5.1 корректно читал кириллицу.

### Тесты

`tasks.cmd test` поднимает отдельную тестовую базу `postgres-test` (на tmpfs),
гоняет pytest в параллельных воркерах и собирает покрытие:

- [`reports/report.html`](reports/report.html) — отчёт по тестам;
- `reports/coverage/index.html` — покрытие.

Интеграционные тесты помечены `-m integration`. Каждый воркер получает свою
схему в тестовой базе (`test_gw0`, `test_gw1`, …), а внутри теста всё живёт в
транзакции, которая откатывается, — поэтому тесты не мешают друг другу и идут
параллельно.

Без обёртки то же самое:

```bash
docker compose up -d --build
docker compose --profile tools run --rm migrate
docker compose --profile test run --rm tests
```

Миграции — отдельной одноразовой джобой (`migrate`, профиль `tools`), а не в
entrypoint приложения: при нескольких репликах они бы выполнялись параллельно.

## С чего начать

1. Открыть [`.planning/ROADMAP.md`](.planning/ROADMAP.md) — текущую Phase 2 и
   milestones внешних интеграций.
2. Сверить задачу с [`.planning/REQUIREMENTS.md`](.planning/REQUIREMENTS.md).
3. Для Higgsfield пройти чек-лист
   [`docs/higgsfield-contract.md`](docs/higgsfield-contract.md).
4. Для оплаты сначала зафиксировать доступный провайдер и транспорт.
5. Для разработки без внешних ключей — `ENGINE=mock`,
   `PAYMENT_PROVIDER=stub`.

## Процесс

Проект ведётся по GSD. Требования — в `.planning/REQUIREMENTS.md`, фазы — в
`.planning/ROADMAP.md`, текущее состояние — в `.planning/STATE.md`, план фазы —
`.planning/phases/<NN-name>/PLAN.md`.

Исторические спецификации OpenSpec сохранены в
[`docs/archive/openspec/`](docs/archive/openspec/) и не являются действующими.
Новая функциональность начинается с требования в `.planning/REQUIREMENTS.md`,
а не с правки кода.
