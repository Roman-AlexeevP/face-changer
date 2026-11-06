"""Тонкий HTTP-слой Higgsfield: таймауты, повторы и маппинг HTTP-ошибок."""

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

import httpx

from app.engines.base import (
    EngineAuthError,
    EngineBadConfig,
    EngineError,
    EngineFailed,
    EngineInputRejected,
    EngineNoCredits,
)

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
AUTH_STATUSES = frozenset({401, 403})
INPUT_STATUSES = frozenset({400, 422})
RETRY_DELAYS_SEC = (2.0, 5.0, 15.0)
DEFAULT_ATTEMPTS = 3
JITTER_RATIO = 0.2
BODY_SNIPPET_LIMIT = 200

Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class RetryPolicy:
    """Сколько попыток делать и с какими базовыми паузами."""

    attempts: int = DEFAULT_ATTEMPTS
    delays: tuple[float, ...] = RETRY_DELAYS_SEC
    jitter_ratio: float = JITTER_RATIO


class HttpTransport:
    """Async-клиент движка: авторизация, таймауты и повторы в одном месте."""

    def __init__(
        self,
        *,
        base_url: str,
        key_id: str,
        key_secret: str,
        timeout_sec: float,
        transport: httpx.AsyncBaseTransport | None = None,
        retry: RetryPolicy | None = None,
        sleep: Sleeper = asyncio.sleep,
    ) -> None:
        self._retry = retry or RetryPolicy()
        self._sleep = sleep
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Key {key_id}:{key_secret}"},
            timeout=httpx.Timeout(timeout_sec),
            transport=transport,
        )

    async def request(
        self,
        method: str,
        url: str,
        payload: Mapping[str, object] | None = None,
        *,
        files: Mapping[str, tuple[str, bytes]] | None = None,
    ) -> httpx.Response:
        """Выполняет запрос с повторами и возвращает успешный ответ."""
        failure: EngineError | None = None
        for attempt in range(self._retry.attempts):
            response, failure, retry_after = await self._attempt(method, url, payload, files=files)
            if response is not None:
                return response
            if attempt + 1 >= self._retry.attempts:
                break
            await self._sleep(compute_delay(self._retry, attempt, retry_after))
        raise failure or EngineFailed("Higgsfield не ответил")

    async def _attempt(
        self,
        method: str,
        url: str,
        payload: Mapping[str, object] | None,
        *,
        files: Mapping[str, tuple[str, bytes]] | None,
    ) -> tuple[httpx.Response | None, EngineError | None, float | None]:
        try:
            response = await self._client.request(method, url, json=payload, files=files)
        except httpx.TransportError as error:
            return None, EngineFailed(f"сетевая ошибка Higgsfield: {error}"), None
        if not is_retryable(response.status_code):
            raise_for_status(response)
            return response, None, None
        return None, EngineFailed(describe_response(response)), parse_retry_after(response)

    async def aclose(self) -> None:
        """Закрывает соединения клиента."""
        await self._client.aclose()


def is_retryable(status: int) -> bool:
    """Повторяем только перегрузку, лимиты и серверные ошибки."""
    return status in RETRYABLE_STATUSES or status >= 500


def raise_for_status(response: httpx.Response) -> None:
    """Поднимает типизированную ошибку для неповторяемого HTTP-кода."""
    if response.status_code >= 400:
        raise error_for_status(response.status_code, response.text)


def error_for_status(status: int, body: str) -> EngineError:
    """Переводит HTTP-код в одну из ошибок контракта движка."""
    detail = snippet(body)
    if status in AUTH_STATUSES:
        return EngineAuthError(
            f"Higgsfield отклонил ключи (HTTP {status}). Проверьте HF_KEY_ID и HF_KEY_SECRET."
        )
    if status == 402:
        return EngineNoCredits("На счёте Higgsfield закончились кредиты (HTTP 402).")
    if status in INPUT_STATUSES:
        return EngineInputRejected(
            f"Higgsfield отклонил входные данные (HTTP {status}): {detail}. "
            "Нужно другое фото или промпт."
        )
    if status == 404:
        return EngineBadConfig(
            f"Higgsfield вернул 404: проверьте HF_MODEL и HF_UPLOAD_URL. {detail}"
        )
    return EngineFailed(f"Higgsfield ответил ошибкой HTTP {status}: {detail}")


def describe_response(response: httpx.Response) -> str:
    return f"Higgsfield ответил HTTP {response.status_code}: {snippet(response.text)}"


def parse_retry_after(response: httpx.Response) -> float | None:
    """Читает Retry-After в секундах; нераспознанное значение игнорируется."""
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def compute_delay(policy: RetryPolicy, attempt: int, retry_after: float | None) -> float:
    """Пауза повтора: серверный Retry-After важнее нашего backoff с джиттером."""
    if retry_after is not None:
        return retry_after
    base = policy.delays[min(attempt, len(policy.delays) - 1)]
    return base * (1.0 + random.uniform(-policy.jitter_ratio, policy.jitter_ratio))


def read_json(response: httpx.Response) -> dict[str, object]:
    """Разбирает JSON-объект ответа; мусор превращает в EngineFailed."""
    try:
        body = response.json()
    except ValueError as error:
        raise EngineFailed(f"Higgsfield вернул не JSON: {snippet(response.text)}") from error
    if not isinstance(body, dict):
        raise EngineFailed("Higgsfield вернул JSON не объектом")
    return body


def snippet(text: str) -> str:
    """Укорачивает тело ответа для сообщения об ошибке."""
    return " ".join(text.split())[:BODY_SNIPPET_LIMIT]
