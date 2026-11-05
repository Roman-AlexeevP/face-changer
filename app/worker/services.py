"""Зависимости воркера, собираемые в одной точке входа."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import utc_now
from app.config import Settings
from app.engines.base import VideoEngine
from app.storage.base import Storage


@dataclass(frozen=True)
class WorkerServices:
    """Всё, что нужно циклу и пайплайну воркера."""

    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    bot: Bot
    engine: VideoEngine
    storage: Storage
    now: Callable[[], datetime] = utc_now
