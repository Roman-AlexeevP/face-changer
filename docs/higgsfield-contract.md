# Контракт Higgsfield: что предполагаем и что проверить

Документ описывает предположения реализации `app/engines/higgsfield.py` и
`app/engines/transport.py`. Реальные ключи и сеть при разработке недоступны,
поэтому всё, что не подтверждено официальным SDK, помечено как предположение.

## 1. Что уже известно

Из `@higgsfield/client`:

- база `https://api.higgsfield.ai` (`HF_BASE_URL`);
- заголовок `Authorization: Key {KEY_ID}:{KEY_SECRET}`
  (`HF_KEY_ID`, `HF_KEY_SECRET`);
- submit: `POST {base}/{endpoint}` с телом `{"input": {...}}`, где `endpoint` —
  идентификатор модели (`HF_MODEL`);
- ответ submit: `{"request_id": "...", "status": "...", "status_url": "..."}`;
- poll: `GET {status_url}` →
  `{"status": "queued|in_progress|completed|failed|nsfw", "video": {"url": "..."}}`;
- при `failed` и `nsfw` кредиты возвращаются на стороне Higgsfield.

## 2. Что предполагаем (не подтверждено)

| Предположение | Где живёт | Чем рискуем |
|---|---|---|
| `input` содержит `video_url`, `image_url`, `prompt`, `duration`, `resolution` | `build_payload` | submit вернёт 400/422 или проигнорирует поля |
| загрузка медиа — `POST HF_UPLOAD_URL`, multipart с полем `file` | `upload_media` | нужен другой формат: JSON-ссылка, base64, presigned PUT |
| ответ загрузки — `{"url": "..."}` (допускаем также `file_url`, `media_url`) | `extract_upload_url` | не найдём ссылку и упадём с `EngineFailed` |
| `GET {status_url}` без query-параметров | `fetch_status` | потребуется `?id=` или заголовок модели |
| при отсутствии `status_url` статус лежит на `{base}/requests/{request_id}` | `extract_status_url` | 404 → `EngineBadConfig` |
| `nsfw` — терминальный отказ модерации | `map_status` | фактическое имя статуса может отличаться |
| неизвестный статус допустим 3 раза подряд, на четвёртом — `unknown_status` | `poll` | сервис может присылать новый промежуточный статус дольше |
| `failed` содержит код в `error.code`, `error.message`, `error_code` или `error` | `extract_error_code` | код потеряется, останется `engine_failed` |

`HF_TIMEOUT_SEC` применяется и к connect, и к read. Кэш URL видео шаблона
живёт в памяти процесса воркера: если Higgsfield выдаёт временные ссылки,
кэш придётся заменить на `templates.engine_video_url` с TTL (задача 5.2
плана).

## 3. Первый живой запрос: чек-лист

1. Задать `HF_KEY_ID`, `HF_KEY_SECRET`, `HF_MODEL`, `HF_UPLOAD_URL`,
   `HF_BASE_URL` в `.env` (только локально, не в git).
2. Взять готовые публичные URL видео и фото и вызвать `generate` с
   `JobSpec`, где `video_url`/`photo_url` — `https://...` (тогда upload не
   участвует). Это проверит auth, submit и poll отдельно от загрузки.
3. Зафиксировать фактический ответ submit: имя поля с `request_id`, наличие
   `status_url`, полный JSON. Сравнить с `submit`/`extract_status_url`.
4. Дождаться `completed`, проверить, что `video.url` — прямая ссылка на mp4,
   доступная без авторизации, и что она живёт достаточно долго для скачивания.
5. Отдельно проверить `HF_UPLOAD_URL` на локальном файле: метод, Content-Type,
   имя multipart-поля, форму ответа. Проверить, что ссылка из ответа доступна
   Higgsfield.
6. Спровоцировать `402` (или посмотреть баланс) и убедиться, что
   `EngineNoCredits` поднимается, а не общий `EngineFailed`.
7. Спровоцировать `400/422` (например, битым фото) и убедиться, что приходит
   `EngineInputRejected`, а повторов нет.
8. Замерить реальное время генерации: укладывается ли оно в
   `HF_POLL_MAX_MIN` (по умолчанию 8 минут).

## 4. Где править, если схема отличается

| Что менять | Файл | Функция |
|---|---|---|
| поля `input`, их имена и вложенность | `app/engines/higgsfield.py` | `build_payload` |
| endpoint модели | `app/engines/higgsfield.py` | `submit_path` |
| адрес и формат загрузки | `app/engines/higgsfield.py` | `upload_media` |
| имя поля со ссылкой в ответе загрузки | `app/engines/higgsfield.py` | `extract_upload_url` |
| адрес опроса, если нет `status_url` | `app/engines/higgsfield.py` | `extract_status_url` |
| имена статусов и их терминальность | `app/engines/higgsfield.py` | `map_status` |
| поле с кодом ошибки | `app/engines/higgsfield.py` | `extract_error_code` |
| HTTP-коды → типы ошибок | `app/engines/transport.py` | `error_for_status` |
| повторы, `Retry-After`, backoff | `app/engines/transport.py` | `RetryPolicy`, `compute_delay` |
| таймауты | `app/config.py` | `HF_TIMEOUT_SEC` |

После правки схемы обновить этот документ и фикстуры
`tests/test_higgsfield_engine.py`. Контракт `JobSpec`/`EngineResult` менять
не нужно: всё расхождение API укладывается в перечисленные функции.

## 5. Политика отказов (соответствие §7 архитектуры)

| Ответ Higgsfield | Результат движка |
|---|---|
| `completed` + `video.url` | `EngineStatus.DONE` |
| `failed` | `EngineStatus.FAILED`, код из ответа |
| `nsfw` | `EngineStatus.REJECTED`, код `moderated` |
| HTTP 402 | исключение `EngineNoCredits` (код `no_credits`) |
| HTTP 401/403 | `EngineAuthError`, без повторов |
| HTTP 400/422 | `EngineInputRejected`, без повторов |
| HTTP 404 | `EngineBadConfig` (кроме загрузки — там `EngineUnavailable`) |
| HTTP 5xx после 3 попыток | `EngineFailed` |
| сеть после 3 попыток | `EngineFailed` |
| опрос дольше `HF_POLL_MAX_MIN` | `EngineStatus.FAILED`, код `timeout` |
| неизвестный статус 3 раза подряд, четвёртый — отказ | `EngineStatus.FAILED`, код `unknown_status` |

Повторы: 3 попытки на сетевые ошибки, `5xx` и `429`; паузы 2 → 5 → 15 секунд
с джиттером, `Retry-After` имеет приоритет. Остальные коды не повторяются.
Решение о повторной генерации заказа принимает `worker/retry`, а не движок.
