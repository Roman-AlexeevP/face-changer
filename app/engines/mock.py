"""Mock-движок: генерирует 5-секундный mp4 через ffmpeg и lavfi."""

import asyncio
import os
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.engines.base import (
    EngineFailed,
    EngineResult,
    EngineStatus,
    EngineUnavailable,
    JobSpec,
)

WIDTH = 720
HEIGHT = 1280
FPS = 30
MOCK_TEXT = "MOCK"
FONT_SIZE = 150
STROKE_WIDTH = 6
OVERLAY_FILTER = "[0:v][1:v]overlay=(W-w)/2:(H-h)/2,format=yuv420p"


@dataclass(frozen=True)
class MockRender:
    """Параметры одного рендера: что наложить и куда положить."""

    overlay: Path
    output: Path
    duration_sec: int


@dataclass(frozen=True)
class MockVideoEngine:
    """Заглушка движка: локальный mp4 с тестовым паттерном и надписью MOCK."""

    work_dir: Path
    ffmpeg: str = "ffmpeg"
    duration_sec: int = 5

    async def generate(self, spec: JobSpec) -> EngineResult:
        binary = shutil.which(self.ffmpeg)
        if binary is None:
            raise EngineUnavailable("ffmpeg не найден: установите ffmpeg или проверьте PATH.")
        output = create_temp_file(self.work_dir, ".mp4")
        overlay = create_overlay_image(self.work_dir)
        try:
            render = MockRender(overlay, output, self.duration_sec)
            await run_ffmpeg(build_ffmpeg_command(binary, render))
        except Exception:
            output.unlink(missing_ok=True)
            raise
        finally:
            overlay.unlink(missing_ok=True)
        raw = {"duration_sec": self.duration_sec, "template_key": spec.template_key}
        return EngineResult(EngineStatus.DONE, str(output), None, raw)


def create_temp_file(directory: Path, suffix: str) -> Path:
    """Создаёт пустой файл во временном каталоге хранилища."""
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="mock-", suffix=suffix, dir=directory)
    os.close(descriptor)
    return Path(name)


def create_overlay_image(directory: Path) -> Path:
    """Рисует полупрозрачную надпись MOCK для наложения на тестовый паттерн."""
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    canvas = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=FONT_SIZE)
    left, top, right, bottom = canvas.textbbox(
        (0, 0), MOCK_TEXT, font=font, stroke_width=STROKE_WIDTH
    )
    position = ((WIDTH - right + left) // 2, (HEIGHT - bottom + top) // 2)
    canvas.text(
        position,
        MOCK_TEXT,
        font=font,
        fill="white",
        stroke_width=STROKE_WIDTH,
        stroke_fill="black",
    )
    path = create_temp_file(directory, ".png")
    image.save(path, format="PNG")
    return path


def build_ffmpeg_command(binary: str, render: MockRender) -> list[str]:
    """Собирает команду: testsrc2 + наложенная надпись, H.264, faststart."""
    command = [binary, "-y", "-hide_banner", "-loglevel", "error"]
    command += ["-f", "lavfi", "-i", build_lavfi_source(render.duration_sec)]
    command += ["-i", str(render.overlay), "-filter_complex", OVERLAY_FILTER]
    command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
    command += ["-movflags", "+faststart", "-an", str(render.output)]
    return command


def build_lavfi_source(duration_sec: int) -> str:
    return f"testsrc2=size={WIDTH}x{HEIGHT}:rate={FPS}:duration={duration_sec}"


async def run_ffmpeg(command: Sequence[str]) -> None:
    """Запускает ffmpeg без shell и превращает ненулевой код в EngineFailed."""
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        tail = stderr.decode("utf-8", errors="replace").strip()[-400:]
        raise EngineFailed(f"ffmpeg завершился с кодом {process.returncode}: {tail}")
