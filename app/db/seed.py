"""Сид дефолтного шаблона: upsert по key и один шаблон по умолчанию."""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import ConfigError, Settings
from app.db import models, repo

DEFAULT_TEMPLATE_KEY = "default"
DEFAULT_TITLE = "Лицо в видео"
DEFAULT_PROMPT = "Заменить лицо в видео-шаблоне, сохранить мимику и освещение."
DEFAULT_SOURCE_PATH = "templates/default/source.mp4"
DEFAULT_DURATION_SEC = 5
DEFAULT_RESOLUTION = "720p"

# Промпт можно положить текстом рядом с видео — без правки кода и пересборки.
PROMPT_FILE = Path("templates/default/prompt.txt")


def resolve_prompt(default: str) -> str:
    """Читает промпт из файла шаблона; пустой или отсутствующий — берёт default."""
    if not PROMPT_FILE.is_file():
        return default
    text = PROMPT_FILE.read_text(encoding="utf-8").strip()
    return text or default


def build_default_template(settings: Settings, *, is_default: bool = True) -> models.Template:
    """Собирает единственный шаблон MVP из цен в настройках."""
    template = models.Template(
        key=DEFAULT_TEMPLATE_KEY,
        title=DEFAULT_TITLE,
        source_path=DEFAULT_SOURCE_PATH,
        prompt=resolve_prompt(DEFAULT_PROMPT),
        engine_model=settings.hf_model or None,
        duration_sec=DEFAULT_DURATION_SEC,
        resolution=DEFAULT_RESOLUTION,
        credits_cost=settings.credits_per_order,
        price_kopecks=settings.price_kopecks,
        is_active=True,
    )
    template.is_default = is_default
    return template


def apply_default_template(
    template: models.Template, settings: Settings, *, is_default: bool
) -> None:
    """Обновляет существующий шаблон из файла и настроек без пересоздания."""
    template.title = DEFAULT_TITLE
    template.source_path = DEFAULT_SOURCE_PATH
    template.prompt = resolve_prompt(DEFAULT_PROMPT)
    template.engine_model = settings.hf_model or None
    template.duration_sec = DEFAULT_DURATION_SEC
    template.resolution = DEFAULT_RESOLUTION
    template.credits_cost = settings.credits_per_order
    template.price_kopecks = settings.price_kopecks
    template.is_active = True
    if is_default:
        template.is_default = True


async def seed_default_template(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """Upsert шаблона: правка prompt.txt применяется при следующем старте."""
    async with session_factory() as session:
        defaults = await repo.count_default_templates(session)
        if defaults > 1:
            raise ConfigError("Найдено больше одного шаблона is_default: исправьте данные.")
        template = await repo.get_template_by_key(session, DEFAULT_TEMPLATE_KEY)
        if template is None:
            session.add(build_default_template(settings, is_default=defaults == 0))
        else:
            apply_default_template(template, settings, is_default=defaults == 0)
        await session.commit()
