"""Контракт Higgsfield-движка на httpx.MockTransport: без сети и реальных ключей."""

import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from app.engines.base import (
    EngineAuthError,
    EngineFailed,
    EngineInputRejected,
    EngineNoCredits,
    EngineStatus,
    EngineUnavailable,
    JobSpec,
)
from app.engines.higgsfield import HiggsfieldConfig, HiggsfieldVideoEngine, build_payload
from app.engines.transport import HttpTransport

BASE_URL = "https://api.higgsfield.ai"
STATUS_URL = f"{BASE_URL}/requests/req-1"
UPLOAD_URL = f"{BASE_URL}/upload"
MODEL_PATH = "/higgsfield/genjutsu"

SPEC = JobSpec(
    template_key="default",
    video_url="https://cdn.example/template.mp4",
    photo_url="https://cdn.example/photo.jpg",
    prompt="replace face",
    duration_sec=5,
    resolution="720p",
    idempotency_key="1:1",
)

Handler = Callable[[httpx.Request], httpx.Response]


class SleepRecorder:
    """Фиксирует паузы повторов вместо реального ожидания."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


async def no_sleep(_: float) -> None:
    return None


def make_config(**overrides: object) -> HiggsfieldConfig:
    config = HiggsfieldConfig(
        base_url=BASE_URL,
        model="higgsfield/genjutsu",
        upload_url=UPLOAD_URL,
        key_id="kid",
        key_secret="secret",
        poll_interval_sec=0.0,
        poll_max_min=8,
    )
    return replace(config, **overrides)


def make_engine(
    handler: Handler,
    config: HiggsfieldConfig | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> HiggsfieldVideoEngine:
    transport = HttpTransport(
        base_url=BASE_URL,
        key_id="kid",
        key_secret="secret",
        timeout_sec=1.0,
        transport=httpx.MockTransport(handler),
        sleep=sleep or no_sleep,
    )
    return HiggsfieldVideoEngine(config or make_config(), transport)


def submit_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"request_id": "req-1", "status": "queued", "status_url": STATUS_URL},
    )


def make_status_handler(statuses: list[dict[str, object]], polls: list[str]) -> Handler:
    queue = iter(statuses)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return submit_response()
        polls.append(request.url.path)
        return httpx.Response(200, json=next(queue))

    return handler


def test_build_payload_contains_all_input_fields() -> None:
    assert build_payload(SPEC) == {
        "input": {
            "video_url": SPEC.video_url,
            "image_url": SPEC.photo_url,
            "prompt": SPEC.prompt,
            "duration": SPEC.duration_sec,
            "resolution": SPEC.resolution,
        }
    }


async def test_generate_submits_polls_and_returns_video() -> None:
    calls: list[str] = []
    bodies: list[dict[str, object]] = []
    auth_headers: list[str | None] = []
    statuses = iter(
        [
            {"status": "queued"},
            {"status": "completed", "video": {"url": "https://cdn.example/result.mp4"}},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        auth_headers.append(request.headers.get("Authorization"))
        if request.method == "POST":
            bodies.append(json.loads(request.content))
            return submit_response()
        return httpx.Response(200, json=next(statuses))

    result = await make_engine(handler).generate(SPEC)

    assert result.status is EngineStatus.DONE
    assert result.result_url == "https://cdn.example/result.mp4"
    assert bodies == [build_payload(SPEC)]
    assert set(auth_headers) == {"Key kid:secret"}
    assert calls == [
        f"POST {MODEL_PATH}",
        "GET /requests/req-1",
        "GET /requests/req-1",
    ]


async def test_failed_status_returns_failed_with_service_code() -> None:
    polls: list[str] = []
    handler = make_status_handler(
        [{"status": "failed", "error": {"code": "face_not_found"}}], polls
    )

    result = await make_engine(handler).generate(SPEC)

    assert result.status is EngineStatus.FAILED
    assert result.error_code == "face_not_found"


async def test_nsfw_status_is_rejected_without_retry() -> None:
    polls: list[str] = []
    handler = make_status_handler([{"status": "nsfw"}], polls)

    result = await make_engine(handler).generate(SPEC)

    assert result.status is EngineStatus.REJECTED
    assert result.error_code == "moderated"
    assert polls == ["/requests/req-1"]


async def test_402_raises_no_credits_without_retries() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(402, json={"error": "no credits"})

    with pytest.raises(EngineNoCredits):
        await make_engine(handler).generate(SPEC)
    assert calls == [MODEL_PATH]


@pytest.mark.parametrize(("status", "error"), [(401, EngineAuthError), (422, EngineInputRejected)])
async def test_client_errors_are_not_retried(status: int, error: type[Exception]) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(status, json={"error": "rejected"})

    with pytest.raises(error):
        await make_engine(handler).generate(SPEC)
    assert calls == [MODEL_PATH]


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


async def test_429_respects_retry_after_and_retries() -> None:
    posts: list[str] = []
    sleeps = SleepRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200, json={"status": "completed", "video": {"url": "https://cdn.example/ok.mp4"}}
            )
        posts.append(request.url.path)
        if len(posts) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, text="slow down")
        return submit_response()

    result = await make_engine(handler, sleep=sleeps).generate(SPEC)

    assert result.status is EngineStatus.DONE
    assert posts == [MODEL_PATH, MODEL_PATH]
    assert sleeps.delays == [7.0]


async def test_poll_timeout_returns_failed_timeout() -> None:
    polls: list[str] = []
    handler = make_status_handler([{"status": "queued"}], polls)

    result = await make_engine(handler, config=make_config(poll_max_min=0)).generate(SPEC)

    assert result.status is EngineStatus.FAILED
    assert result.error_code == "timeout"
    assert len(polls) == 1


async def test_fourth_unknown_status_fails() -> None:
    polls: list[str] = []
    handler = make_status_handler([{"status": "strange"}] * 4, polls)

    result = await make_engine(handler).generate(SPEC)

    assert result.status is EngineStatus.FAILED
    assert result.error_code == "unknown_status"
    assert len(polls) == 4


async def test_template_video_is_uploaded_once(tmp_path: Path) -> None:
    template = tmp_path / "template.mp4"
    template.write_bytes(b"template-video")
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"photo-bytes")
    spec = replace(SPEC, video_url=str(template), photo_url=str(photo))
    uploads: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload":
            uploads.append(request)
            return httpx.Response(200, json={"url": "https://cdn.example/uploaded"})
        if request.method == "POST":
            return submit_response()
        return httpx.Response(
            200, json={"status": "completed", "video": {"url": "https://cdn.example/out.mp4"}}
        )

    engine = make_engine(handler)
    await engine.generate(spec)
    await engine.generate(spec)

    assert len(uploads) == 3


async def test_missing_upload_url_raises_unavailable(tmp_path: Path) -> None:
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"photo-bytes")
    spec = replace(SPEC, photo_url=str(photo))
    engine = make_engine(lambda _: httpx.Response(200), config=make_config(upload_url=""))

    with pytest.raises(EngineUnavailable, match="HF_UPLOAD_URL"):
        await engine.generate(spec)


async def test_upload_404_raises_unavailable_with_hint(tmp_path: Path) -> None:
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"photo-bytes")
    spec = replace(SPEC, photo_url=str(photo))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    with pytest.raises(EngineUnavailable, match="HF_UPLOAD_URL"):
        await make_engine(handler).generate(spec)
