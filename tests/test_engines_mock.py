"""Контракт mock-движка: mp4 через ffmpeg или понятная ошибка без него."""

import asyncio
import shutil
from pathlib import Path

import pytest

from app.engines.base import EngineStatus, EngineUnavailable, JobSpec
from app.engines.mock import MockVideoEngine

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def make_spec() -> JobSpec:
    return JobSpec(
        template_key="default",
        video_url="templates/default/source.mp4",
        photo_url="photo-1.jpg",
        prompt="mock",
        duration_sec=5,
        resolution="720p",
        idempotency_key="1:1",
    )


def is_valid_mp4(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0 and path.read_bytes()[4:8] == b"ftyp"


async def test_missing_ffmpeg_raises_clear_error(tmp_path: Path) -> None:
    engine = MockVideoEngine(tmp_path, ffmpeg="definitely-missing-ffmpeg")
    with pytest.raises(EngineUnavailable, match="ffmpeg"):
        await engine.generate(make_spec())


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg недоступен в окружении")
async def test_generate_returns_five_second_mp4(tmp_path: Path) -> None:
    engine = MockVideoEngine(tmp_path)
    result = await engine.generate(make_spec())

    assert result.status is EngineStatus.DONE
    assert result.result_url is not None
    assert await asyncio.to_thread(is_valid_mp4, Path(result.result_url))
