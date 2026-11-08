"""Движок Higgsfield: загрузка медиа, submit и polling до терминального статуса."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from app.engines.base import (
    EngineBadConfig,
    EngineFailed,
    EngineResult,
    EngineStatus,
    EngineUnavailable,
    JobSpec,
    SubmitHook,
)
from app.engines.transport import HttpTransport, read_json

SECONDS_PER_MINUTE = 60.0
MAX_UNKNOWN_STATUSES = 3
IN_PROGRESS_STATUSES = frozenset({"queued", "in_progress", "processing", "pending"})
UPLOAD_URL_FIELDS = ("url", "file_url", "media_url")
REMOTE_PREFIXES = ("http://", "https://")
DEFAULT_TIMEOUT_SEC = 30.0

Sleeper = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


@dataclass(frozen=True)
class HiggsfieldConfig:
    """Всё, что движку нужно от настроек HF_*."""

    base_url: str
    model: str
    upload_url: str
    # Секреты исключены из repr: конфиг может попасть в лог целиком.
    key_id: str = field(repr=False)
    key_secret: str = field(repr=False)
    timeout_sec: float = DEFAULT_TIMEOUT_SEC
    poll_interval_sec: float = 3.0
    poll_max_min: float = 8.0


@dataclass(frozen=True)
class Submission:
    """Ответ на submit: по каким данным потом опрашивать статус."""

    request_id: str
    status_url: str


@dataclass(frozen=True)
class HiggsfieldVideoEngine:
    """Реальный движок: upload → submit → poll, без бизнес-правил."""

    config: HiggsfieldConfig
    transport: HttpTransport
    now: Clock = time.monotonic
    sleep: Sleeper = asyncio.sleep
    video_urls: dict[str, str] = field(default_factory=dict, repr=False, compare=False)

    async def generate(self, spec: JobSpec, *, on_submit: SubmitHook | None = None) -> EngineResult:
        """Проводит одну генерацию от загрузки медиа до терминального ответа."""
        if spec.request_id:
            return await self.poll(
                Submission(spec.request_id, self.status_url_for(spec.request_id))
            )
        media = replace(
            spec,
            video_url=await self.ensure_video_url(spec),
            photo_url=await upload_media(self.transport, self.config.upload_url, spec.photo_url),
        )
        submission = await self.submit(build_payload(media))
        if on_submit is not None:
            await on_submit(submission.request_id)
        return await self.poll(submission)

    def status_url_for(self, request_id: str) -> str:
        """Собирает адрес статуса для resume, когда status_url не сохранён."""
        return extract_status_url({}, self.config.base_url, request_id)

    async def ensure_video_url(self, spec: JobSpec) -> str:
        """Отдаёт URL видео шаблона из кэша или загружает его один раз."""
        cached = self.video_urls.get(spec.template_key)
        if cached is not None:
            return cached
        uploaded = await upload_media(self.transport, self.config.upload_url, spec.video_url)
        self.video_urls[spec.template_key] = uploaded
        return uploaded

    async def submit(self, payload: Mapping[str, object]) -> Submission:
        """Отправляет задание и возвращает идентификатор запроса."""
        response = await self.transport.request("POST", self.submit_path(), payload)
        body = read_json(response)
        request_id = body.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise EngineFailed("Higgsfield не вернул request_id на submit.")
        return Submission(request_id, extract_status_url(body, self.config.base_url, request_id))

    def submit_path(self) -> str:
        """Endpoint модели — её идентификатор из HF_MODEL."""
        model = self.config.model.strip().strip("/")
        if not model:
            raise EngineBadConfig("HF_MODEL не задан: укажите идентификатор модели Higgsfield.")
        return f"/{model}"

    async def poll(self, submission: Submission) -> EngineResult:
        """Опрашивает статус до терминального ответа или таймаута."""
        deadline = self.now() + self.config.poll_max_min * SECONDS_PER_MINUTE
        unknown = 0
        while True:
            body = await self.fetch_status(submission.status_url)
            result, unknown = map_status(body, unknown)
            if result is not None:
                return result
            if unknown > MAX_UNKNOWN_STATUSES:
                return failed_result("unknown_status", body)
            if self.now() >= deadline:
                return failed_result("timeout", body)
            await self.sleep(self.config.poll_interval_sec)

    async def fetch_status(self, status_url: str) -> dict[str, object]:
        return read_json(await self.transport.request("GET", status_url))

    async def aclose(self) -> None:
        """Закрывает HTTP-клиент движка."""
        await self.transport.aclose()


async def upload_media(transport: HttpTransport, upload_url: str, source: str) -> str:
    """Загружает локальный файл в Higgsfield и возвращает публичную ссылку."""
    if is_remote_url(source):
        return source
    if not upload_url.strip():
        raise EngineUnavailable("HF_UPLOAD_URL не задан: укажите адрес загрузки медиа Higgsfield.")
    path = Path(source)
    data = await read_file(path)
    try:
        response = await transport.request("POST", upload_url, files={"file": (path.name, data)})
    except EngineBadConfig as error:
        raise EngineUnavailable(build_upload_hint(upload_url)) from error
    return extract_upload_url(read_json(response))


async def read_file(path: Path) -> bytes:
    try:
        return await asyncio.to_thread(path.read_bytes)
    except OSError as error:
        raise EngineFailed(f"не удалось прочитать файл {path.name}: {error}") from error


def build_upload_hint(upload_url: str) -> str:
    return (
        f"HF_UPLOAD_URL={upload_url} отвечает 404. "
        "Укажите актуальный адрес загрузки медиа Higgsfield в HF_UPLOAD_URL."
    )


def is_remote_url(source: str) -> bool:
    return source.lower().startswith(REMOTE_PREFIXES)


def extract_upload_url(body: Mapping[str, object]) -> str:
    """Достаёт ссылку из ответа загрузки; имя поля пока предполагаемое."""
    for name in UPLOAD_URL_FIELDS:
        value = body.get(name)
        if isinstance(value, str) and value:
            return value
    raise EngineFailed("Ответ загрузки Higgsfield не содержит ссылки на медиа.")


def build_payload(spec: JobSpec) -> dict[str, object]:
    """Собирает тело submit: единственное место, где описана схема input."""
    return {
        "input": {
            "video_url": spec.video_url,
            "image_url": spec.photo_url,
            "prompt": spec.prompt,
            "duration": spec.duration_sec,
            "resolution": spec.resolution,
        }
    }


def extract_status_url(body: Mapping[str, object], base_url: str, request_id: str) -> str:
    """Берёт status_url из ответа или собирает по известному шаблону."""
    value = body.get("status_url")
    if isinstance(value, str) and value:
        return value
    return f"{base_url.rstrip('/')}/requests/{request_id}"


def map_status(body: Mapping[str, object], unknown_count: int) -> tuple[EngineResult | None, int]:
    """Переводит статус Higgsfield в результат; None — ещё не терминальный."""
    status = str(body.get("status", "")).strip().lower()
    if status == "completed":
        return completed_result(body), 0
    if status == "failed":
        return failed_result(extract_error_code(body), body), 0
    if status == "nsfw":
        return EngineResult(EngineStatus.REJECTED, error_code="moderated", raw=dict(body)), 0
    if status in IN_PROGRESS_STATUSES:
        return None, 0
    return None, unknown_count + 1


def completed_result(body: Mapping[str, object]) -> EngineResult:
    url = extract_video_url(body)
    if url is None:
        return failed_result("bad_response", body)
    return EngineResult(EngineStatus.DONE, url, None, dict(body))


def failed_result(code: str, body: Mapping[str, object]) -> EngineResult:
    return EngineResult(EngineStatus.FAILED, error_code=code, raw=dict(body))


def extract_video_url(body: Mapping[str, object]) -> str | None:
    video = body.get("video")
    if not isinstance(video, dict):
        return None
    url = video.get("url")
    return url if isinstance(url, str) and url else None


def extract_error_code(body: Mapping[str, object]) -> str:
    direct = body.get("error_code")
    if isinstance(direct, str) and direct:
        return direct
    return nested_error_code(body.get("error"))


def nested_error_code(error: object) -> str:
    if isinstance(error, str) and error:
        return error
    if isinstance(error, dict):
        code = error.get("code") or error.get("message")
        if isinstance(code, str) and code:
            return code
    return "engine_failed"
