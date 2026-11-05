"""Сид дефолтного шаблона: без него сценарий заказа не стартует."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import models, repo

DEFAULT_TEMPLATE_KEY = "default"
DEFAULT_TITLE = "Лицо в видео"
DEFAULT_PROMPT = "Заменить лицо в видео-шаблоне, сохранить мимику и освещение."
DEFAULT_SOURCE_PATH = "templates/default/source.mp4"
DEFAULT_DURATION_SEC = 5
DEFAULT_RESOLUTION = "720p"


def build_default_template(settings: Settings) -> models.Template:
    """Собирает единственный шаблон MVP из цен в настройках."""
    return models.Template(
        key=DEFAULT_TEMPLATE_KEY,
        title=DEFAULT_TITLE,
        source_path=DEFAULT_SOURCE_PATH,
        prompt=DEFAULT_PROMPT,
        engine_model=settings.hf_model or None,
        duration_sec=DEFAULT_DURATION_SEC,
        resolution=DEFAULT_RESOLUTION,
        credits_cost=settings.credits_per_order,
        price_kopecks=settings.price_kopecks,
        is_active=True,
    )


async def seed_default_template(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """Вставляет шаблон, только если таблица шаблонов пуста."""
    async with session_factory() as session:
        if await repo.count_templates(session) > 0:
            return
        session.add(build_default_template(settings))
        await session.commit()
