"""Промпт шаблона: можно задать файлом рядом с видео, без правки кода."""

import os
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import ConfigError, Settings
from app.db import models, repo, seed

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5433/facechanger_test"

# Каждый процесс pytest (включая воркеры xdist) пишет в свой каталог:
# фиксированный путь даёт гонку между тестами.
SCRATCH = Path(".tmp") / f"seed-test-{os.getpid()}"


def write_prompt_file(text: str) -> Path:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = SCRATCH / "prompt.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setattr(seed, "PROMPT_FILE", SCRATCH / "absent.txt")
    assert seed.resolve_prompt("базовый") == "базовый"


def test_prompt_is_read_from_file(monkeypatch) -> None:
    path = write_prompt_file("  свой промпт для Genjutsu \n")
    monkeypatch.setattr(seed, "PROMPT_FILE", path)
    assert seed.resolve_prompt("базовый") == "свой промпт для Genjutsu"


def test_blank_file_falls_back_to_default(monkeypatch) -> None:
    path = write_prompt_file("   \n\n")
    monkeypatch.setattr(seed, "PROMPT_FILE", path)
    assert seed.resolve_prompt("базовый") == "базовый"


@pytest.mark.integration
async def test_seed_upserts_prompt_and_keeps_one_default(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("первый промпт", encoding="utf-8")
    monkeypatch.setattr(seed, "PROMPT_FILE", prompt)
    settings = Settings(database_url=DATABASE_URL, storage_dir=tmp_path)

    await seed.seed_default_template(session_factory, settings)
    template = await repo.get_template_by_key(session, "default")
    assert template is not None
    assert template.prompt == "первый промпт"
    assert template.is_default is True
    assert await repo.count_default_templates(session) == 1

    prompt.write_text("второй промпт", encoding="utf-8")
    await seed.seed_default_template(session_factory, settings)

    await session.refresh(template)
    assert template.prompt == "второй промпт"
    assert await repo.count_default_templates(session) == 1


@pytest.mark.integration
async def test_two_defaults_are_config_error(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    for key in ("one", "two"):
        session.add(
            models.Template(
                key=key,
                title=key,
                source_path=f"templates/{key}/source.mp4",
                prompt="p",
                duration_sec=5,
                resolution="720p",
                credits_cost=1,
                price_kopecks=100,
                is_active=True,
                is_default=True,
            )
        )
    await session.flush()
    settings = Settings(database_url=DATABASE_URL, storage_dir=tmp_path)

    with pytest.raises(ConfigError, match="is_default"):
        await seed.seed_default_template(session_factory, settings)
