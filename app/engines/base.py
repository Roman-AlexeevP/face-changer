"""Контракт видео-движка: задание, результат и типы ошибок."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

type SubmitHook = Callable[[str], Awaitable[None]]


class EngineStatus(StrEnum):
    """Терминальные и промежуточные статусы генерации из architecture §4."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    REJECTED = "rejected"
    NO_CREDITS = "no_credits"


@dataclass(frozen=True)
class JobSpec:
    """Всё, что движку нужно знать для одной генерации."""

    template_key: str
    video_url: str
    photo_url: str
    prompt: str
    duration_sec: int
    resolution: str
    idempotency_key: str
    request_id: str | None = None


@dataclass(frozen=True)
class EngineResult:
    """Ответ движка; ``result_url`` для mock указывает на локальный файл."""

    status: EngineStatus
    result_url: str | None = None
    error_code: str | None = None
    raw: dict[str, object] | None = None


class EngineError(RuntimeError):
    """Движок не смог выдать результат; сообщение идёт в лог."""

    code = "engine_error"


class EngineUnavailable(EngineError):
    """Движок не установлен или не настроен."""

    code = "engine_unavailable"


class EngineFailed(EngineError):
    """Движок запустился, но завершился ошибкой."""

    code = "engine_failed"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class EngineAuthError(EngineError):
    """Движок отклонил ключи доступа (HTTP 401/403)."""

    code = "engine_auth"


class EngineNoCredits(EngineError):
    """На счёте движка закончились кредиты (HTTP 402)."""

    code = "no_credits"


class EngineInputRejected(EngineError):
    """Движок отклонил входные данные: фото, промпт или параметры (HTTP 400/422)."""

    code = "bad_input"


class EngineBadConfig(EngineError):
    """Модель или адрес загрузки медиа заданы неверно (HTTP 404, пустой HF_MODEL)."""

    code = "engine_bad_config"


class VideoEngine(Protocol):
    """Порт генерации: mock отвечает сразу, реальный движок — через poll."""

    async def generate(self, spec: JobSpec, *, on_submit: SubmitHook | None = None) -> EngineResult:
        """Выполняет одну генерацию и возвращает терминальный результат."""
        ...
