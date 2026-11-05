"""Контракт видео-движка: задание, результат и типы ошибок."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


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


class VideoEngine(Protocol):
    """Порт генерации: mock отвечает сразу, реальный движок — через poll."""

    async def generate(self, spec: JobSpec) -> EngineResult:
        """Выполняет одну генерацию и возвращает терминальный результат."""
        ...
