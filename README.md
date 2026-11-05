# face-changer

Telegram-бот: пользователь присылает фото, бот вставляет лицо в видео-шаблон
через Higgsfield API (Genjutsu) и возвращает готовое видео.

Стадия: **MVP не начат**, документация и план готовы.

## Документы

| Документ | Что внутри |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | компоненты, контракты, схема БД, потоки, обработка отказов |
| [`docs/stack.md`](docs/stack.md) | стек, обоснование, env-переменные, структура репозитория |
| [`docs/implementation-plan.md`](docs/implementation-plan.md) | этапы, календарь, гейты, риски |
| [`openspec/project.md`](openspec/project.md) | контекст, границы MVP, соглашения проекта |
| [`openspec/changes/mvp-001-core-flow/`](openspec/changes/mvp-001-core-flow/) | предложение, дизайн, задачи и требования MVP |

## Спецификации

Требования живут в изменении `mvp-001-core-flow` как дельта, пока изменение не
заархивировано. После реализации `openspec archive` перенесёт их в
`openspec/specs/` — это штатный жизненный цикл OpenSpec.

- [`tg-entry`](openspec/changes/mvp-001-core-flow/specs/tg-entry/spec.md) — вход, согласие, приём фото
- [`template-catalog`](openspec/changes/mvp-001-core-flow/specs/template-catalog/spec.md) — шаблон как данные
- [`generation`](openspec/changes/mvp-001-core-flow/specs/generation/spec.md) — submit, polling, ретраи
- [`billing`](openspec/changes/mvp-001-core-flow/specs/billing/spec.md) — заказ, заглушка оплаты, ledger
- [`delivery`](openspec/changes/mvp-001-core-flow/specs/delivery/spec.md) — выдача видео
- [`privacy-retention`](openspec/changes/mvp-001-core-flow/specs/privacy-retention/spec.md) — удаление фото, логи без PII
- [`ops`](openspec/changes/mvp-001-core-flow/specs/ops/spec.md) — админка, гейты, алерты

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
PowerShell по умолчанию запрещает запуск `.ps1`. Если политика у вас
разрешена, можно вызывать `.\tasks.ps1` напрямую.

Без обёртки то же самое:

```bash
docker compose up -d --build
docker compose --profile tools run --rm migrate
docker compose --profile test run --rm tests
```

Миграции — отдельной одноразовой джобой (`migrate`, профиль `tools`), а не в
entrypoint приложения: при нескольких репликах они бы выполнялись параллельно.

## С чего начать

1. Прочитать `docs/implementation-plan.md` — этап 0.
2. Пройти проверку движка (0,5 дня) — это гейт для всего остального.
3. Вернуться в `openspec/changes/mvp-001-core-flow/tasks.md` и идти по списку.

## Процесс

Проект инициализирован под OpenSpec CLI и проходит проверку:

```
openspec validate --all     # ✓ change/mvp-001-core-flow
openspec status --change mvp-001-core-flow
openspec list               # mvp-001-core-flow  0/63 tasks
```

`openspec/specs/` — текущая правда (пока пусто, система не реализована);
`openspec/changes/<id>/` — предлагаемые изменения: `proposal.md`, `design.md`,
`tasks.md` и `specs/` с дельтой требований (`## ADDED Requirements`).

Новая функциональность начинается с нового каталога в `changes/`, а не с
правки кода. После реализации изменение архивируется, и дельта переезжает в
`openspec/specs/`.
